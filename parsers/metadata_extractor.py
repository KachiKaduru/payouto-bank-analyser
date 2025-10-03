import re
import pdfplumber
from typing import Dict, Optional

RX_MONEY = re.compile(r"₦?\s?[-\d,]+\.\d{2}")
RX_DATE_YMD = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
RX_DATE_DMY = re.compile(r"\b\d{2}\s?[A-Za-z]{3}\s?\d{4}\b")  # 01 Mar 2025
RX_DATE_SIMPLE = re.compile(r"\b\d{2}[-/]\d{2}[-/]\d{4}\b")


def _first_match(text: str, labels: list[str], rx: re.Pattern) -> Optional[str]:
    for label in labels:
        # capture after the label (same line or next)
        m = re.search(rf"{re.escape(label)}\s*[:\n]?\s*(.+)", text, re.IGNORECASE)
        if m:
            candidate_line = m.group(1).splitlines()[0].strip()
            mm = rx.search(candidate_line)
            if mm:
                return mm.group(0)
            # sometimes the value sits exactly without needing rx
            if candidate_line:
                return candidate_line
    return None


def _first_money_after(text: str, labels: list[str]) -> Optional[str]:
    for label in labels:
        m = re.search(rf"{re.escape(label)}\s*[:\n]?\s*(.+)", text, re.IGNORECASE)
        if m:
            candidate_line = m.group(1).splitlines()[0]
            mm = RX_MONEY.search(candidate_line)
            if mm:
                return mm.group(0)
    return None


def _first_plain_after(text: str, labels: list[str]) -> Optional[str]:
    for label in labels:
        m = re.search(rf"{re.escape(label)}\s*[:\n]?\s*(.+)", text, re.IGNORECASE)
        if m:
            return m.group(1).splitlines()[0].strip()
    return None


def extract_statement_meta(path: str) -> Dict[str, Optional[str]]:
    meta = {
        "bank": None,
        "account_name": None,
        "account_number": None,
        "start_date": None,
        "end_date": None,
        "opening_balance": None,
        "closing_balance": None,
        "current_balance": None,
        "date_printed": None,
    }

    with pdfplumber.open(path) as pdf:
        if not pdf.pages:
            return meta
        first = pdf.pages[0]
        text = (first.extract_text() or "").strip()

    T = text  # shorthand

    # Bank guess (simple heuristics based on keywords seen in samples)
    if "OPay" in T or "OWealth" in T or "Account Statement" in T and "Wallet" in T:
        meta["bank"] = "OPay"
    if "Palmpay" in T or "PalmPay" in T:
        meta["bank"] = "PalmPay"

    # Account name/number
    meta["account_name"] = _first_plain_after(T, ["Account Name", "Name"])
    meta["account_number"] = _first_plain_after(
        T, ["Account Number", "Acct No", "Account No"]
    )

    # Dates
    # Prefer labeled fields; fall back to the first few date-looking tokens
    meta["start_date"] = _first_match(
        T, ["Start Date", "From"], RX_DATE_DMY
    ) or _first_match(T, ["Start Date", "From"], RX_DATE_SIMPLE)
    meta["end_date"] = _first_match(T, ["End Date", "To"], RX_DATE_DMY) or _first_match(
        T, ["End Date", "To"], RX_DATE_SIMPLE
    )
    meta["date_printed"] = _first_match(
        T, ["Date Printed", "Print Time", "Printed"], RX_DATE_DMY
    ) or _first_match(T, ["Date Printed", "Print Time", "Printed"], RX_DATE_SIMPLE)

    # Balances
    meta["opening_balance"] = _first_money_after(T, ["Opening Balance", "Opening Bal"])
    meta["closing_balance"] = _first_money_after(T, ["Closing Balance", "Closing Bal"])
    meta["current_balance"] = _first_money_after(T, ["Current Balance", "Current Bal"])

    return meta
