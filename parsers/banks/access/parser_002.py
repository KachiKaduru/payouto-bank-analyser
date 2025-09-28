import pdfplumber
from typing import List, Dict
from utils import *


def parse(path: str) -> List[Dict[str, str]]:
    transactions = []
    global_headers = None
    global_header_map = None

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                print(f"(access:002): Processing page {page_num}", file=sys.stderr)
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

                        if not is_header_row:
                            # Skip summary-like 2-column tables without printing
                            if len(first_row) <= 2:
                                continue

                        if is_header_row and not global_headers:
                            # Store headers from the first page with headers
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
                            # Process data rows (skip header row)
                            data_rows = table[1:]
                        elif is_header_row and global_headers:
                            # Check if first row matches global_headers
                            if normalized_first_row == global_headers:
                                print(
                                    f"Skipping repeated header row on page {page_num}",
                                    file=sys.stderr,
                                )
                                data_rows = table[1:]  # Skip header row
                            else:
                                # Treat as data if different headers
                                print(
                                    f"Different headers on page {page_num}, treating as data",
                                    file=sys.stderr,
                                )
                                data_rows = table
                        else:
                            # No header row, use global_headers
                            data_rows = table

                        if not global_headers:
                            print(
                                f"(access:002): No headers found by page {page_num}, skipping table",
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
                                "BALANCE": row_dict.get("BALANCE", ""),
                                "Check": "",
                                "Check 2": "",
                            }

                            if has_amount and balance_idx != -1:
                                amount = normalize_money(row_dict.get("AMOUNT", ""))
                                current_balance = normalize_money(
                                    row_dict.get("BALANCE", "")
                                )

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
                                prev_balance = normalize_money(current_balance)
                            else:
                                standardized_row["DEBIT"] = normalize_money(
                                    row_dict.get("DEBIT", "0.00")
                                )
                                standardized_row["CREDIT"] = normalize_money(
                                    row_dict.get("CREDIT", "0.00")
                                )
                                standardized_row["BALANCE"] = (
                                    f"{to_float(row_dict.get('BALANCE', '0')):.2f}"
                                )

                                bal_raw = standardized_row["BALANCE"]
                                prev_balance = (
                                    to_float(bal_raw) if bal_raw else prev_balance
                                )

                            transactions.append(standardized_row)
                else:
                    # Fallback: Extract text if no tables found
                    print(
                        f"No tables found on page {page_num}, attempting text extraction ",
                        file=sys.stderr,
                    )

        return calculate_checks(
            [t for t in transactions if t["TXN_DATE"] or t["VAL_DATE"]]
        )

    except Exception as e:
        print(f"Error processing statement: {e}", file=sys.stderr)
        return []
