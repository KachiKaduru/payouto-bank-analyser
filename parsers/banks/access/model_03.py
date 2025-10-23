# banks/access/parser_003.py
import sys
import pdfplumber
from typing import List, Dict
from utils import (
    MAIN_TABLE_SETTINGS,
    normalize_column_name,
    parse_text_row,
    merge_and_drop_year_artifacts,
    calculate_checks,
)

EXPECTED_ORDER = [
    "TXN_DATE",
    "REMARKS",
    "REFERENCE",
    "VAL_DATE",
    "DEBIT",
    "CREDIT",
    "BALANCE",
]


def _looks_like_main_header(row: List[str]) -> bool:
    """
    True if a row looks like the big transaction header row:
    e.g. ['S/NO','DATE','TRANSACTION DETAILS','REF. NO','VALUE DATE','WITHDRAWAL','LODGEMENT','BALANCE']
    We only need the mappable ones to be present after normalization.
    """
    norm = [normalize_column_name(c or "") for c in row]
    hits = set(norm) & {
        "TXN_DATE",
        "VAL_DATE",
        "REFERENCE",
        "REMARKS",
        "DEBIT",
        "CREDIT",
        "BALANCE",
    }
    return len(hits) >= 4  # robust to OCR tweaks


def _build_header_from_row(row: List[str]) -> List[str]:
    """
    Normalize a found header row into our canonical order.
    Access tables are usually:
      DATE | TRANSACTION DETAILS | REF. NO | VALUE DATE | WITHDRAWAL | LODGEMENT | BALANCE
    We map those to EXPECTED_ORDER. Extra columns (like S/NO) are dropped.
    """
    norm = [normalize_column_name(c or "") for c in row]
    out: List[str] = []
    for key in [
        "TXN_DATE",
        "REMARKS",
        "REFERENCE",
        "VAL_DATE",
        "DEBIT",
        "CREDIT",
        "BALANCE",
    ]:
        # Find the first index in normalized row that matches this canonical key
        # (It’s ok if some are missing on weird pages; we’ll pad rows later.)
        try:
            idx = norm.index(key)
            out.append(key)
        except ValueError:
            out.append(key)  # keep canonical placeholder; rows will be padded
    return out


def _infer_header_from_first_data_row(row: List[str]) -> List[str]:
    """
    Safety net: if page 1 header is missed but we see a 7+col data-like row,
    assume the standard Access order.
    """
    if len(row) >= 7:
        return EXPECTED_ORDER.copy()
    return []


def parse(path: str) -> List[Dict[str, str]]:
    txns: List[Dict[str, str]] = []
    global_headers: List[str] = []

    with pdfplumber.open(path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            print(
                f"(access parser_003): 📄 Processing page {page_num}", file=sys.stderr
            )
            tables = page.extract_tables(MAIN_TABLE_SETTINGS) or []

            if not tables:
                print("No tables found; skipping page", file=sys.stderr)
                continue

            for ti, table in enumerate(tables):
                if not table or len(table) < 1:
                    continue

                first_row = table[0]
                # Skip tiny/summary tables (e.g., the 2-column summary block)
                if len(first_row) <= 3 and not global_headers:
                    continue

                # 1) Try to lock the global header if we don’t have it yet
                if not global_headers:
                    if _looks_like_main_header(first_row):
                        global_headers = _build_header_from_row(first_row)
                        print(
                            f"   ↳ Found main header on p{page_num}, t{ti}: {global_headers}",
                            file=sys.stderr,
                        )
                        data_rows = table[1:]  # skip header row
                    else:
                        # Didn’t look like a header; maybe this is already a data table.
                        guessed = _infer_header_from_first_data_row(first_row)
                        if guessed:
                            global_headers = guessed
                            print(
                                f"   ↳ Guessed header from data on p{page_num}, t{ti}: {global_headers}",
                                file=sys.stderr,
                            )
                            data_rows = table  # include first row as data
                        else:
                            # Not usable for transactions; move on
                            continue
                else:
                    # We already have headers:
                    # If the current table’s first row equals headers (repeated header), drop it.
                    norm_first = [normalize_column_name(c or "") for c in first_row]
                    if set(norm_first) & {
                        "TXN_DATE",
                        "VAL_DATE",
                        "REFERENCE",
                        "REMARKS",
                        "DEBIT",
                        "CREDIT",
                        "BALANCE",
                    }:
                        # looks like a header-ish row; if it’s very close, skip it
                        data_rows = table[1:]
                    else:
                        data_rows = table

                # 2) Convert table rows → standardized dicts
                for row in data_rows:
                    # pad row to header length
                    if len(row) < len(global_headers):
                        row = row + [""] * (len(global_headers) - len(row))
                    # Use the shared utility that:
                    #  - joins date fragments like "01-Apr-\n2025"
                    #  - normalizes dates/money
                    #  - maps columns by header names
                    row_dict = parse_text_row(row, global_headers)

                    # Drop rows that are obviously not transactions (completely empty)
                    if not any(
                        [
                            row_dict.get("TXN_DATE"),
                            row_dict.get("VAL_DATE"),
                            row_dict.get("DEBIT"),
                            row_dict.get("CREDIT"),
                            row_dict.get("BALANCE"),
                            row_dict.get("REMARKS"),
                        ]
                    ):
                        continue

                    txns.append(row_dict)

    # 3) Merge/remove page-break “year” artifacts and re-normalize defensively
    txns = merge_and_drop_year_artifacts(txns)

    # 4) Recompute row-by-row checks using balances
    txns = calculate_checks(txns)

    return txns
