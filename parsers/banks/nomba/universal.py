# banks/nomba/universal.py

import re
import sys
import pdfplumber
from typing import List, Dict
from utils import STANDARDIZED_ROW, normalize_date, to_float, calculate_checks


def parse(pdf_path: str) -> List[Dict[str, str]]:
    transactions: List[Dict[str, str]] = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text()
                if not text:
                    continue

                lines = text.split("\n")

                for line in lines:
                    # Detect transaction lines (example: "March 1st 2025, 12:35 AM POS/Card Payment/... + ₦598.20 - ₦47,914,526.13")
                    if not re.search(r"\d{4}", line):
                        continue

                    txn = STANDARDIZED_ROW.copy()

                    # Extract date-time (everything up to first narration token)
                    date_match = re.match(
                        r"^([A-Za-z]+\s+\d{1,2}(st|nd|rd|th)?\s+\d{4},\s+\d{1,2}:\d{2}\s*(AM|PM))",
                        line,
                    )
                    if date_match:
                        raw_date = date_match.group(1)
                        txn["TXN_DATE"] = normalize_date(raw_date)
                        txn["VAL_DATE"] = txn["TXN_DATE"]

                    # Extract amounts
                    credit_match = re.search(r"\+\s*₦([\d,]+\.\d{2})", line)
                    debit_match = re.search(r"-\s*₦([\d,]+\.\d{2})", line)

                    if credit_match:
                        txn["CREDIT"] = f"{to_float(credit_match.group(1)):.2f}"
                    if debit_match:
                        # In Nomba, the second `- ₦` is usually balance; the first could be debit
                        # We’ll split all `- ₦` occurrences
                        minus_parts = re.findall(r"-\s*₦([\d,]+\.\d{2})", line)
                        if len(minus_parts) == 1:
                            # Only one negative → treat as balance, no debit
                            txn["BALANCE"] = f"{to_float(minus_parts[0]):.2f}"
                        elif len(minus_parts) >= 2:
                            # First is debit, last is balance
                            txn["DEBIT"] = f"{to_float(minus_parts[0]):.2f}"
                            txn["BALANCE"] = f"{to_float(minus_parts[-1]):.2f}"

                    # Extract remarks (strip date and amounts)
                    remarks = line
                    if date_match:
                        remarks = remarks[len(date_match.group(0)) :].strip()
                    remarks = re.sub(r"[+-]\s*₦[\d,]+\.\d{2}", "", remarks).strip()
                    txn["REMARKS"] = remarks

                    # Defaults if not found
                    txn["DEBIT"] = txn["DEBIT"] if txn["DEBIT"] != "0.00" else "0.00"
                    txn["CREDIT"] = txn["CREDIT"] if txn["CREDIT"] != "0.00" else "0.00"

                    if txn["TXN_DATE"] and txn["BALANCE"]:
                        transactions.append(txn)

        return calculate_checks(transactions)

    except Exception as e:
        print(f"Error parsing Nomba statement: {e}", file=sys.stderr)
        return []
