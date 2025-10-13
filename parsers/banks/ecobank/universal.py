import sys
import re
import pdfplumber
from typing import List, Dict
from utils import (
    normalize_column_name,
    FIELD_MAPPINGS,
    normalize_money,
    to_float,
    parse_text_row,
    calculate_checks,
)

# --------- Helpers for light validation / header repair ----------

DATE_RE = re.compile(r"^(\d{2}[-/.]\d{2}[-/.]\d{4}|\d{1,2}-[A-Za-z]{3}-\d{2,4})$")
AMOUNT_RE = re.compile(r"^(?:\d{1,3}(?:,\d{3})*|\d+)\.\d{2}$")


def _looks_date(s: str) -> bool:
    return bool(DATE_RE.match((s or "").strip()))


def _repair_ecobank_headers(headers: List[str]) -> List[str]:
    """
    Ecobank often has an empty header cell between TXN_DATE and REMARKS
    where REFERENCE should be. If we detect that shape, rename the empty
    cell to 'REFERENCE' so row indices align.
    """
    if not headers:
        return headers

    h = headers[:]
    try:
        t_idx = h.index("TXN_DATE")
    except ValueError:
        return h

    expected_tail = all(
        col in h for col in ["REMARKS", "VAL_DATE", "DEBIT", "CREDIT", "BALANCE"]
    )
    if t_idx + 1 < len(h) and expected_tail and (h[t_idx + 1] in ("", None)):
        h[t_idx + 1] = "REFERENCE"

    return h


def parse(path: str) -> List[Dict[str, str]]:
    transactions = []
    global_headers: List[str] | None = None

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                print(f"(ecobank): Processing page {page_num}", file=sys.stderr)

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
                            if len(first_row) <= 2:
                                continue

                        if is_header_row and not global_headers:
                            # Store and repair headers once
                            repaired = _repair_ecobank_headers(normalized_first_row)
                            global_headers = repaired
                            print(
                                f"Stored global headers: {global_headers}",
                                file=sys.stderr,
                            )
                            data_rows = table[1:]
                        elif is_header_row and global_headers:
                            # Repeated headers — treat as header if matching after repair
                            repaired = _repair_ecobank_headers(normalized_first_row)
                            if repaired == global_headers:
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
                                f"(ecobank): No headers found by page {page_num}, skipping table",
                                file=sys.stderr,
                            )
                            continue

                        # Pre-calc indices
                        has_amount = "AMOUNT" in global_headers
                        balance_idx = (
                            global_headers.index("BALANCE")
                            if "BALANCE" in global_headers
                            else -1
                        )
                        ref_idx = (
                            global_headers.index("REFERENCE")
                            if "REFERENCE" in global_headers
                            else None
                        )

                        prev_balance = None

                        for row in data_rows:
                            # ---- Per-row shape alignment ----
                            # Ecobank drops the blank REFERENCE column on continuation pages → rows become 6 cols.
                            # If the header has REFERENCE but this row is shorter by 1, insert '' at REFERENCE index.
                            if ref_idx is not None and len(row) == (
                                len(global_headers) - 1
                            ):
                                row = row[:]  # copy
                                row.insert(ref_idx, "")  # put empty REFERENCE in place
                                # Optional: log once per page if helpful
                                # print(f"(ecobank): inserted missing REFERENCE for a row on page {page_num}", file=sys.stderr)

                            # Pad short rows (should rarely happen after the insert)
                            if len(row) < len(global_headers):
                                row = row[:] + [""] * (len(global_headers) - len(row))

                            # Build dict by header index
                            row_dict = {
                                global_headers[i]: (row[i] if i < len(row) else "")
                                for i in range(len(global_headers))
                            }

                            standardized_row = parse_text_row(row, global_headers)
                            # Extra guard: if TXN_DATE isn't a date but VAL_DATE is, swap them
                            if (
                                standardized_row["TXN_DATE"]
                                and standardized_row["VAL_DATE"]
                            ):
                                if (
                                    not _looks_date(standardized_row["TXN_DATE"])
                                ) and _looks_date(standardized_row["VAL_DATE"]):
                                    (
                                        standardized_row["TXN_DATE"],
                                        standardized_row["VAL_DATE"],
                                    ) = (
                                        standardized_row["VAL_DATE"],
                                        standardized_row["TXN_DATE"],
                                    )

                            # Determine debit/credit
                            if has_amount and balance_idx != -1:
                                amount = to_float(row_dict.get("AMOUNT", ""))
                                current_balance = to_float(row_dict.get("BALANCE", ""))

                                if (
                                    prev_balance is not None
                                    and current_balance is not None
                                ):
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

                                prev_balance = (
                                    current_balance
                                    if current_balance is not None
                                    else prev_balance
                                )
                            else:
                                # Use provided debit/credit columns
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
                    # Text fallback widened to dd-MMM-yyyy as well
                    print(
                        f"(ecobank): No tables found on page {page_num}, attempting text extraction",
                        file=sys.stderr,
                    )

        # Only keep rows that have at least one date
        return calculate_checks(
            [t for t in transactions if t["TXN_DATE"] or t["VAL_DATE"]]
        )

    except Exception as e:
        print(f"Error processing ecobank statement: {e}", file=sys.stderr)
        return []
