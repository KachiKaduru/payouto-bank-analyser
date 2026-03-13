import sys
import re
import pdfplumber
from typing import List, Dict, Optional

from utils import (
    MAIN_TABLE_SETTINGS,
    FIELD_MAPPINGS,
    STANDARDIZED_ROW,
    normalize_column_name,
    normalize_date,
    normalize_money,
    normalize_whitespace,
    to_float,
    calculate_checks,
)

# Jaiz dates usually look like:
# 02-\nOCT-25\n14:12:08
# 23-\nOCT-\n25
RX_JAIZ_DATE = re.compile(r"(\d{2})\s*-\s*([A-Z]{3})\s*-\s*(\d{2})", re.IGNORECASE)
RX_SERIAL = re.compile(r"^\d{1,5}$")


def _cell_text(cell) -> str:
    if cell is None:
        return ""
    return str(cell).strip()


def _looks_like_serial(cell: str) -> bool:
    return bool(RX_SERIAL.fullmatch((cell or "").strip()))


def _extract_jaiz_date(raw: str) -> str:
    """
    Pull only the DD-MMM-YY portion from TXN_DATE/VAL_DATE cells.
    Ignores time fragments like 14:12:08 or 00:11.
    """
    if not raw:
        return ""

    text = _cell_text(raw).replace("\n", " ").upper()
    m = RX_JAIZ_DATE.search(text)
    if m:
        d, mon, yy = m.groups()
        return normalize_date(f"{d}-{mon}-{yy}")

    # fallback
    compact = re.sub(r"\s+", "", _cell_text(raw))
    return normalize_date(compact)


def _is_probable_noise_row(row: List[str]) -> bool:
    joined = " ".join(_cell_text(x) for x in row if x).strip().lower()
    if not joined:
        return True

    noise_markers = [
        "account statement - jaiz portal",
        "jaizportal.jaiz.local",
        "current system running date",
    ]
    return any(marker in joined for marker in noise_markers)


def _realign_row_to_headers(row: List[str], headers: List[str]) -> List[str]:
    """
    Fix Jaiz continuation-page extraction drift.

    Expected good shape:
        [S/N, TXN_DATE, VAL_DATE, REMARKS, BRANCH, INSTR_NO, REFERENCE, JV, DEBIT, CREDIT, BALANCE]

    Observed bad shape on continuation pages:
        [JUNK_OR_NONE, S/N, TXN_DATE, VAL_DATE, REMARKS, BRANCH, INSTR_NO, REFERENCE, JV, DEBIT, CREDIT, BALANCE]

    So if we detect an extra leading cell and the serial number at index 1, we shift left by one.
    """
    row = [_cell_text(c) for c in row]
    expected_len = len(headers)

    # Common Jaiz continuation-page artifact:
    # extra leading junk/None cell before real S/N
    if len(row) == expected_len + 1 and _looks_like_serial(row[1]):
        row = row[1:]

    # More defensive fallback:
    # if row is too wide, look for the first likely S/N in the first few cells and slice from there
    if len(row) > expected_len:
        for start_idx in range(min(3, len(row))):
            if _looks_like_serial(row[start_idx]):
                candidate = row[start_idx : start_idx + expected_len]
                if len(candidate) == expected_len:
                    row = candidate
                    break

    # Trim overflow
    if len(row) > expected_len:
        row = row[:expected_len]

    # Pad short rows
    if len(row) < expected_len:
        row.extend([""] * (expected_len - len(row)))

    return row


def _row_to_standardized(
    row: List[str], headers: List[str]
) -> Optional[Dict[str, str]]:
    row = _realign_row_to_headers(row, headers)

    if _is_probable_noise_row(row):
        return None

    row_dict = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}

    # Ignore opening balance / brought-forward rows with no dates
    remarks = _cell_text(row_dict.get("REMARKS", ""))
    if remarks.upper() == "B/F":
        return None

    standardized = STANDARDIZED_ROW.copy()

    standardized["TXN_DATE"] = _extract_jaiz_date(
        row_dict.get("TXN_DATE", "") or row_dict.get("VAL_DATE", "")
    )
    standardized["VAL_DATE"] = _extract_jaiz_date(
        row_dict.get("VAL_DATE", "") or row_dict.get("TXN_DATE", "")
    )

    standardized["REFERENCE"] = _cell_text(row_dict.get("REFERENCE", ""))
    standardized["REMARKS"] = normalize_whitespace(remarks)

    standardized["DEBIT"] = normalize_money(row_dict.get("DEBIT", "0.00"))
    standardized["CREDIT"] = normalize_money(row_dict.get("CREDIT", "0.00"))

    bal_raw = _cell_text(row_dict.get("BALANCE", ""))
    standardized["BALANCE"] = f"{to_float(bal_raw):.2f}" if bal_raw else ""

    # Final sanity gate: a valid transaction should have at least a date and balance,
    # or a date and either debit/credit.
    has_date = bool(standardized["TXN_DATE"] or standardized["VAL_DATE"])
    has_amount = standardized["DEBIT"] not in {"", "0.00"} or standardized[
        "CREDIT"
    ] not in {"", "0.00"}
    has_balance = standardized["BALANCE"] not in {"", "0.00"}

    if not has_date and not has_amount and not has_balance:
        return None

    return standardized


def parse(path: str) -> List[Dict[str, str]]:
    transactions: List[Dict[str, str]] = []
    global_headers: Optional[List[str]] = None

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                print(f"(jaiz_model_01): Processing page {page_num}", file=sys.stderr)

                tables = page.extract_tables(MAIN_TABLE_SETTINGS)

                if not tables:
                    print(
                        f"(jaiz_model_01): No tables found on page {page_num}",
                        file=sys.stderr,
                    )
                    continue

                for table in tables:
                    if not table:
                        continue

                    first_row = table[0]
                    normalized_first_row = [
                        normalize_column_name(_cell_text(h)) for h in first_row
                    ]

                    is_header_row = any(
                        h in FIELD_MAPPINGS for h in normalized_first_row if h
                    )

                    if is_header_row and global_headers is None:
                        global_headers = normalized_first_row
                        print(
                            f"Stored global headers: {global_headers}", file=sys.stderr
                        )
                        data_rows = table[1:]
                    elif is_header_row and global_headers is not None:
                        if normalized_first_row == global_headers:
                            print(
                                f"Skipping repeated header row on page {page_num}",
                                file=sys.stderr,
                            )
                            data_rows = table[1:]
                        else:
                            # Rare case: header-like row but not the same structure
                            # Treat the whole table as data only if headers were already known.
                            print(
                                f"Header-like but different row on page {page_num}; using stored headers",
                                file=sys.stderr,
                            )
                            data_rows = table
                    else:
                        if global_headers is None:
                            print(
                                f"(jaiz_model_01): No headers found by page {page_num}, skipping table",
                                file=sys.stderr,
                            )
                            continue
                        data_rows = table

                    if global_headers is None:
                        continue

                    for raw_row in data_rows:
                        txn = _row_to_standardized(raw_row, global_headers)
                        if txn and (txn["TXN_DATE"] or txn["VAL_DATE"]):
                            transactions.append(txn)

        return calculate_checks(transactions)

    except Exception as e:
        print(f"Error processing Jaiz Bank statement: {e}", file=sys.stderr)
        return []
