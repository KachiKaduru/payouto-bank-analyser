import pdfplumber
import re
import sys
from typing import List, Dict
from utils import *

# Regex for transaction start in text mode (e.g., "03-Feb-25")
DATE_PATTERN = re.compile(r"^\d{2}-[A-Za-z]{3}-\d{2,4}")


def parse(path: str) -> List[Dict[str, str]]:
    transactions = []
    global_headers = None
    prev_balance = None
    current_row = None  # For text fallback

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                print(f"(fidelity parser): Processing page {page_num}", file=sys.stderr)

                # Optimized table settings for Fidelity (tighter tolerances for text alignment)
                table_settings = {
                    "vertical_strategy": "text",  # Better for Fidelity's text-based columns
                    "horizontal_strategy": "lines",  # Detect horizontal lines for rows
                    "snap_tolerance": 4,  # Slightly increased to handle spacing
                    "join_tolerance": 4,  # Merge close lines
                    "min_words_vertical": 2,  # Require words for columns
                    "min_words_horizontal": 1,  # Allow short rows
                    "text_tolerance": 1,  # Precise text alignment
                    # "keep_blank_chars": False,  # Ignore blanks
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
                                f"No headers found by page {page_num}, skipping table",
                                file=sys.stderr,
                            )
                            continue

                        # Process rows with multi-line merging
                        i = 0
                        while i < len(data_rows):
                            row = data_rows[i]
                            if len(row) < len(global_headers):
                                row.extend([""] * (len(global_headers) - len(row)))

                            # Merge multi-line remarks (if next row has no date in first cell)
                            remarks = (
                                row[global_headers.index("REMARKS")]
                                if "REMARKS" in global_headers
                                else ""
                            )
                            while i + 1 < len(data_rows) and not DATE_PATTERN.match(
                                data_rows[i + 1][0]
                            ):
                                next_row = data_rows[i + 1]
                                remarks += " " + (
                                    next_row[global_headers.index("REMARKS")]
                                    if "REMARKS" in global_headers
                                    else " ".join(next_row)
                                )
                                i += 1  # Skip the merged row

                            row_dict = {
                                global_headers[j]: row[j] if j < len(row) else ""
                                for j in range(len(global_headers))
                            }
                            row_dict["REMARKS"] = (
                                remarks.strip()
                            )  # Update with merged remarks

                            # Standardize row
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
                                "DEBIT": row_dict.get("DEBIT", "0.00"),
                                "CREDIT": row_dict.get("CREDIT", "0.00"),
                                "BALANCE": row_dict.get("BALANCE", ""),
                                "Check": "",
                                "Check 2": "",
                            }

                            # Infer debit/credit from balance change if needed
                            current_balance = to_float(standardized_row["BALANCE"])
                            debit = to_float(standardized_row["DEBIT"])
                            credit = to_float(standardized_row["CREDIT"])
                            if prev_balance is not None and debit == 0 and credit == 0:
                                if current_balance < prev_balance:
                                    standardized_row["DEBIT"] = (
                                        f"{abs(current_balance - prev_balance):.2f}"
                                    )
                                    standardized_row["CREDIT"] = "0.00"
                                else:
                                    standardized_row["CREDIT"] = (
                                        f"{abs(current_balance - prev_balance):.2f}"
                                    )
                                    standardized_row["DEBIT"] = "0.00"
                            prev_balance = current_balance

                            transactions.append(standardized_row)
                            i += 1  # Move to next row

                else:
                    # Text fallback with improved multi-line handling
                    print(
                        f"No tables found on page {page_num}, using text fallback",
                        file=sys.stderr,
                    )
                    text = page.extract_text()
                    if text:
                        lines = text.split("\n")
                        for line in lines:
                            line = line.strip()
                            if not line:
                                continue
                            if DATE_PATTERN.match(line):
                                if current_row:
                                    transactions.append(current_row)
                                parts = re.split(
                                    r"\s{2,}", line
                                )  # Split on multiple spaces
                                current_row = make_standard_row(parts)
                            else:
                                if current_row:
                                    current_row["REMARKS"] += " " + line

            # Add last row if pending
            if current_row:
                transactions.append(current_row)

        return calculate_checks(
            [t for t in transactions if t["TXN_DATE"] or t["VAL_DATE"]]
        )

    except Exception as e:
        print(f"Error processing Fidelity PDF: {e}", file=sys.stderr)
        return []


def make_standard_row(parts: List[str]) -> Dict[str, str]:
    """
    Standardize a raw text row into the transaction dict.
    Assumes order: TXN_DATE, VAL_DATE, REFERENCE, REMARKS (multi-line), DEBIT, CREDIT, BALANCE
    """
    row = {
        "TXN_DATE": normalize_date(parts[0]) if len(parts) > 0 else "",
        "VAL_DATE": normalize_date(parts[1]) if len(parts) > 1 else "",
        "REFERENCE": parts[2] if len(parts) > 2 else "",
        "REMARKS": " ".join(parts[3:-3]) if len(parts) > 5 else "",
        "DEBIT": to_float(parts[-3] if len(parts) > 2 else "0.00"),
        "CREDIT": to_float(parts[-2] if len(parts) > 1 else "0.00"),
        "BALANCE": parts[-1] if len(parts) > 0 else "0.00",
        "Check": "",
        "Check 2": "",
    }
    return row
