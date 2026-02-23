import re
import sys
from typing import List, Dict, Optional

import pdfplumber

from utils import (
    normalize_date,
    join_date_fragments,
    normalize_money,
    clean_money,
    to_float,
    calculate_checks,
    RX_MULTI_WS,
)

# Matches "12/05/25" (Kuda commonly uses dd/mm/yy)
RX_DATE = re.compile(r"^\s*(\d{2}/\d{2}/\d{2})\b")

# Matches "07:47:16"
RX_TIME = re.compile(r"^\s*(\d{2}:\d{2}:\d{2})\b")

# Matches ₦ amounts including negatives: ₦-28,997.57
RX_NAIRA = re.compile(r"₦\s*-?\s*\d[\d,]*\.\d{2}")

# Heuristic: lines that are definitely not transaction content
RX_JUNK = re.compile(
    r"(?i)^\s*(statement|summary|opening balance|closing balance|money in|money out|kuda mf bank|all rights reserved|ndic)\b"
)

HEADER_MARKERS = (
    "Date/Time",
    "Money In",
    "Money out",
    "Category",
    "To / From",
    "Description",
    "Balance",
)


def _collapse_spaces(s: str) -> str:
    return RX_MULTI_WS.sub(" ", (s or "").strip())


def _extract_money_tokens(line: str) -> List[str]:
    return [m.group(0) for m in RX_NAIRA.finditer(line or "")]


def _strip_money_tokens(line: str) -> str:
    return RX_NAIRA.sub(" ", line or "")


def _infer_debit_credit_from_balances(
    amount: float,
    prev_balance: Optional[float],
    curr_balance: Optional[float],
) -> tuple[str, str]:
    """
    If we only have ONE txn amount, infer whether it's debit/credit using balance movement.
    Falls back to 0/0 if we can't infer.
    """
    if prev_balance is None or curr_balance is None:
        return ("0.00", "0.00")

    # If balance went down, that's a debit; else credit.
    if curr_balance < prev_balance:
        return (f"{abs(amount):.2f}", "0.00")
    return ("0.00", f"{abs(amount):.2f}")


