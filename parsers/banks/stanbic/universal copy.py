import sys
import re
import pdfplumber
from typing import List, Dict

from utils import (
    normalize_date,
    to_float,
    parse_text_row,
    calculate_checks,
)

DATE_LINE = re.compile(r"^\d{2}[-/]\d{2}[-/]\d{4}\s+\d{2}[-/]\d{2}[-/]\d{4}")

HEADERS = ["TXN_DATE", "VAL_DATE", "REMARKS", "DEBIT", "CREDIT", "BALANCE"]


def parse(path: str) -> List[Dict[str, str]]:
    transactions: List[Dict[str, str]] = []
    prev_balance: float | None = None
    buffer_remarks: List[str] = []

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                print(f"(stanbic): Processing page {page_num}", file=sys.stderr)

                lines = [
                    " ".join(w["text"] for w in sorted(ws, key=lambda x: x["x0"]))
                    for _, ws in sorted(
                        {
                            round(w["top"], 1): []
                            for w in page.extract_words(
                                x_tolerance=2, y_tolerance=3, keep_blank_chars=True
                            )
                        }.items()
                    )
                ]

                # actually group by y properly
                word_lines = {}
                for w in page.extract_words(
                    x_tolerance=2, y_tolerance=3, keep_blank_chars=True
                ):
                    word_lines.setdefault(round(w["top"], 1), []).append(w)
                lines = [
                    " ".join(w["text"] for w in sorted(ws, key=lambda x: x["x0"]))
                    for y, ws in sorted(word_lines.items())
                ]

                for line in lines:
                    line = line.strip()
                    if not line:
                        continue

                    if DATE_LINE.match(line):
                        # finalize the remarks collected so far
                        remarks = " ".join(buffer_remarks).strip()
                        buffer_remarks = []

                        parts = line.split()
                        if len(parts) < 4:
                            print(
                                f"(stanbic): Could not parse line: {line}",
                                file=sys.stderr,
                            )
                            continue

                        txn_date = normalize_date(parts[0])
                        val_date = normalize_date(parts[1])
                        # last two are amount + balance
                        amount_str = parts[-2]
                        balance_str = parts[-1]

                        amount = to_float(amount_str)
                        balance = to_float(balance_str)

                        debit, credit = "0.00", "0.00"
                        if prev_balance is not None:
                            if balance < prev_balance:
                                debit = f"{abs(amount):.2f}"
                            else:
                                credit = f"{abs(amount):.2f}"
                        # for very first row, we don’t know → put amount in debit by default
                        else:
                            debit = f"{abs(amount):.2f}"

                        row = [
                            txn_date,
                            val_date,
                            remarks,
                            debit,
                            credit,
                            f"{balance:.2f}",
                        ]
                        transactions.append(parse_text_row(row, HEADERS))
                        prev_balance = balance
                    else:
                        # part of remarks
                        buffer_remarks.append(line)

        return calculate_checks(transactions)

    except Exception as e:
        print(f"Error processing Stanbic statement: {e}", file=sys.stderr)
        return []
