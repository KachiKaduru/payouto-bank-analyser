# banks/fcmb/parser_001.py
import sys
import re
import pdfplumber
from typing import List, Dict, Optional

from utils import (
    normalize_date,
    to_float,
    calculate_checks,
)

# Date patterns seen on FCMB (e.g., 01-Jan-2025, 01/01/2025, 01-01-2025)
DATE_RX = re.compile(r"^(?P<date>\d{2}[-/.](?:[A-Za-z]{3}|\d{2})[-/.]\d{4})\b")

# Money token like: 1,234.00  or (1,234.00)
MONEY_RX = re.compile(r"\(?\s*\d{1,3}(?:,\d{3})*(?:\.\d{2})?\s*\)?$")

# Lines to always skip (summaries/footers)
SKIP_RX = re.compile(
    r"(debit\s*count|credit\s*count|total\s+charges|sms alert charges|maintenance fee|vat|stamp duty)",
    re.IGNORECASE,
)


def _strip_amount(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    neg = s.startswith("(") and s.endswith(")")
    v = f"{to_float(s):.2f}"
    return f"-{v}" if neg else v


def _ends_with_two_money_tokens(text: str) -> Optional[List[str]]:
    """
    Return [amount, balance] if the line ends with 2 money-like tokens; else None.
    We are tolerant of extra spaces.
    """
    parts = [p for p in text.strip().split() if p]
    if len(parts) < 2:
        return None
    last = parts[-1]
    prev = parts[-2]
    if MONEY_RX.match(last) and MONEY_RX.match(prev):
        return [prev, last]  # amount, balance
    return None


def _infer_dr_cr(
    prev_balance: Optional[float], amount_f: float, balance_f: float
) -> tuple[str, str]:
    """
    Decide whether 'amount' is DEBIT or CREDIT using running balance.
    - If balance decreased by ~amount => DEBIT
    - If balance increased by ~amount => CREDIT
    We allow a tiny tolerance (kobo drift).
    """
    if prev_balance is None:
        # first row: we can't infer — set both 0 and keep amount in CREDIT by default (common for inflows)
        return ("0.00", f"{amount_f:.2f}")
    dec = round(prev_balance - balance_f, 2)
    inc = round(balance_f - prev_balance, 2)
    amt = round(abs(amount_f), 2)

    tol = 0.05
    if abs(dec - amt) <= tol:
        return (f"{amt:.2f}", "0.00")  # DEBIT
    if abs(inc - amt) <= tol:
        return ("0.00", f"{amt:.2f}")  # CREDIT

    # Fallback heuristics: treat as CREDIT if positive delta, else DEBIT
    if inc > dec:
        return ("0.00", f"{amt:.2f}")
    else:
        return (f"{amt:.2f}", "0.00")


def parse(path: str) -> List[Dict[str, str]]:
    records: List[Dict[str, str]] = []

    try:
        with pdfplumber.open(path) as pdf:
            # We’ll build a flat list of textual lines across all pages
            raw_lines: List[str] = []
            for pno, page in enumerate(pdf.pages, 1):
                print(f"(fcmb:001) page {pno}", file=sys.stderr)
                text = page.extract_text() or ""
                # Some FCMB pages may insert odd blanks; keep non-empty lines
                for line in text.splitlines():
                    line = line.strip()
                    if line:
                        raw_lines.append(line)

        # Now stitch transactions using a buffer
        prev_balance: Optional[float] = None
        buffer_lines: List[str] = []
        current_date: Optional[str] = None
        current_val_date: Optional[str] = None

        def flush_buffer():
            """Parse the buffered lines into a record if possible."""
            nonlocal prev_balance, buffer_lines, current_date, current_val_date

            if not buffer_lines:
                return

            # Merge buffered lines with spaces (safer for trailing tokens detection)
            merged = " ".join(buffer_lines).strip()
            buffer_lines = []

            if SKIP_RX.search(merged.lower()):
                return

            # Date at start
            m = DATE_RX.match(merged)
            if not m:
                return  # not a transaction line

            txn_date_raw = m.group("date")
            txn_date = normalize_date(txn_date_raw)

            # Try to pick VAL_DATE immediately after TXN_DATE if present
            rest = merged[m.end() :].strip()
            val_m = DATE_RX.match(rest)
            if val_m:
                val_date_raw = val_m.group("date")
                val_date = normalize_date(val_date_raw)
                narr = rest[val_m.end() :].strip()
            else:
                val_date = ""
                narr = rest

            # Extract trailing two money tokens (amount, balance)
            tail = _ends_with_two_money_tokens(narr)
            if not tail:
                # No clean ending → cannot parse; skip
                return

            amount_txt, balance_txt = tail
            amount = _strip_amount(amount_txt)
            balance = _strip_amount(balance_txt)

            # Remaining narration (remove the two trailing tokens)
            narr_wo_tail = narr[: narr.rfind(amount_txt)].rstrip()
            narr_wo_tail = (
                narr_wo_tail[: narr_wo_tail.rfind(balance_txt)].strip()
                if balance_txt in narr_wo_tail
                else narr_wo_tail
            )
            # Safer: recompute by splitting tokens
            narr_tokens = narr.split()
            narr_core_tokens = narr_tokens[:-2]
            remarks = " ".join(narr_core_tokens).strip()

            # Infer DR/CR from running balance
            amt_f = to_float(amount)
            bal_f = to_float(balance)
            debit, credit = _infer_dr_cr(prev_balance, amt_f, bal_f)

            records.append(
                {
                    "TXN_DATE": txn_date,
                    "VAL_DATE": val_date,
                    "REFERENCE": "",
                    "REMARKS": remarks,
                    "DEBIT": debit,
                    "CREDIT": credit,
                    "BALANCE": balance,
                }
            )

            prev_balance = bal_f
            current_date = None
            current_val_date = None

        # Walk through lines and build transaction rows
        for line in raw_lines:
            # Start of a new transaction if:
            #  - line starts with a date, and
            #  - (eventually) we’ll wait until buffer ends with 2 money tokens to flush
            if DATE_RX.match(line):
                # If we had an ongoing buffer that never closed with amounts, drop it
                flush_buffer()
                buffer_lines = [line]
            else:
                # Inside a transaction: append narration/continuation
                if buffer_lines:
                    buffer_lines.append(line)
                else:
                    # ignore non-transaction lines outside a buffer
                    continue

            # If buffer (joined) ends with two money tokens, we can flush
            joined = " ".join(buffer_lines).strip()
            if _ends_with_two_money_tokens(joined):
                flush_buffer()

        # Flush trailing buffer if valid
        flush_buffer()

        # Remove empties, run sanity checks
        cleaned = [r for r in records if r["TXN_DATE"] or r["VAL_DATE"]]
        return calculate_checks(cleaned)

    except Exception as e:
        print(f"(fcmb:001 text) Error: {e}", file=sys.stderr)
        return []
