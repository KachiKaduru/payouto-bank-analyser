import sys
import re
import pdfplumber
from typing import List, Dict

from utils import (
    normalize_column_name,
    FIELD_MAPPINGS,
    MAIN_TABLE_SETTINGS,
    to_float,
    parse_text_row,
    calculate_checks,
)


def clean_transaction(row: Dict[str, str], prev_balance: float) -> Dict[str, str]:
    """
    Fix misaligned UBA_parser_001 rows where narration fragments spill into DEBIT, CREDIT, or REFERENCE.
    Also fixes false double-entry rows by comparing balance movement.
    """
    remarks_extra = []

    # --- Clean REFERENCE ---
    ref = row.get("REFERENCE", "")
    if ref and not re.match(r"^\d+$", ref.strip()):  # not purely numeric
        remarks_extra.append(ref)
        row["REFERENCE"] = ""

    # Helper to check if a string looks like a money value with decimals
    def is_decimal_number(value: str) -> bool:
        if not isinstance(value, str):
            return False
        return bool(re.match(r"^\d[\d,]*\.\d{2}$", value.strip()))

    # --- Clean DEBIT ---
    debit = (row.get("DEBIT") or "").strip()
    credit = (row.get("CREDIT") or "").strip()

    if debit:
        if is_decimal_number(debit):
            row["DEBIT"] = debit
        else:
            if re.match(r"^\d+$", debit) and is_decimal_number(credit):
                remarks_extra.append(debit)
                row["DEBIT"] = "0.00"
            else:
                numbers = re.findall(r"\d[\d,]*\.?\d*", debit)
                if numbers and is_decimal_number(numbers[-1]):
                    row["DEBIT"] = numbers[-1]
                    junk = debit.replace(numbers[-1], "").strip()
                    if junk:
                        remarks_extra.append(junk)
                else:
                    remarks_extra.append(debit)
                    row["DEBIT"] = "0.00"
    else:
        row["DEBIT"] = "0.00"

    # --- Clean CREDIT ---
    if credit:
        if is_decimal_number(credit):
            row["CREDIT"] = credit
        else:
            if re.match(r"^\d+$", credit) and is_decimal_number(debit):
                remarks_extra.append(credit)
                row["CREDIT"] = "0.00"
            else:
                numbers = re.findall(r"\d[\d,]*\.?\d*", credit)
                if numbers and is_decimal_number(numbers[-1]):
                    row["CREDIT"] = numbers[-1]
                    junk = credit.replace(numbers[-1], "").strip()
                    if junk:
                        remarks_extra.append(junk)
                else:
                    remarks_extra.append(credit)
                    row["CREDIT"] = "0.00"
    else:
        row["CREDIT"] = "0.00"

    # --- Intelligent Balance-Based Fix ---
    try:
        # current_balance may be empty or malformed; to_float returns float or None
        current_balance = None
        bal_raw = row.get("BALANCE", "")
        if bal_raw:
            # Use to_float for robust parsing (handles commas and blanks)
            current_balance = to_float(bal_raw)

        # Parse debit/credit values to floats (safe fallback to 0.0)
        try:
            debit_val = float(row["DEBIT"].replace(",", "")) if row["DEBIT"] else 0.0
        except Exception:
            debit_val = 0.0
        try:
            credit_val = float(row["CREDIT"].replace(",", "")) if row["CREDIT"] else 0.0
        except Exception:
            credit_val = 0.0

        # If both debit & credit are > 0, and we know prev_balance, decide which one is wrong
        if (
            debit_val > 0
            and credit_val > 0
            and prev_balance is not None
            and current_balance is not None
        ):
            if current_balance > prev_balance:
                # Balance increased → CREDIT transaction; clear DEBIT
                row["DEBIT"] = "0.00"
            elif current_balance < prev_balance:
                # Balance decreased → DEBIT transaction; clear CREDIT
                row["CREDIT"] = "0.00"
            # if equal, ambiguous — keep as-is (or we could clear smaller amount; opted to keep)
    except Exception:
        # never fail the cleaner; leave row as-is if something unexpected happens
        pass

    # Merge extras into remarks
    if remarks_extra:
        row["REMARKS"] = (
            row.get("REMARKS", "") + " " + " ".join(remarks_extra)
        ).strip()

    return row


