import re
from typing import List, Dict
import pdfplumber

from utils import (
    MAIN_TABLE_SETTINGS,
    normalize_column_name,
    FIELD_MAPPINGS,
    parse_text_row,
    calculate_checks,
)


# -----------------------------------------------------
# Helper — clean invalid numeric amounts
# -----------------------------------------------------
def clean_amount(value: str) -> str:
    """
    Returns a sanitized amount:
    - Rejects values containing letters (e.g. "Page 4")
    - Rejects values without a decimal point (page numbers)
    - Returns 0.00 for invalid or empty entries
    - Otherwise formats as a 2-decimal float
    """
    if not value:
        return "0.00"

    s = value.strip()

    # Reject alphanumeric junk like "Page", "Page 3"
    if re.search(r"[A-Za-z]", s):
        return "0.00"

    # Values without decimals are considered invalid for this bank
    if "." not in s:
        return "0.00"

    try:
        return f"{float(s):.2f}"
    except:
        return "0.00"


# -----------------------------------------------------
# Helper — convert raw table row → standardized dict
# -----------------------------------------------------
def _build_clean_dict(row: List[str], headers: List[str]) -> Dict[str, str]:
    """
    Normalizes row length, maps columns → utils.parse_text_row,
    cleans DEBIT/CREDIT, and filters out footer/summary rows.
    """

    if not headers:
        return None

    # Fix short rows
    if len(row) < len(headers):
        row = row + [""] * (len(headers) - len(row))

    parsed = parse_text_row(row, headers)

    # Skip summary or total rows
    txn_date = (parsed.get("TXN_DATE") or "").lower()
    if txn_date.startswith(("total", "closing", "opening", "subtotal")):
        return None

    # Clean suspicious amounts (often page numbers)
    parsed["DEBIT"] = clean_amount(parsed.get("DEBIT", ""))
    parsed["CREDIT"] = clean_amount(parsed.get("CREDIT", ""))

    return parsed


# -----------------------------------------------------
# Main parser for Providus (variant) statement
# -----------------------------------------------------
def parse(path: str) -> List[Dict[str, str]]:
    transactions = []
    global_headers = None

    with pdfplumber.open(path) as pdf:

        # -------------------------------------------
        # PAGE 1 — detect the LONGEST table
        # -------------------------------------------
        first_page = pdf.pages[0]
        tables = first_page.extract_tables(MAIN_TABLE_SETTINGS)

        if not tables:
            return []

        # Pick the table with the most rows
        longest_table = max(tables, key=lambda t: len(t))

        if len(longest_table) < 2:
            return []  # no data rows

        # The first row contains the headers
        header_row = longest_table[0]

        # Normalize headers
        global_headers = [normalize_column_name(h) if h else "" for h in header_row]

        # Must contain mapped field names
        if not any(h in FIELD_MAPPINGS for h in global_headers):
            return []

        # Parse page 1 rows
        for raw in longest_table[1:]:
            cleaned = _build_clean_dict(raw, global_headers)
            if cleaned:
                transactions.append(cleaned)

        # -------------------------------------------
        # REMAINING PAGES — data rows only
        # -------------------------------------------
        for page_num in range(1, len(pdf.pages)):
            page = pdf.pages[page_num]
            page_tables = page.extract_tables(MAIN_TABLE_SETTINGS)

            if not page_tables:
                continue

            for table in page_tables:
                if not table or len(table) < 1:
                    continue

                # Detect if the first row is a repeated header
                candidate_header = [
                    normalize_column_name(h) if h else "" for h in table[0]
                ]

                is_header_row = any(col in FIELD_MAPPINGS for col in candidate_header)

                # Skip duplicate page headers
                if is_header_row and candidate_header == global_headers:
                    data_rows = table[1:]
                else:
                    data_rows = table

                # Parse rows
                for raw in data_rows:
                    cleaned = _build_clean_dict(raw, global_headers)
                    if cleaned:
                        transactions.append(cleaned)

    # -----------------------------------------------------------
    # Final validation (enzymes: date fixing, balance checks, etc.)
    # -----------------------------------------------------------
    return calculate_checks(transactions)
