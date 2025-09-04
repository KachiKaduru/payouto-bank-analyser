import pdfplumber
import re
import sys
from typing import List, Dict
from utils import (
    normalize_column_name,
    FIELD_MAPPINGS,
    normalize_date,
    to_float,
    calculate_checks,
)


def parse(path: str) -> List[Dict[str, str]]:
    transactions = []
    global_headers = None
    prev_balance = None

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                print(f"(uba parser_001): Processing page {page_num}", file=sys.stderr)

                # Extract tables from the page
                table_settings = {
                    "vertical_strategy": "lines",  # Use graphical lines for columns
                    "horizontal_strategy": "lines",  # Use graphical lines for rows
                    "snap_tolerance": 8,  # Handle variable spacing
                    "join_tolerance": 8,  # Merge close lines
                    "min_words_vertical": 1,  # Detect short columns
                    "min_words_horizontal": 1,  # Detect short rows
                    "text_tolerance": 3,  # Allow overlap for multi-line text
                }
                tables = page.extract_tables(table_settings)

                if not tables or len(tables) < 1:
                    print(
                        f"(uba parser_001): No tables found on page {page_num}, skipping",
                        file=sys.stderr,
                    )
                    continue

                # Handle multiple tables on page 1 (skip Account Summary)
                if page_num == 1 and len(tables) > 1:
                    tables = tables[1:]  # Skip the first table (Account Summary)

                for table in tables:
                    if not table or len(table) < 1:
                        continue

                    # Clean and merge first row cells for headers
                    first_row = []
                    current_cell = ""
                    for cell in table[0]:
                        if cell and cell.strip():
                            if current_cell:
                                first_row.append(current_cell.strip())
                            current_cell = cell.strip()
                        else:
                            current_cell += " " + (cell or "").strip()
                    if current_cell:
                        first_row.append(current_cell.strip())

                    normalized_first_row = [
                        normalize_column_name(h) if h else "" for h in first_row
                    ]
                    is_header_row = (
                        any(h in FIELD_MAPPINGS for h in normalized_first_row if h)
                        and len(normalized_first_row) >= 5
                    )  # Ensure valid header

                    if is_header_row and not global_headers:
                        global_headers = normalized_first_row
                        print(
                            f"Stored global headers: {global_headers}", file=sys.stderr
                        )
                        data_rows = table[1:]  # Skip header row
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
                            f"(uba parser_001): No headers found by page {page_num}, skipping table",
                            file=sys.stderr,
                        )
                        continue

                    # Process data rows
                    for row in data_rows:
                        # Clean and merge row cells
                        cleaned_row = []
                        current_cell = ""
                        for cell in row:
                            if cell and cell.strip():
                                if (
                                    current_cell
                                    and any(c.isdigit() for c in current_cell)
                                    and any(c.isdigit() for c in cell)
                                ):
                                    cleaned_row.append(
                                        current_cell.strip()
                                    )  # Split numeric sequences
                                    current_cell = cell.strip()
                                elif current_cell:
                                    cleaned_row.append(current_cell.strip())
                                    current_cell = cell.strip()
                                else:
                                    current_cell = cell.strip()
                            else:
                                current_cell += " " + (cell or "").strip()
                        if current_cell:
                            cleaned_row.append(current_cell.strip())

                        if len(cleaned_row) < 2:  # Skip invalid rows
                            continue

                        # Align to headers
                        if len(cleaned_row) < len(global_headers):
                            cleaned_row.extend(
                                [""] * (len(global_headers) - len(cleaned_row))
                            )
                        elif len(cleaned_row) > len(global_headers):
                            cleaned_row = cleaned_row[: len(global_headers)]

                        row_dict = {
                            global_headers[j]: cleaned_row[j]
                            for j in range(len(global_headers))
                        }

                        # Skip if no valid date
                        txn_date = normalize_date(
                            row_dict.get("TXN_DATE", row_dict.get("VAL_DATE", ""))
                        )
                        if not txn_date or txn_date == "-":
                            continue

                        standardized_row = {
                            "TXN_DATE": txn_date,
                            "VAL_DATE": normalize_date(
                                row_dict.get("VAL_DATE", row_dict.get("TXN_DATE", ""))
                            ),
                            "REFERENCE": row_dict.get("REFERENCE", "").strip(),
                            "REMARKS": row_dict.get("REMARKS", "").strip(),
                            "DEBIT": "",
                            "CREDIT": "",
                            "BALANCE": row_dict.get("BALANCE", "").strip(),
                            "Check": "",
                            "Check 2": "",
                        }

                        # Handle opening balance row
                        is_opening_balance = (
                            "opening balance" in standardized_row["REMARKS"].lower()
                        )
                        if is_opening_balance:
                            standardized_row["DEBIT"] = "0.00"
                            standardized_row["CREDIT"] = "0.00"
                        else:
                            # Infer debit/credit from balance
                            current_balance = to_float(standardized_row["BALANCE"])
                            if prev_balance is not None and current_balance is not None:
                                balance_diff = current_balance - prev_balance
                                if balance_diff < 0:
                                    standardized_row["DEBIT"] = (
                                        f"{abs(balance_diff):.2f}"
                                    )
                                elif balance_diff > 0:
                                    standardized_row["CREDIT"] = (
                                        f"{abs(balance_diff):.2f}"
                                    )
                            prev_balance = current_balance

                        transactions.append(standardized_row)

        return calculate_checks([t for t in transactions if t["TXN_DATE"]])

    except Exception as e:
        print(f"Error processing UBA statement (parser_001): {e}", file=sys.stderr)
        return []
