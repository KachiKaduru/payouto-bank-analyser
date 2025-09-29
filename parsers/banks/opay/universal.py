# banks/opay/universal.py
import sys
import pdfplumber
from typing import List, Dict
from utils import (
    normalize_column_name,
    FIELD_MAPPINGS,
    normalize_date,
    to_float,
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
                print(f"(opay): Processing page {page_num}", file=sys.stderr)
                tables = page.extract_tables()

                if not tables:
                    continue

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
                        data_rows = table[1:]
                    elif is_header_row and global_headers:
                        data_rows = (
                            table[1:]
                            if normalized_first_row == global_headers
                            else table
                        )
                    else:
                        data_rows = table

                    if not global_headers:
                        print(
                            f"(opay): No headers found by page {page_num}, skipping",
                            file=sys.stderr,
                        )
                        continue

                    for row in data_rows:
                        if len(row) < len(global_headers):
                            row.extend([""] * (len(global_headers) - len(row)))
                        row_dict = {
                            global_headers[i]: row[i]
                            for i in range(len(global_headers))
                        }
                        txn = {
                            "TXN_DATE": normalize_date(row_dict.get("TXN_DATE", "")),
                            "VAL_DATE": normalize_date(row_dict.get("VAL_DATE", "")),
                            "REFERENCE": row_dict.get("REFERENCE", ""),
                            "REMARKS": row_dict.get("REMARKS", ""),
                            "DEBIT": row_dict.get("DEBIT", "0.00"),
                            "CREDIT": row_dict.get("CREDIT", "0.00"),
                            "BALANCE": row_dict.get("BALANCE", ""),
                            "Check": "",
                            "Check 2": "",
                        }
                        transactions.append(txn)

        return calculate_checks(transactions)

    except Exception as e:
        print(f"Error processing Opay statement: {e}", file=sys.stderr)
        return []
