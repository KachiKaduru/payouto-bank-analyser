import re
import pdfplumber
from typing import List, Dict

from utils import (
    normalize_date,
    normalize_money,
    calculate_checks,
)

RX_TXN_START = re.compile(r"^(\d{2}-\d{2}-\d{2})\s+(.*)")

RX_TIME_LINE = re.compile(r"^(\d{2}:\d{2}:\d{2})\s*(.*)")

RX_AMOUNT_BAL = re.compile(
    r"([+-])\s*₦?\s*([\d,]+(?:\.\d+)?)\s+₦?\s*([\d,]+(?:\.\d+)?)"
)


def extract_reference(text: str):
    patterns = [
        r"(\d{15,})",  # transaction ids
        r"([A-Z0-9]{8,})",  # reference codes
    ]

    for p in patterns:
        m = re.search(p, text)
        if m:
            return m.group(1)

    return ""


def flush_transaction(buffer):

    if not buffer:
        return None

    full = " ".join(buffer)

    m = RX_TXN_START.search(full)
    if not m:
        return None

    raw_date = m.group(1)

    txn_date = normalize_date(raw_date)

    amt_match = RX_AMOUNT_BAL.search(full)

    if not amt_match:
        return None

    sign, amount, balance = amt_match.groups()

    amount = normalize_money(amount)
    balance = normalize_money(balance)

    narration = full[m.end() : amt_match.start()].strip()

    narration = re.sub(
        r"\d{2}:\d{2}:\d{2}",
        "",
        narration,
    )

    narration = re.sub(r"\s+", " ", narration).strip()

    reference = extract_reference(narration)

    debit = "0.00"
    credit = "0.00"

    if sign == "+":
        credit = amount
    else:
        debit = amount

    return {
        "TXN_DATE": txn_date,
        "VAL_DATE": txn_date,
        "REFERENCE": reference,
        "REMARKS": narration,
        "DEBIT": debit,
        "CREDIT": credit,
        "BALANCE": balance,
    }


def parse(path: str) -> List[Dict]:

    transactions = []
    buffer = []

    with pdfplumber.open(path) as pdf:

        for page in pdf.pages:
            print(f"(firstmonie): Processing page {page.page_number}")
            text = page.extract_text()

            if not text:
                continue
            lines = [l.strip() for l in text.splitlines() if l.strip()]

            for line in lines:
                if any(
                    line.startswith(x)
                    for x in (
                        "Statement",
                        "Store id:",
                        "From date:",
                        "To Date:",
                        "Generated Date:",
                        "Date Narration Amount Balance",
                    )
                ):
                    continue

                # New transaction starts whenever line begins with date
                if RX_TXN_START.match(line):

                    if buffer:

                        txn = flush_transaction(buffer)

                        if txn:
                            transactions.append(txn)

                    buffer = [line]

                else:
                    buffer.append(line)

        if buffer:

            txn = flush_transaction(buffer)

            if txn:
                transactions.append(txn)

    return calculate_checks(transactions)