def parse(pdf_path: str) -> List[Dict[str, str]]:
    """
    Kuda statement parser:
    - TXN_DATE: date portion from Date/Time column
    - VAL_DATE: same as TXN_DATE (Kuda doesn't provide a separate value date here)
    - REMARKS: combines Category + To/From + Description (and any wrapped lines)
    - DEBIT/CREDIT:
        * If both Money In and Money Out exist on the same txn => map directly.
        * If only one amount exists => infer using previous & current balances.
    - BALANCE: last ₦ amount on the primary row for that txn
    """
    rows: List[Dict[str, str]] = []

    # Working state for the current txn being built
    current: Optional[Dict[str, str]] = None
    current_date_raw: str = ""
    current_time_raw: str = ""
    current_desc_parts: List[str] = []
    current_amounts: List[str] = []  # txn amounts (not balance)
    current_balance_raw: str = ""

    prev_balance: Optional[float] = None

    def flush_current():
        nonlocal current, current_date_raw, current_time_raw, current_desc_parts
        nonlocal current_amounts, current_balance_raw, prev_balance

        if not current_date_raw and not current_balance_raw and not current_amounts:
            # nothing meaningful
            current = None
            current_desc_parts = []
            current_amounts = []
            current_balance_raw = ""
            current_date_raw = ""
            current_time_raw = ""
            return

        txn_date = normalize_date(join_date_fragments(current_date_raw))
        if not txn_date:
            # if we can't normalize, still keep the raw date as last resort
            txn_date = current_date_raw.strip()

        # Balance
        bal_clean = normalize_money(current_balance_raw) if current_balance_raw else ""
        curr_balance = to_float(bal_clean) if bal_clean else None

        # Decide debit/credit
        debit = "0.00"
        credit = "0.00"

        # If we managed to capture two txn amounts (money in + money out), map directly.
        # Otherwise, infer using balance movement.
        # NOTE: Kuda rows sometimes include just one txn amount (either in or out).
        cleaned_amounts = [
            normalize_money(a) for a in current_amounts if a and a.strip()
        ]
        cleaned_amounts = [a for a in cleaned_amounts if to_float(a) != 0.0]

        if len(cleaned_amounts) >= 2:
            # Assume [money_in, money_out] in that order when both appear.
            # If Kuda ever flips, balance-inference later via checks will flag.
            credit = cleaned_amounts[0]
            debit = cleaned_amounts[1]
        elif len(cleaned_amounts) == 1:
            amt = to_float(cleaned_amounts[0])
            d, c = _infer_debit_credit_from_balances(amt, prev_balance, curr_balance)
            debit, credit = d, c
        else:
            # no txn amount captured
            debit, credit = ("0.00", "0.00")

        remarks = _collapse_spaces(
            " ".join([p for p in current_desc_parts if p and p.strip()])
        )

        row = {
            "TXN_DATE": txn_date,
            "VAL_DATE": txn_date,
            "REFERENCE": "",
            "REMARKS": remarks,
            "DEBIT": debit,
            "CREDIT": credit,
            "BALANCE": bal_clean,
            "Check": "",
            "Check 2": "",
        }

        rows.append(row)

        # Update prev balance for next inference
        if curr_balance is not None:
            prev_balance = curr_balance

        # reset
        current = None
        current_desc_parts = []
        current_amounts = []
        current_balance_raw = ""
        current_date_raw = ""
        current_time_raw = ""

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            print(f"(kuda:model_01): Processing page {page_num}", file=sys.stderr)

            text = page.extract_text(layout=True) or ""
            if not text.strip():
                continue

            lines = text.splitlines()

            # Find where the transaction table starts (header row).
            start_idx = 0
            for i, ln in enumerate(lines):
                if all(h in ln for h in ("Date/Time", "Money In", "Money out")):
                    start_idx = i + 1
                    break

            for ln in lines[start_idx:]:
                line = ln.rstrip("\n")
                if not line.strip():
                    continue
                if RX_JUNK.match(line):
                    continue

                # If we hit a footer-ish line, skip
                if "Kuda MF Bank" in line:
                    continue

                # Start of a new transaction row (date present)
                m_date = RX_DATE.match(line)
                if m_date:
                    # flush any previous txn before starting a new one
                    flush_current()

                    current_date_raw = m_date.group(1)
                    rest = line[m_date.end() :].strip()

                    # Extract money tokens from this line
                    money_tokens = _extract_money_tokens(line)

                    # Balance is almost always the last ₦ token on the primary row
                    # (the one that has the date + most columns).
                    if money_tokens:
                        current_balance_raw = money_tokens[-1]

                        # Any earlier ₦ tokens are txn amounts (Money In / Money out)
                        if len(money_tokens) >= 2:
                            current_amounts.extend(money_tokens[:-1])
                        else:
                            # only one ₦ token: could be amount or balance.
                            # If it's the only token on this row, treat it as amount for now;
                            # If later lines provide a balance, we'll overwrite.
                            current_amounts.append(money_tokens[0])

                    # Add descriptive text (category/to-from/description), stripping money
                    rest_desc = _strip_money_tokens(rest)
                    rest_desc = _collapse_spaces(rest_desc)
                    if rest_desc:
                        current_desc_parts.append(rest_desc)
                    continue

                # Time line (continuation line)
                m_time = RX_TIME.match(line)
                if m_time and current_date_raw:
                    current_time_raw = m_time.group(1)
                    rest = line[m_time.end() :].strip()
                    rest_desc = _collapse_spaces(_strip_money_tokens(rest))
                    if rest_desc:
                        current_desc_parts.append(rest_desc)
                    continue

                # If line contains ₦ amounts but no date, it may be a continuation where
                # the amount/balance landed on a separate wrapped line (seen in Momoh PDF).
                if RX_NAIRA.search(line) and current_date_raw:
                    money_tokens = _extract_money_tokens(line)

                    # If line contains a balance-like last token and we don't have balance yet,
                    # or if this line clearly ends with a balance, update balance.
                    if money_tokens:
                        # If this line has 2 tokens, it may be [amount, balance]
                        # If 1 token and our current_balance_raw looks missing/weak, update.
                        # We'll treat the last as balance if it "looks like" it sits near end.
                        current_balance_raw = money_tokens[-1] or current_balance_raw

                        if len(money_tokens) >= 2:
                            current_amounts.extend(money_tokens[:-1])
                        else:
                            # single token on continuation line: could be amount
                            current_amounts.append(money_tokens[0])

                    rest_desc = _collapse_spaces(_strip_money_tokens(line))
                    if rest_desc:
                        current_desc_parts.append(rest_desc)
                    continue

                # Other continuation text lines (wrapped To/From or Description)
                if current_date_raw:
                    cont = _collapse_spaces(line)
                    if cont and not RX_JUNK.match(cont):
                        current_desc_parts.append(cont)

            # end page loop; do not flush here yet because txn may continue
            # but in practice Kuda wraps within page, still safe to keep.
        # flush last txn
        flush_current()

    # Remove rows with no date
    rows = [r for r in rows if (r.get("TXN_DATE") or "").strip()]

    # Recompute checks using your utility
    return calculate_checks(rows)
