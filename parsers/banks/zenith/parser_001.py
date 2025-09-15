import pdfplumber
import re
import sys
from typing import List, Dict
from utils import (
    normalize_date,
    normalize_column_name,
    calculate_checks,
    to_float,
    FIELD_MAPPINGS,
    STANDARDIZED_ROW,
)


def parse(path: str) -> List[Dict[str, str]]:
    """
    Parser for Zenith Bank Variant 002: Multi-line description table structure.
    - Headers: DATE POSTED, VALUE DATE, DESCRIPTION (multi-line), DEBIT, CREDIT, BALANCE.
    - Uses extract_text() for robust handling of multi-line descriptions and indented layout.
    - Parses line-by-line: Identifies date lines for TXN_DATE/VAL_DATE, collects description lines,
      then extracts DEBIT/CREDIT/BALANCE from amount lines.
    - Skips summary/header sections; focuses on transaction blocks.
    - Integrates with utils for normalization and check calculation.
    """
    transactions = []
    in_table = False
    current_txn = {}
    desc_lines = []
    prev_balance = None

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                print(
                    f"(zenith parser_002): Processing page {page_num}", file=sys.stderr
                )

                # First, try extract_tables() with tuned settings for this variant
                table_settings = {
                    "vertical_strategy": "lines",  # Zenith tables have clear lines
                    "horizontal_strategy": "lines",
                    "snap_tolerance": 3,
                    "join_tolerance": 3,
                    "min_words_vertical": 3,
                    "min_words_horizontal": 1,
                    "text_tolerance": 2,  # Higher for multi-line desc
                }
                tables = page.extract_tables(table_settings)

                if tables and len(tables) > 0:
                    print(
                        f"(zenith parser_002): Found {len(tables)} table(s) on page {page_num}, attempting table parse",
                        file=sys.stderr,
                    )
                    for table in tables:
                        if not table or len(table) < 2:
                            continue

                        # Assume first row is headers
                        headers = [
                            normalize_column_name(str(cell).strip()) if cell else ""
                            for cell in table[0]
                        ]
                        if "date posted" not in headers and "value date" not in headers:
                            continue  # Not our table

                        # Map to standard fields
                        header_map = {
                            "date posted": "TXN_DATE",
                            "value date": "VAL_DATE",
                            "description": "REMARKS",
                            "debit": "DEBIT",
                            "credit": "CREDIT",
                            "balance": "BALANCE",
                        }
                        standard_headers = [
                            header_map.get(h.lower(), h) for h in headers
                        ]

                        for row_idx, row in enumerate(table[1:], 1):
                            if len(row) < len(standard_headers):
                                row += [""] * (len(standard_headers) - len(row))

                            row_data = [
                                str(cell).strip() if cell else "" for cell in row
                            ]
                            row_dict = {
                                standard_headers[i]: row_data[i]
                                for i in range(len(standard_headers))
                            }

                            # Handle multi-line desc: Join if needed (pdfplumber may split)
                            if "REMARKS" in row_dict and len(row_dict["REMARKS"]) > 0:
                                # If desc spans, but in table it's usually single cell
                                pass

                            standardized_row = STANDARDIZED_ROW.copy()
                            standardized_row.update(
                                {
                                    "TXN_DATE": normalize_date(
                                        row_dict.get("TXN_DATE", "")
                                    ),
                                    "VAL_DATE": normalize_date(
                                        row_dict.get("VAL_DATE", "")
                                    ),
                                    "REFERENCE": "",  # Often part of desc; extract if needed
                                    "REMARKS": row_dict.get("REMARKS", ""),
                                    "DEBIT": row_dict.get("DEBIT", "0.00"),
                                    "CREDIT": row_dict.get("CREDIT", "0.00"),
                                    "BALANCE": row_dict.get("BALANCE", ""),
                                }
                            )

                            # Quick balance check
                            current_balance = to_float(standardized_row["BALANCE"])
                            if prev_balance is not None:
                                expected = round(
                                    prev_balance
                                    - to_float(standardized_row["DEBIT"])
                                    + to_float(standardized_row["CREDIT"]),
                                    2,
                                )
                                if abs(expected - current_balance) > 0.01:
                                    print(
                                        f"(zenith parser_002): Balance mismatch on row {row_idx}: expected {expected}, got {current_balance}",
                                        file=sys.stderr,
                                    )
                            prev_balance = current_balance

                            if (
                                standardized_row["TXN_DATE"]
                                or standardized_row["VAL_DATE"]
                            ):
                                transactions.append(standardized_row)
                        in_table = True
                        break  # Assume one main table per page
                else:
                    # Fallback to extract_text() for multi-line handling
                    print(
                        f"(zenith parser_002): No tables detected on page {page_num}, using text extraction",
                        file=sys.stderr,
                    )
                    text = page.extract_text()
                    if not text:
                        continue

                    lines = [line.strip() for line in text.split("\n") if line.strip()]

                    i = 0
                    while i < len(lines):
                        line = lines[i]

                        # Detect table start (headers)
                        if (
                            not in_table
                            and "DATE POSTED" in line
                            and "VALUE DATE" in lines[i + 1]
                            if i + 1 < len(lines)
                            else False
                        ):
                            print(
                                f"(zenith parser_002): Detected table headers on page {page_num}",
                                file=sys.stderr,
                            )
                            in_table = True
                            i += 5  # Skip headers (DESCRIPTION, DEBIT, etc.)
                            continue

                        # Skip non-transaction lines (account info, totals)
                        if (
                            re.match(r"^\d{3}[A-Z\s]+ROAD", line)
                            or "Account Number:" in line
                            or "Opening Balance:" in line
                            or "Total Debit:" in line
                        ):
                            i += 1
                            continue

                        # Detect DATE POSTED (indented date)
                        date_posted_match = re.match(r"^\s*(\d{2}/\d{2}/\d{4})$", line)
                        if date_posted_match and in_table:
                            if current_txn:  # Save previous
                                if current_txn.get("TXN_DATE"):
                                    transactions.append(current_txn)

                                # Update prev_balance for check
                                prev_balance = to_float(
                                    current_txn.get("BALANCE", "0.00")
                                )

                            current_txn = STANDARDIZED_ROW.copy()
                            current_txn["TXN_DATE"] = normalize_date(
                                date_posted_match.group(1)
                            )
                            i += 1

                            # Next line: VALUE DATE
                            if i < len(lines):
                                val_date_match = re.match(
                                    r"^\s*(\d{2}/\d{2}/\d{4})$", lines[i]
                                )
                                if val_date_match:
                                    current_txn["VAL_DATE"] = normalize_date(
                                        val_date_match.group(1)
                                    )
                                    i += 1

                            # Collect description lines until amount
                            desc_lines = []
                            while (
                                i < len(lines)
                                and not re.match(r"^\s*[\d,]+\.?\d*\s*$", lines[i])
                                and not re.match(r"^\s*(\d{2}/\d{2}/\d{4})$", lines[i])
                            ):
                                if lines[i] and not lines[i].startswith(
                                    "Opening Balance"
                                ):
                                    desc_lines.append(lines[i])
                                i += 1

                            current_txn["REMARKS"] = " ".join(desc_lines).strip()
                            current_txn["REFERENCE"] = re.search(
                                r"(\d{10,})", current_txn["REMARKS"]
                            )  # Extract ref if numeric

                            # Now parse amounts: Next 3 lines: DEBIT, CREDIT, BALANCE
                            if i < len(lines):
                                debit_match = re.match(r"^\s*([\d,]+\.?\d*)$", lines[i])
                                if debit_match:
                                    current_txn["DEBIT"] = (
                                        f"{to_float(debit_match.group(1)):.2f}"
                                    )
                                    i += 1

                                if i < len(lines):
                                    credit_match = re.match(
                                        r"^\s*([\d,]+\.?\d*)$", lines[i]
                                    )
                                    if credit_match:
                                        current_txn["CREDIT"] = (
                                            f"{to_float(credit_match.group(1)):.2f}"
                                        )
                                        i += 1

                                    if i < len(lines):
                                        balance_match = re.match(
                                            r"^\s*([\d,]+\.?\d*)$", lines[i]
                                        )
                                        if balance_match:
                                            current_txn["BALANCE"] = (
                                                f"{to_float(balance_match.group(1)):.2f}"
                                            )
                                            i += 1

                            # Quick validation
                            if not current_txn.get("TXN_DATE"):
                                current_txn = {}
                                continue

                            continue  # Next transaction

                        i += 1

                # Reset for next page if in table
                if in_table and page_num % 2 == 0:  # Assume even pages continue table
                    pass
                else:
                    in_table = False

        # Add last transaction if pending
        if current_txn and current_txn.get("TXN_DATE"):
            transactions.append(current_txn)

        # Filter valid and calculate checks
        valid_transactions = [t for t in transactions if t["TXN_DATE"] or t["VAL_DATE"]]
        result = calculate_checks(valid_transactions)
        print(
            f"(zenith parser_002): Parsed {len(result)} transactions successfully",
            file=sys.stderr,
        )
        return result

    except Exception as e:
        print(f"(zenith parser_002): Parsing error: {e}", file=sys.stderr)
        return []
