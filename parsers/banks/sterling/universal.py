import sys
import re
import pdfplumber
from typing import List, Dict

from utils import (
    normalize_column_name,
    FIELD_MAPPINGS,
    normalize_date,
    to_float,
    normalize_money,
    parse_text_row,
    calculate_checks,
)


def parse(path: str) -> List[Dict[str, str]]:
    transactions = []
    global_headers = None
    global_header_map = None

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                print(f"(sterling): Processing page {page_num}", file=sys.stderr)
                # Table extraction settings
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

                if tables:
                    for table in tables:
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
                            global_header_map = {
                                i: h
                                for i, h in enumerate(global_headers)
                                if h in FIELD_MAPPINGS
                            }
                            print(
                                f"Stored global headers: {global_headers}",
                                file=sys.stderr,
                            )
                            data_rows = table[1:]
                        elif is_header_row and global_headers:
                            if normalized_first_row == global_headers:
                                print(
                                    f"Skipping repeated header row on page {page_num}",
                                    file=sys.stderr,
                                )
                                data_rows = table[1:]
                            else:
                                print(
                                    f"Different headers on page {page_num}, treating as data",
                                    file=sys.stderr,
                                )
                                data_rows = table
                        else:
                            data_rows = table

                        if not global_headers:
                            print(
                                f"(sterling): No headers found by page {page_num}, skipping table",
                                file=sys.stderr,
                            )
                            continue

                        has_amount = "AMOUNT" in global_headers
                        balance_idx = (
                            global_headers.index("BALANCE")
                            if "BALANCE" in global_headers
                            else -1
                        )
                        prev_balance = None

                        for row in data_rows:
                            if len(row) < len(global_headers):
                                row.extend([""] * (len(global_headers) - len(row)))

                            row_dict = {
                                global_headers[i]: row[i] if i < len(row) else ""
                                for i in range(len(global_headers))
                            }

                            standardized_row = {
                                "TXN_DATE": normalize_date(
                                    row_dict.get(
                                        "TXN_DATE", row_dict.get("VAL_DATE", "")
                                    )
                                ),
                                "VAL_DATE": normalize_date(
                                    row_dict.get(
                                        "VAL_DATE", row_dict.get("TXN_DATE", "")
                                    )
                                ),
                                "REFERENCE": row_dict.get("REFERENCE", ""),
                                "REMARKS": row_dict.get("REMARKS", ""),
                                "DEBIT": "",
                                "CREDIT": "",
                                "BALANCE": normalize_money(row_dict.get("BALANCE", "")),
                                "Check": "",
                                "Check 2": "",
                            }

                            if has_amount and balance_idx != -1:
                                amount = to_float(row_dict.get("AMOUNT", ""))
                                current_balance = to_float(row_dict.get("BALANCE", ""))

                                if prev_balance is not None:
                                    if current_balance < prev_balance:
                                        standardized_row["DEBIT"] = f"{abs(amount):.2f}"
                                        standardized_row["CREDIT"] = "0.00"
                                    else:
                                        standardized_row["DEBIT"] = "0.00"
                                        standardized_row["CREDIT"] = (
                                            f"{abs(amount):.2f}"
                                        )
                                else:
                                    standardized_row["DEBIT"] = "0.00"
                                    standardized_row["CREDIT"] = "0.00"
                                prev_balance = current_balance
                            else:
                                standardized_row["DEBIT"] = normalize_money(
                                    row_dict.get("DEBIT", "0.00")
                                )
                                standardized_row["CREDIT"] = normalize_money(
                                    row_dict.get("CREDIT", "0.00")
                                )
                                prev_balance = (
                                    to_float(standardized_row["BALANCE"])
                                    if standardized_row["BALANCE"]
                                    else prev_balance
                                )

                            transactions.append(standardized_row)
                else:
                    print(
                        f"(sterling): No tables found on page {page_num}, attempting text extraction",
                        file=sys.stderr,
                    )
                    text = page.extract_text()
                    if text and global_headers:
                        lines = text.split("\n")
                        current_row = []
                        for line in lines:
                            if re.match(r"^\d{2}[-/.]\d{2}[-/.]\d{4}", line):
                                if current_row:
                                    transactions.append(
                                        parse_text_row(current_row, global_headers)
                                    )
                                current_row = [line]
                            else:
                                current_row.append(line)
                        if current_row:
                            transactions.append(
                                parse_text_row(current_row, global_headers)
                            )

        return calculate_checks(
            [t for t in transactions if t["TXN_DATE"] or t["VAL_DATE"]]
        )

    except Exception as e:
        print(f"Error processing Sterling Bank statement: {e}", file=sys.stderr)
        return []
