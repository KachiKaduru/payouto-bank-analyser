import sys
import re
import pdfplumber
from typing import List, Dict, Optional

from utils import (
    normalize_column_name,
    FIELD_MAPPINGS,
    MAIN_TABLE_SETTINGS,
    normalize_date,
    to_float,
    calculate_checks,
)


def clean_amount(val: str) -> str:
    if not val:
        return ""

    val = val.replace(",", "").strip()
    val = val.replace("-", "")

    if val.startswith("(") and val.endswith(")"):
        val = val[1:-1]

    return val


def parse(path: str) -> List[Dict[str, str]]:
    transactions = []
    global_headers = None

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                print(f"(wema:model_01): Processing page {page_num}", file=sys.stderr)

                # Table extraction settings
                tables = page.extract_tables(MAIN_TABLE_SETTINGS)

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
                            if len(first_row) <= 2:
                                continue

                        if is_header_row and not global_headers:
                            global_headers = normalized_first_row

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
                                f"(wema:model_01): No headers found by page {page_num}, skipping table",
                                file=sys.stderr,
                            )
                            continue

                        for row in data_rows:
                            if len(row) < len(global_headers):
                                row.extend([""] * (len(global_headers) - len(row)))

                            row_dict = {
                                global_headers[i]: row[i] if i < len(row) else ""
                                for i in range(len(global_headers))
                            }

                            debit_raw = row_dict.get("DEBIT", "") or "0.00"
                            credit_raw = row_dict.get("CREDIT", "") or "0.00"
                            bal_raw = row_dict.get("BALANCE", "")

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
                                "DEBIT": clean_amount(debit_raw),
                                "CREDIT": clean_amount(credit_raw),
                                "BALANCE": (
                                    f"{to_float(bal_raw):.2f}" if bal_raw else ""
                                ),
                            }

                            transactions.append(standardized_row)

        return calculate_checks(
            [t for t in transactions if t["TXN_DATE"] or t["VAL_DATE"]]
        )

    except Exception as e:
        print(f"Error processing wema:model_01 statement: {e}", file=sys.stderr)
        return []
