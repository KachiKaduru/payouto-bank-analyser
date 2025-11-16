import pdfplumber
import sys
from typing import List, Dict
from utils import *  # Import shared: to_float, normalize_date, etc.


def parse(path: str) -> List[Dict[str, str]]:
    transactions = []
    global_headers = None
    global_header_map = None

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                print(f"Processing page {page_num}", file=sys.stderr)
                # Variant-specific: Adjusted table settings (e.g., for Zenith/First Bank type with denser tables)
                table_settings = {
                    "vertical_strategy": "lines_strict",  # Variant tweak: Stricter lines
                    "horizontal_strategy": "lines_strict",
                    "explicit_vertical_lines": [],
                    "explicit_horizontal_lines": [],
                    "snap_tolerance": 2,  # Tighter snap for this variant
                    "join_tolerance": 2,
                    "min_words_vertical": 2,  # Allow shorter vertical text
                    "min_words_horizontal": 1,
                    "text_tolerance": 0.5,  # More precise text alignment
                }
                tables = page.extract_tables(table_settings)

                # The rest is the same as universal.py - copy the extraction logic here
                # ... (paste the if tables: ... else: ... block from universal.py)

                # Example variant addition: Bank-specific post-processing
                # e.g., for Zenith variant 001, clean remarks if they contain extra text
                # for txn in transactions:
                #     txn["REMARKS"] = txn["REMARKS"].replace("ZenithExtra:", "")  # Hypothetical

        return calculate_checks(
            [t for t in transactions if t["TXN_DATE"] or t["VAL_DATE"]]
        )

    except Exception as e:
        print(f"Error processing PDF: {e}", file=sys.stderr)
        return []


# Copy parse_text_row from universal.py if needed for text fallback
def parse_text_row(row: List[str], headers: List[str]) -> Dict[str, str]:
    standardized_row = {
        "TXN_DATE": "",
        "VAL_DATE": "",
        "REFERENCE": "",
        "REMARKS": "",
        "DEBIT": "0.00",
        "CREDIT": "0.00",
        "BALANCE": "0.00",
        "Check": "",
        "Check 2": "",
    }

    if len(row) < len(headers):
        row.extend([""] * (len(headers) - len(row)))

    row_dict = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}

    standardized_row["TXN_DATE"] = normalize_date(
        row_dict.get("TXN_DATE", row_dict.get("VAL_DATE", ""))
    )
    standardized_row["VAL_DATE"] = normalize_date(
        row_dict.get("VAL_DATE", row_dict.get("TXN_DATE", ""))
    )
    standardized_row["REFERENCE"] = row_dict.get("REFERENCE", "")
    standardized_row["REMARKS"] = row_dict.get("REMARKS", "")
    standardized_row["DEBIT"] = row_dict.get("DEBIT", "0.00")
    standardized_row["CREDIT"] = row_dict.get("CREDIT", "0.00")
    standardized_row["BALANCE"] = row_dict.get("BALANCE", "0.00")

    return standardized_row
