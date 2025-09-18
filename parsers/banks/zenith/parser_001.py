import pdfplumber
import re
import sys
from typing import List, Dict
from utils import normalize_date, to_float, calculate_checks, STANDARDIZED_ROW


# Keywords that signal noise (summaries, headers, footers)
SKIP_KEYWORDS = [
    "total debit",
    "total credit",
    "closing balance",
    "period:",
    "date posted",
    "value date",
    "description",
    "debit",
    "credit",
    "balance",
    "account number:",
    "currency:",
    "payment services limited",
]


def is_noise_line(line: str) -> bool:
    """Check if a line is summary/header/footer noise."""
    line_lower = line.lower()
    return any(kw in line_lower for kw in SKIP_KEYWORDS)


def parse(path: str) -> List[Dict[str, str]]:
    transactions: List[Dict[str, str]] = []

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                print(
                    f"(zenith_parser_001): Processing page {page_num}", file=sys.stderr
                )

                text = page.extract_text() or ""
                lines = text.split("\n")

                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    if is_noise_line(line):
                        continue

                    # Handle pure "Opening Balance" line
                    if line.lower().startswith("opening balance"):
                        parts = line.split()
                        if parts and to_float(parts[-1]) != 0.0:
                            opening_balance = to_float(parts[-1])
                            row = STANDARDIZED_ROW.copy()
                            row.update(
                                {
                                    "TXN_DATE": "",
                                    "VAL_DATE": "",
                                    "REFERENCE": "",
                                    "REMARKS": "Opening Balance",
                                    "DEBIT": "0.00",
                                    "CREDIT": "0.00",
                                    "BALANCE": f"{opening_balance:.2f}",
                                    "Check": "TRUE",
                                    "Check 2": "0.00",
                                }
                            )
                            transactions.append(row)
                        continue

                    # Match standard transaction rows
                    match = re.match(
                        r"^(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\s+(.*?)(\d[\d,]*\.\d{2})\s+(\d[\d,]*\.\d{2})\s+(\d[\d,]*\.\d{2})$",
                        line,
                    )
                    if match:
                        txn_date, val_date, desc, debit, credit, balance = (
                            match.groups()
                        )
                        row = STANDARDIZED_ROW.copy()
                        row.update(
                            {
                                "TXN_DATE": normalize_date(txn_date),
                                "VAL_DATE": normalize_date(val_date),
                                "REFERENCE": "",
                                "REMARKS": desc.strip(),
                                "DEBIT": f"{to_float(debit):.2f}",
                                "CREDIT": f"{to_float(credit):.2f}",
                                "BALANCE": f"{to_float(balance):.2f}",
                            }
                        )
                        transactions.append(row)
                    else:
                        # Continuation lines: only if not noise
                        if transactions and not is_noise_line(line):
                            transactions[-1]["REMARKS"] += " " + line.strip()

        return calculate_checks(transactions)

    except Exception as e:
        print(f"Error in zenith parser_001: {e}", file=sys.stderr)
        return []
