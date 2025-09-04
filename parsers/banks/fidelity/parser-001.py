import pdfplumber
import re
import sys
from typing import List, Dict
from utils import normalize_date, to_float, calculate_checks, FIELD_MAPPINGS

# Regex to detect transaction start lines by date formats like: 03-Feb-25 or 03-Feb-2025
DATE_PATTERN = re.compile(r"^\d{2}-[A-Za-z]{3}-\d{2,4}$")


def normalize_column_name(name: str) -> str:
    """
    Matches a column name against FIELD_MAPPINGS to return the standardized header.
    """
    if not name:
        return ""

    name_lower = name.strip().lower()
    for standard_field, aliases in FIELD_MAPPINGS.items():
        for alias in aliases:
            if alias.strip().lower() == name_lower:
                return standard_field
    return name.strip()  # fallback to original if no match


def parse(path: str) -> List[Dict[str, str]]:
    transactions = []
    global_headers = None
    global_header_map = None
    current_row = None

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                print(f"Processing page {page_num}", file=sys.stderr)

                # Attempt to extract tables first
                tables = page.extract_tables(
                    {
                        "vertical_strategy": "lines",
                        "horizontal_strategy": "lines",
                        "snap_tolerance": 3,
                        "join_tolerance": 3,
                        "min_words_vertical": 3,
                        "min_words_horizontal": 1,
                        "text_tolerance": 2,
                    }
                )

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
                                f"No headers found by page {page_num}, skipping table",
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

                            # Merge multiline remarks
                            if "REMARKS" in row_dict:
                                row_dict["REMARKS"] = " ".join(
                                    str(row_dict["REMARKS"]).split()
                                )

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
                                "DEBIT": to_float(row_dict.get("DEBIT", "0.00")),
                                "CREDIT": to_float(row_dict.get("CREDIT", "0.00")),
                                "BALANCE": row_dict.get("BALANCE", "") or "0.00",
                                "Check": "",
                                "Check 2": "",
                            }

                            transactions.append(standardized_row)
                else:
                    # If no tables, fall back to text-based parsing
                    print(
                        f"No tables found on page {page_num}, switching to text mode",
                        file=sys.stderr,
                    )
                    lines = (
                        page.extract_text().split("\n") if page.extract_text() else []
                    )
                    for line in lines:
                        parts = line.split()
                        if not parts:
                            continue

                        # Check if first token is a date (start of new transaction)
                        if DATE_PATTERN.match(parts[0]):
                            # Save previous row if exists
                            if current_row:
                                transactions.append(current_row)
                            # Start new row
                            current_row = make_standard_row(parts)
                        else:
                            # Otherwise, append line to remarks of the current transaction
                            if current_row:
                                current_row["REMARKS"] += " " + line

            # Append any pending row after last page
            if current_row:
                transactions.append(current_row)

        # Final sanity checks & computed fields
        return calculate_checks(
            [t for t in transactions if t["TXN_DATE"] or t["VAL_DATE"]]
        )

    except Exception as e:
        print(f"Error processing statement: {e}", file=sys.stderr)
        return []


def make_standard_row(row: List[str]) -> Dict[str, str]:
    """
    Given a raw row from the PDF, standardize it into the expected transaction dict.
    Assumes columns are in this order:
    [TXN_DATE, VAL_DATE, REFERENCE, REMARKS, DEBIT, CREDIT, BALANCE]
    """
    return {
        "TXN_DATE": normalize_date(row[0]) if len(row) > 0 else "",
        "VAL_DATE": normalize_date(row[1]) if len(row) > 1 else "",
        "REFERENCE": row[2] if len(row) > 2 else "",
        "REMARKS": row[3] if len(row) > 3 else "",
        "DEBIT": to_float(row[-3]) if len(row) >= 3 else 0.00,
        "CREDIT": to_float(row[-2]) if len(row) >= 2 else 0.00,
        "BALANCE": row[-1] if len(row) >= 1 else "0.00",
        "Check": "",
        "Check 2": "",
    }
