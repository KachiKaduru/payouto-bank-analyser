import re
import pdfplumber
from typing import List, Dict

from utils import (
    normalize_date,
    normalize_money,
    calculate_checks,
)

# Regex patterns
RX_TXN_DATE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}")
RX_VAL_DATE = re.compile(r"\d{2}-[A-Z]{3}-\d{4}")
RX_AMOUNT = re.compile(r"[-\d,]+\.\d{2}")


def extract_fields(remarks: str) -> Dict[str, str]:
    date_pattern = re.compile(r"\b\d{2}-[A-Za-z]{3}-\d{4}\b")
    amount_pattern = RX_AMOUNT
    # amount_pattern = re.compile(r"\d[\d,]*\.\d{2}")

    # Work on a copy so we can strip things out
    cleaned = remarks

    # 1. Find first date
    date_match = date_pattern.search(remarks)
    val_date = date_match.group(0) if date_match else ""
    if val_date:
        cleaned = cleaned.replace(val_date, "", 1)

    # 2. Reference = token immediately before date
    reference = ""
    if date_match:
        tokens = remarks[: date_match.start()].strip().split()
        if tokens:
            reference = tokens[-1]
            cleaned = re.sub(rf"\b{re.escape(reference)}\b", "", cleaned, count=1)

    # 3. Amounts
    amounts = amount_pattern.findall(remarks)
    debit = credit = balance = "0.00"
    if len(amounts) > 0:
        balance = amounts[0]
        cleaned = cleaned.replace(balance, "", 1)

    if len(amounts) > 1:
        credit, balance = amounts[0], amounts[1]
        for val in (credit, balance):
            cleaned = cleaned.replace(val, "", 1)

    if len(amounts) > 2:
        debit, credit, balance = amounts[0], amounts[1], amounts[2]
        for val in (debit, credit, balance):
            cleaned = cleaned.replace(val, "", 1)

    # Final clean up of extra spaces
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()

    return {
        "VAL_DATE": val_date,
        "REFERENCE": reference,
        "DEBIT": debit,
        "CREDIT": credit,
        "BALANCE": balance,
        "REMARKS": cleaned,  # new cleaned remarks
    }


def parse(path: str) -> List[Dict[str, str]]:
    transactions: List[Dict[str, str]] = []

    with pdfplumber.open(path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

            buffer = {}
            remarks_parts = []

            for line in lines:
                # Detect start of new transaction
                txn_date = normalize_date(line.split()[0])

                if RX_TXN_DATE.match(line):
                    # flush previous buffer if valid
                    if buffer:
                        transactions.append(buffer)

                        buffer = {}
                        remarks_parts = []

                    buffer["TXN_DATE"] = normalize_date(txn_date)

                    # Start remarks with rest of line
                    remainder = " ".join(line.split()[1:])
                    if remainder:
                        remarks_parts.append(remainder)
                        remainder = " ".join(line.split()[1:])

                        # Extract structured fields from the remainder
                        extracted = extract_fields(remainder)

                        buffer["VAL_DATE"] = (
                            normalize_date(extracted["VAL_DATE"]) or txn_date
                        )
                        buffer["REFERENCE"] = extracted["REFERENCE"] or ""
                        buffer["REMARKS"] = extracted["REMARKS"] or ""

                        if extracted.get("DEBIT"):
                            buffer["DEBIT"] = normalize_money(extracted["DEBIT"])
                        if extracted.get("CREDIT"):
                            buffer["CREDIT"] = normalize_money(extracted["CREDIT"])
                        if extracted.get("BALANCE"):
                            buffer["BALANCE"] = normalize_money(extracted["BALANCE"])

                else:
                    # middle lines → keep as remarks or reference
                    remarks_parts.append(line)

            # flush last txn
            if buffer:
                transactions.append(buffer)

    return calculate_checks(transactions)
