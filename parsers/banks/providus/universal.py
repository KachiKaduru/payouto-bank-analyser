import sys
import pdfplumber
from typing import List, Dict
from utils import (
    normalize_column_name,
    FIELD_MAPPINGS,
    parse_text_row,
    calculate_checks,
    MAIN_TABLE_SETTINGS,
    to_float,
)


# --------------------------------------------------------------
# Detect if a row is a REMARKS-only row (to be removed)
# --------------------------------------------------------------
def is_garbage_row(parsed):
    """
    Garbage rows include:
    - Rows with only REMARKS (no dates, no amounts)
    - Rows with no TXN_DATE, no VAL_DATE, no REMARKS,
      AND debit/credit/balance are all empty or zero.
    """

    if not parsed:
        return True

    txn = (parsed.get("TXN_DATE") or "").strip()
    val = (parsed.get("VAL_DATE") or "").strip()
    remarks = (parsed.get("REMARKS") or "").strip()

    debit = to_float(str(parsed.get("DEBIT", "0") or "0"))
    credit = to_float(str(parsed.get("CREDIT", "0") or "0"))

    # Case 1 — remarks-only row
    if remarks and not txn and not val:
        if abs(debit) < 1e-9 and abs(credit) < 1e-9:
            return True

    # Case 2 — completely empty row / meaningless numeric junk (like page numbers)
    if not txn and not val and not remarks:
        if abs(debit) < 1e-9 and abs(credit) < 1e-9:
            # balance may be page number, ignore it
            return True

    return False


# --------------------------------------------------------------
# Convert extracted row → normalized dict
# --------------------------------------------------------------
def _convert_row(row: List[str], headers: List[str]):
    if not headers:
        return None

    # Fix short rows
    if len(row) < len(headers):
        row = row + [""] * (len(headers) - len(row))

    # Fix long rows
    row = row[: len(headers)]

    parsed = parse_text_row(row, headers)

    # Ignore total/closing rows
    txn_date = (parsed.get("TXN_DATE") or "").strip().lower()
    if txn_date.startswith(("total", "closing", "opening", "subtotal")):
        return None

    return parsed


# --------------------------------------------------------------
# Debit/Credit swap detection
# --------------------------------------------------------------
def detect_and_fix_debit_credit_swap(transactions, sample_size=50, tolerance=0.01):
    vote_ok = 0
    vote_swap = 0
    checked = 0
    prev_balance = None

    for t in transactions:
        bal = to_float(t.get("BALANCE", ""))
        debit = to_float(t.get("DEBIT", ""))
        credit = to_float(t.get("CREDIT", ""))

        if prev_balance is None:
            prev_balance = bal
            continue

        # ignore rows without movement
        if abs(debit) < 1e-9 and abs(credit) < 1e-9:
            prev_balance = bal
            continue

        expected_delta = round(credit - debit, 2)
        actual_delta = round(bal - prev_balance, 2)

        if abs(expected_delta - actual_delta) <= tolerance:
            vote_ok += 1
        elif abs((-expected_delta) - actual_delta) <= tolerance:
            vote_swap += 1

        checked += 1
        prev_balance = bal

        if checked >= sample_size:
            break

    # Swap required
    if checked > 0 and vote_swap > vote_ok and vote_swap >= max(2, checked // 3):
        for t in transactions:
            t["DEBIT"], t["CREDIT"] = t["CREDIT"], t["DEBIT"]
        return transactions, True

    return transactions, False


# --------------------------------------------------------------
# Main universal parser
# --------------------------------------------------------------
def parse(path: str) -> List[Dict[str, str]]:
    transactions = []
    global_headers = None

    try:
        with pdfplumber.open(path) as pdf:

            # ----------------------------------------------------
            # PAGE 1 — detect headers using the longest table
            # ----------------------------------------------------
            first_page = pdf.pages[0]
            tables = first_page.extract_tables(MAIN_TABLE_SETTINGS)

            if not tables:
                print("(universal) No tables found on page 1", file=sys.stderr)
                return []

            main_table = max(tables, key=lambda t: len(t))

            header_row = main_table[0]
            global_headers = [normalize_column_name(h) if h else "" for h in header_row]

            if not any(h in FIELD_MAPPINGS for h in global_headers):
                print("(universal) Failed to detect valid headers", file=sys.stderr)
                return []

            print(
                f"(universal) Detected global headers: {global_headers}",
                file=sys.stderr,
            )

            # Parse page 1 rows
            for raw in main_table[1:]:
                # Convert None to empty strings, to satisfy type checker expectations (List[str])
                normalized_row = [(cell if cell is not None else "") for cell in raw]
                parsed = _convert_row(normalized_row, global_headers)
                if parsed and not is_garbage_row(parsed):
                    transactions.append(parsed)
            # REMAINING PAGES — data-only tables
            # ----------------------------------------------------
            for page_num in range(1, len(pdf.pages)):
                page = pdf.pages[page_num]
                page_tables = page.extract_tables(MAIN_TABLE_SETTINGS)

                if not page_tables:
                    continue

                for table in page_tables:
                    if len(table) < 1:
                        continue

                    # Detect internal headers on later pages
                    candidate = [
                        normalize_column_name(c) if c else "" for c in table[0]
                    ]
                    is_header_row = any(c in FIELD_MAPPINGS for c in candidate)

                    data_rows = (
                        table[1:]
                        if is_header_row and candidate == global_headers
                        else table
                    )

                    for raw in data_rows:
                        # Convert None to empty strings, to satisfy type checker expectations (List[str])
                        normalized_row = [
                            (cell if cell is not None else "") for cell in raw
                        ]
                        parsed = _convert_row(normalized_row, global_headers)
                        if parsed and not is_garbage_row(parsed):
                            transactions.append(parsed)

        # ----------------------------------------------------
        # FINAL CLEANUP
        # ----------------------------------------------------
        transactions, _ = detect_and_fix_debit_credit_swap(transactions)

        # Final checks: balance consistency, sequence, etc.
        return calculate_checks(transactions)

    except Exception as e:
        print(f"Error (universal parser): {e}", file=sys.stderr)
        return []
