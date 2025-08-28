import pdfplumber
import re
import sys
from typing import List, Dict
from utils import *


def parse(path: str) -> List[Dict[str, str]]:
    transactions = []
    global_headers = None

    try:
        with pdfplumber.open(path) as pdf:
            full_text = ""
            for page_num, page in enumerate(pdf.pages, 1):
                print(f"(access parser): Processing page {page_num}", file=sys.stderr)
                text = page.extract_text()
                if text:
                    full_text += text + "\n"

            # Split the full text into lines
            lines = full_text.split("\n")

            # Find the headers
            for i, line in enumerate(lines):
                normalized_line = normalize_column_name(line.lower())
                if "posted date" in normalized_line or "txn date" in normalized_line:
                    # Assume headers are in this line or next
                    header_line = line.strip()
                    global_headers = re.split(
                        r"\s{2,}", header_line
                    )  # Split on multiple spaces
                    global_headers = [
                        normalize_column_name(h) for h in global_headers if h
                    ]
                    print(f"Detected headers: {global_headers}", file=sys.stderr)
                    start_line = i + 1  # Start transactions after headers
                    break

            if not global_headers:
                print(
                    "(access parser): No headers found, using default", file=sys.stderr
                )
                global_headers = [
                    "TXN_DATE",
                    "VAL_DATE",
                    "REMARKS",
                    "DEBIT",
                    "CREDIT",
                    "BALANCE",
                ]

            # Parse transactions from lines after headers
            current_row = []
            for line in lines[start_line:]:
                line = line.strip()
                if not line:
                    continue

                # Check if line starts with a date pattern (new row)
                if re.match(r"^\d{2}-[A-Z]{3}-\d{2}", line):
                    if current_row:
                        # Process previous row
                        transactions.append(
                            process_row(" ".join(current_row), global_headers)
                        )
                    current_row = [line]
                else:
                    # Append to current row (multi-line description)
                    current_row.append(line)

            # Process the last row
            if current_row:
                transactions.append(process_row(" ".join(current_row), global_headers))

        return calculate_checks(
            [t for t in transactions if t["TXN_DATE"] or t["VAL_DATE"]]
        )

    except Exception as e:
        print(f"Error processing Access Bank PDF: {e}", file=sys.stderr)
        return []


def process_row(row_str: str, headers: List[str]) -> Dict[str, str]:
    # Split the row string into fields
    # Pattern: date1 date2 description debit credit balance
    # Debit/credit: one is number, other is '-'
    # Use regex to extract
    date_pattern = r"(\d{2}-[A-Z]{3}-\d{2})\s+(\d{2}-[A-Z]{3}-\d{2})\s+(.*?)(\s+([\d,]+.\d{2}|-)\s+([\d,]+.\d{2}|-)\s+([\d,]+.\d{2}))?$"
    match = re.match(date_pattern, row_str)
    if match:
        txn_date = match.group(1)
        val_date = match.group(2)
        remarks = match.group(3).strip()
        debit = match.group(5) if match.group(5) and match.group(5) != "-" else "0.00"
        credit = match.group(6) if match.group(6) and match.group(6) != "-" else "0.00"
        balance = match.group(7) if match.group(7) else ""
    else:
        # Fallback splitting
        parts = re.split(r"\s{2,}", row_str.strip())
        txn_date = parts[0] if len(parts) > 0 else ""
        val_date = parts[1] if len(parts) > 1 else ""
        remarks = " ".join(parts[2:-3]) if len(parts) > 5 else ""
        debit = parts[-3] if len(parts) > 2 else "0.00"
        credit = parts[-2] if len(parts) > 1 else "0.00"
        balance = parts[-1] if len(parts) > 0 else ""

    standardized_row = {
        "TXN_DATE": normalize_date(txn_date),
        "VAL_DATE": normalize_date(val_date),
        "REFERENCE": "",  # Not in this PDF, can extract from remarks if needed
        "REMARKS": remarks,
        "DEBIT": debit.replace(",", "") if debit != "-" else "0.00",
        "CREDIT": credit.replace(",", "") if credit != "-" else "0.00",
        "BALANCE": balance.replace(",", ""),
        "Check": "",
        "Check 2": "",
    }

    return standardized_row
