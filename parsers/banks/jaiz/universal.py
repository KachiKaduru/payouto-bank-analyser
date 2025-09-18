# banks/jaiz/universal.py
import sys
import re
import pdfplumber
from typing import List, Dict

from utils import (
    normalize_column_name,
    FIELD_MAPPINGS,
    normalize_date,
    to_float,
    calculate_checks,
)


def extract_balances(page) -> Dict[str, float]:
    """
    Extract start and end balances from the page text.
    Jaiz statements label them differently:
      - 'OPENING BAL.:' in the PDF = true start of period (earliest balance).
      - 'CLOSING BAL.:' in the PDF = true end of period (latest balance).
    """
    balances = {"start_balance": None, "end_balance": None}
    try:
        text = page.extract_text() or ""

        # True start of period (oldest balance)
        match_start = re.search(r"OPENING BAL\.*[: ]+([₦\d,.\-]+)", text, re.IGNORECASE)
        if match_start:
            balances["start_balance"] = to_float(match_start.group(1))
            print(
                f"(jaiz): Found 'OPENING BAL.:' = {balances['start_balance']} (treated as start_balance)",
                file=sys.stderr,
            )

        # True end of period (latest balance)
        match_end = re.search(r"CLOSING BAL\.*[: ]+([₦\d,.\-]+)", text, re.IGNORECASE)
        if match_end:
            balances["end_balance"] = to_float(match_end.group(1))
            print(
                f"(jaiz): Found 'CLOSING BAL.:' = {balances['end_balance']} (treated as end_balance)",
                file=sys.stderr,
            )

    except Exception as e:
        print(f"(jaiz): Could not extract balances: {e}", file=sys.stderr)

    return balances


def parse(path: str) -> List[Dict[str, str]]:
    raw_rows = []
    global_headers = None

    try:
        with pdfplumber.open(path) as pdf:
            if not pdf.pages:
                return []

            # Extract balances from first page
            balances = extract_balances(pdf.pages[0])
            start_balance = balances.get("start_balance")
            end_balance = balances.get("end_balance")

            print(f"(jaiz): Using start_balance = {start_balance}", file=sys.stderr)
            print(f"(jaiz): Using end_balance   = {end_balance}", file=sys.stderr)

            # Extract all rows (without computing balances yet)
            for page_num, page in enumerate(pdf.pages, 1):
                print(f"(jaiz): Processing page {page_num}", file=sys.stderr)

                table_settings = {
                    "vertical_strategy": "lines",
                    "horizontal_strategy": "lines",
                    "explicit_vertical_lines": [],
                    "explicit_horizontal_lines": [],
                    "snap_tolerance": 3,
                    "join_tolerance": 3,
                    "min_words_vertical": 3,
                    "min_words_horizontal": 1,
                    "text_tolerance": 1,
                }
                tables = page.extract_tables(table_settings)

                if not tables:
                    print(
                        f"(jaiz): No tables found on page {page_num}", file=sys.stderr
                    )
                    continue

                for table in tables:
                    if not table or len(table) < 2:
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
                            f"(jaiz): Stored headers: {global_headers}", file=sys.stderr
                        )
                        data_rows = table[1:]
                    elif is_header_row and global_headers:
                        if normalized_first_row == global_headers:
                            data_rows = table[1:]
                        else:
                            data_rows = table
                    else:
                        data_rows = table

                    if not global_headers:
                        continue

                    # Collect raw rows
                    for row in data_rows:
                        if len(row) < len(global_headers):
                            row.extend([""] * (len(global_headers) - len(row)))

                        row_dict = {
                            global_headers[i]: row[i] if i < len(global_headers) else ""
                            for i in range(len(global_headers))
                        }

                        raw_rows.append(row_dict)

            # Reverse rows to chronological order (oldest → newest)
            raw_rows.reverse()

            # Apply running balance
            transactions = []
            current_balance = start_balance if start_balance is not None else 0.0

            for row_dict in raw_rows:
                debit = to_float(row_dict.get("DEBIT", "0.00"))
                credit = to_float(row_dict.get("CREDIT", "0.00"))

                # Forward calculation
                current_balance = round(current_balance - debit + credit, 2)

                standardized_row = {
                    "TXN_DATE": normalize_date(
                        row_dict.get("TXN_DATE", row_dict.get("VAL_DATE", ""))
                    ),
                    "VAL_DATE": normalize_date(
                        row_dict.get("VAL_DATE", row_dict.get("TXN_DATE", ""))
                    ),
                    "REFERENCE": row_dict.get("REFERENCE", ""),
                    "REMARKS": row_dict.get("REMARKS", ""),
                    "DEBIT": f"{debit:.2f}" if debit else "0.00",
                    "CREDIT": f"{credit:.2f}" if credit else "0.00",
                    "BALANCE": f"{current_balance:.2f}",
                    "Check": "",
                    "Check 2": "",
                }

                transactions.append(standardized_row)

            # Cross-check final balance vs expected end_balance
            if end_balance is not None and abs(current_balance - end_balance) > 0.01:
                print(
                    f"(jaiz): ⚠️ Balance mismatch. Expected end_balance {end_balance}, got {current_balance}",
                    file=sys.stderr,
                )

            return calculate_checks(transactions)

    except Exception as e:
        print(f"Error processing Jaiz Bank statement: {e}", file=sys.stderr)
        return []
