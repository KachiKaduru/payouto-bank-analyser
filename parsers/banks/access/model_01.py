import re
import sys
import pdfplumber
from typing import List, Dict, Optional

from utils import (
    normalize_date,
    normalize_money,
    calculate_checks,
)

# TXN date in US style: m/d/yyyy or mm/dd/yyyy
RX_TXN_DATE = re.compile(r"^\s*\d{1,2}/\d{1,2}/\d{4}\b")

# Value date like 02-JAN-2025 (allow mixed case month)
RX_VAL_DATE = re.compile(r"\b\d{2}-[A-Za-z]{3}-\d{4}\b")

# Money token like 12,345.67 or -12,345.67
RX_AMOUNT = re.compile(r"-?\d[\d,]*\.\d{2}")


def _to_float(s: str) -> float:
    return float(s.replace(",", "").strip())


def _assign_amounts(amounts: List[str]) -> Dict[str, str]:
    """
    More consistent amount assignment:

    - Balance = LAST money token if present (most reliable)
    - Remaining tokens (before balance):
        * 2 tokens => debit, credit (in order)
        * 1 token  => decide debit vs credit by sign
        * 0 tokens => none
    """
    debit = credit = "0.00"
    balance = "0.00"

    if not amounts:
        return {"DEBIT": debit, "CREDIT": credit, "BALANCE": balance}

    # Balance is safest as the last amount
    balance = amounts[-1]
    rest = amounts[:-1]

    if len(rest) >= 2:
        debit = rest[0]
        credit = rest[1]
    elif len(rest) == 1:
        amt = rest[0]
        try:
            v = _to_float(amt)
            if v < 0:
                # treat negative as debit; store as positive debit value
                debit = f"{abs(v):.2f}"
                credit = "0.00"
            else:
                credit = f"{v:.2f}"
                debit = "0.00"
        except Exception:
            # fallback: keep as credit if parsing fails
            credit = amt

    return {"DEBIT": debit, "CREDIT": credit, "BALANCE": balance}


def extract_fields(remarks: str) -> Dict[str, str]:
    """
    Extract VAL_DATE, REFERENCE, DEBIT/CREDIT/BALANCE from a blob of remarks text,
    and return the leftover as cleaned REMARKS.
    """
    cleaned = remarks

    # 1) Value date (first occurrence)
    date_match = RX_VAL_DATE.search(remarks)
    val_date = date_match.group(0) if date_match else ""
    if val_date:
        cleaned = cleaned.replace(val_date, "", 1)

    # 2) Reference = token immediately before that value date
    reference = ""
    if date_match:
        before = remarks[: date_match.start()].strip()
        tokens = before.split()
        if tokens:
            reference = tokens[-1]
            cleaned = re.sub(rf"\b{re.escape(reference)}\b", "", cleaned, count=1)

    # 3) Amounts (use consistent assignment)
    amounts = RX_AMOUNT.findall(remarks)
    assigned = _assign_amounts(amounts)

    # Remove extracted amounts from cleaned (once each)
    # Remove balance first (usually easiest), then others
    for val in [assigned["BALANCE"], assigned["DEBIT"], assigned["CREDIT"]]:
        if val and val != "0.00":
            cleaned = cleaned.replace(val, "", 1)

    # Final cleanup
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()

    return {
        "VAL_DATE": val_date,
        "REFERENCE": reference,
        "DEBIT": assigned["DEBIT"],
        "CREDIT": assigned["CREDIT"],
        "BALANCE": assigned["BALANCE"],
        "REMARKS": cleaned,
    }


def _flush_transaction(
    buffer: Dict[str, str], remarks_parts: List[str]
) -> Optional[Dict[str, str]]:
    """
    Turn the accumulated buffer + remarks_parts into a final transaction dict.
    Runs extract_fields ONCE here (the key fix for wrapped/multi-page rows).
    """
    if not buffer:
        return None

    # Combine all continuation lines into one blob
    blob = " ".join([p for p in remarks_parts if p]).strip()

    extracted = (
        extract_fields(blob)
        if blob
        else {
            "VAL_DATE": "",
            "REFERENCE": "",
            "REMARKS": "",
            "DEBIT": "0.00",
            "CREDIT": "0.00",
            "BALANCE": "0.00",
        }
    )

    txn_date = buffer.get("TXN_DATE", "")

    # Fill fields (fallback VAL_DATE to TXN_DATE if missing)
    buffer["VAL_DATE"] = normalize_date(extracted["VAL_DATE"]) or txn_date
    buffer["REFERENCE"] = extracted["REFERENCE"] or ""
    buffer["REMARKS"] = extracted["REMARKS"] or ""

    buffer["DEBIT"] = normalize_money(extracted.get("DEBIT", "0.00"))
    buffer["CREDIT"] = normalize_money(extracted.get("CREDIT", "0.00"))
    buffer["BALANCE"] = normalize_money(extracted.get("BALANCE", "0.00"))

    return buffer


def parse(path: str) -> List[Dict[str, str]]:
    transactions: List[Dict[str, str]] = []

    # IMPORTANT: keep these OUTSIDE the page loop so a txn can span pages
    buffer: Dict[str, str] = {}
    remarks_parts: List[str] = []

    with pdfplumber.open(path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            print(f"(access:001): Processing page {page_no}", file=sys.stderr)

            text = page.extract_text() or ""
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

            for line in lines:
                # Start of a new transaction row?
                if RX_TXN_DATE.match(line):
                    # Flush previous txn first
                    flushed = _flush_transaction(buffer, remarks_parts)
                    if flushed:
                        transactions.append(flushed)

                    # Start new txn buffer
                    buffer = {}
                    remarks_parts = []

                    parts = line.split()
                    raw_txn_date = parts[0]  # safe now: we know it matches
                    txn_date = normalize_date(raw_txn_date)

                    buffer["TXN_DATE"] = txn_date

                    # Everything after TXN_DATE is part of the blob to extract from
                    remainder = " ".join(parts[1:]).strip()
                    if remainder:
                        remarks_parts.append(remainder)

                else:
                    # Continuation line: belongs to current transaction (if any)
                    if buffer:
                        remarks_parts.append(line)

            # do NOT flush at end of page; allow txn to continue to next page

    # Flush last txn after all pages
    flushed = _flush_transaction(buffer, remarks_parts)
    if flushed:
        transactions.append(flushed)

    return calculate_checks(transactions)
