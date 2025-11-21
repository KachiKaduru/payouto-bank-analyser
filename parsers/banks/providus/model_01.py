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
# Helper — converts raw table row into standardized dict
# -----------------------------------------------------
def _build_clean_dict(row: List[str], headers: List[str]) -> Dict[str, str]:
    """
    Normalizes row length, maps columns → utils.parse_text_row,
    and filters out footer/summary rows.
    """

    if not headers:
        return None

    # Fix short rows
    if len(row) < len(headers):
        row = row + [""] * (len(headers) - len(row))

    parsed = parse_text_row(row, headers)

    # Skip summary rows
    txn_date = (parsed.get("TXN_DATE") or "").lower()
    if txn_date.startswith(("total", "closing", "opening", "subtotal")):
        return None

    return parsed


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

        # First row should contain the headers
        header_row = longest_table[0]

        # Normalize headers
        global_headers = [normalize_column_name(h) if h else "" for h in header_row]

        # Ensure they truly contain mapped fields
        if not any(h in FIELD_MAPPINGS for h in global_headers):
            # If headers failed, abort – something unexpected
            return []

        # Process page 1 data rows
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

                # Detect if first row is a header row
                possible_header = [
                    normalize_column_name(h) if h else "" for h in table[0]
                ]

                is_header_row = any(h in FIELD_MAPPINGS for h in possible_header)

                # Skip header row if it matches global headers
                if is_header_row:
                    if possible_header == global_headers:
                        data_rows = table[1:]
                    else:
                        # Unknown header style – treat whole table as data
                        data_rows = table
                else:
                    data_rows = table

                # Parse data rows
                for raw in data_rows:
                    cleaned = _build_clean_dict(raw, global_headers)
                    if cleaned:
                        transactions.append(cleaned)

    # Final validation and debit/credit checks
    return calculate_checks(transactions)