def parse(path: str) -> List[Dict[str, str]]:
    transactions = []
    global_headers = None
    prev_balance = None  # persist across the whole document

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                print(f"(uba_parser_001): Processing page {page_num}", file=sys.stderr)
                # Table extraction settings (from MAIN_TABLE_SETTINGS)
                table_settings = MAIN_TABLE_SETTINGS.copy()
                tables = page.extract_tables(table_settings) or []

                # Skip first table on page 1 if there are multiple (Account Summary)
                if page_num == 1 and len(tables) >= 2:
                    print(
                        f"(uba_parser_001): Skipping first table on page 1",
                        file=sys.stderr,
                    )
                    tables = tables[1:]

                if not tables:
                    print(
                        f"(uba_parser_001): No tables found on page {page_num}",
                        file=sys.stderr,
                    )
                    # If headers already known, try text fallback for that page
                    if global_headers:
                        text = page.extract_text() or ""
                        lines = text.split("\n")
                        current_row = []
                        for line in lines:
                            if re.match(r"^\d{2}[-/.]\d{2}[-/.]\d{4}", line):
                                if current_row:
                                    standardized_row = parse_text_row(
                                        current_row, global_headers
                                    )
                                    # determine current balance before cleaning
                                    current_balance = (
                                        to_float(standardized_row.get("BALANCE", ""))
                                        if standardized_row.get("BALANCE")
                                        else None
                                    )
                                    # Clean using prev_balance
                                    standardized_row = clean_transaction(
                                        standardized_row, prev_balance
                                    )
                                    transactions.append(standardized_row)
                                    if current_balance is not None:
                                        prev_balance = current_balance
                                current_row = [line]
                            else:
                                current_row.append(line)
                        if current_row:
                            standardized_row = parse_text_row(
                                current_row, global_headers
                            )
                            current_balance = (
                                to_float(standardized_row.get("BALANCE", ""))
                                if standardized_row.get("BALANCE")
                                else None
                            )
                            standardized_row = clean_transaction(
                                standardized_row, prev_balance
                            )
                            transactions.append(standardized_row)
                            if current_balance is not None:
                                prev_balance = current_balance
                    continue

                # Iterate through all tables on the page (some PDFs split header/data)
                for table_idx, table in enumerate(tables, start=1):
                    if not table or len(table) < 1:
                        continue

                    first_row = table[0]
                    normalized_first_row = [
                        normalize_column_name(h) if h else "" for h in first_row
                    ]
                    is_header_row = any(
                        h in FIELD_MAPPINGS for h in normalized_first_row if h
                    )

                    if is_header_row and not global_headers:
                        global_headers = normalized_first_row
                        print(
                            f"Stored global headers: {global_headers}", file=sys.stderr
                        )
                        data_rows = table[1:]
                    elif is_header_row and global_headers:
                        if normalized_first_row == global_headers:
                            # If header repeated but table has data rows, drop header row and use remainder
                            if len(table) > 1:
                                data_rows = table[1:]
                            else:
                                # header-only table (no rows), skip
                                data_rows = []
                        else:
                            # different header layout - treat entire table as data (best-effort)
                            data_rows = table
                    else:
                        data_rows = table

                    if not global_headers:
                        # no headers determined yet; skip this table (we can't map columns)
                        print(
                            f"(uba_parser_001): No headers found on page {page_num}, table {table_idx}, skipping",
                            file=sys.stderr,
                        )
                        continue

                    # Process data_rows
                    for row in data_rows:
                        # parse_text_row expects a list of cell strings + global_headers
                        standardized_row = parse_text_row(row, global_headers)

                        # If this is an explicit opening balance description, set both to 0.00
                        if (
                            standardized_row.get("REMARKS")
                            and "opening balance" in standardized_row["REMARKS"].lower()
                        ):
                            standardized_row["DEBIT"] = "0.00"
                            standardized_row["CREDIT"] = "0.00"
                        # Determine current balance BEFORE cleaning (clean uses prev_balance)
                        current_balance = None
                        if standardized_row.get("BALANCE"):
                            current_balance = to_float(
                                standardized_row.get("BALANCE", "")
                            )

                        # Clean using previous balance (not current)
                        standardized_row = clean_transaction(
                            standardized_row, prev_balance
                        )

                        # Append and then update prev_balance from current_balance (if present)
                        transactions.append(standardized_row)
                        if current_balance is not None:
                            prev_balance = current_balance

            # final filter & checks
            cleaned = [
                t for t in transactions if t.get("TXN_DATE") or t.get("VAL_DATE")
            ]
            return calculate_checks(cleaned)

    except Exception as e:
        print(f"Error processing UBA variant statement: {e}", file=sys.stderr)
        return []
