import re
import sys
from typing import List, Dict, Optional, Tuple

import pdfplumber

from utils import (
    normalize_date,
    join_date_fragments,
    normalize_money,
    to_float,
    calculate_checks,
    RX_MULTI_WS,
)

RX_DATE = re.compile(r"^\s*(\d{2}/\d{2}/\d{2})\b")
RX_TIME = re.compile(r"^\s*(\d{2}:\d{2}:\d{2})\b")
RX_NAIRA = re.compile(r"₦\s*-?\s*\d[\d,]*\.\d{2}")

RX_JUNK = re.compile(
    r"(?i)^\s*(statement|summary|opening balance|closing balance|money in|money out|kuda mf bank|all rights reserved|ndic)\b"
)

# Split Kuda columns using preserved layout spacing
RX_COL_SPLIT = re.compile(r"\s{2,}")

# Footer noise markers (page bottom) + next page carryover
FOOTER_MARKERS = (
    "licensed by the central bank of nigeria",
    "“kuda” and “kudabank”",
    '"kuda" and "kudabank"',
    "trademarks of kuda technologies",
    "commercial avenue",
    "finsbury pavement",
    "page ",
    "account number",
)

CARRYOVER_MARKERS = ("all statements",)


def _collapse_spaces(s: str) -> str:
    return RX_MULTI_WS.sub(" ", (s or "").strip())


def _extract_money_tokens(line: str) -> List[str]:
    return [m.group(0) for m in RX_NAIRA.finditer(line or "")]


def _strip_money_tokens_keep_spacing(line: str) -> str:
    """
    Remove ₦ amounts but keep other whitespace so we can split columns by 2+ spaces.
    """
    return RX_NAIRA.sub(" ", line or "")


def _looks_like_footer(line: str) -> bool:
    t = (line or "").strip().lower()
    if not t:
        return False
    if any(m in t for m in CARRYOVER_MARKERS):
        return True
    if any(m in t for m in FOOTER_MARKERS):
        return True
    return False


def _trim_footer_from_text(s: str) -> str:
    """
    If footer text leaks into a transaction line, cut it off.
    """
    if not s:
        return ""
    t = s
    low = t.lower()
    cut = None
    for m in FOOTER_MARKERS:
        idx = low.find(m)
        if idx != -1:
            cut = idx if cut is None else min(cut, idx)
    for m in CARRYOVER_MARKERS:
        idx = low.find(m)
        if idx != -1:
            cut = idx if cut is None else min(cut, idx)

    if cut is not None:
        t = t[:cut]
    return _collapse_spaces(t)


def _parse_columns_from_rest(rest_no_money: str) -> Tuple[str, str]:
    """
    Given the part of the line after removing date/time and ₦ amounts,
    split into Kuda columns:
      Category | To/From | Description

    We return:
      reference (Category), remarks (Description)
    """
    raw = rest_no_money.rstrip()
    # Split by large spacing blocks (table columns)
    parts = [p.strip() for p in RX_COL_SPLIT.split(raw) if p.strip()]

    if not parts:
        return ("", "")

    # Typical Kuda row yields:
    # parts[0] = Category (e.g., "inward transfer")
    # parts[1] = To/From (ignored)
    # parts[2] = Description (remarks)
    #
    # Sometimes pdf text merges To/From + Description into one chunk → parts length 2
    # Then we treat parts[1] as Description.
    reference = parts[0] if len(parts) >= 1 else ""
    if len(parts) >= 3:
        remarks = " ".join(parts[2:])
    elif len(parts) == 2:
        remarks = parts[1]
    else:
        remarks = ""

    return (_collapse_spaces(reference), _collapse_spaces(remarks))


def _infer_debit_credit_from_balances(
    amount: float,
    prev_balance: Optional[float],
    curr_balance: Optional[float],
    default_side: str = "CREDIT",  # used when prev_balance is None
) -> Tuple[str, str]:
    """
    If we only have ONE txn amount:
    - infer debit/credit using balance movement when possible.
    - if prev_balance is None, default to CREDIT (or DEBIT) depending on heuristics.
    """
    if prev_balance is None or curr_balance is None:
        if default_side == "DEBIT":
            return (f"{abs(amount):.2f}", "0.00")
        return ("0.00", f"{abs(amount):.2f}")

    if curr_balance < prev_balance:
        return (f"{abs(amount):.2f}", "0.00")
    return ("0.00", f"{abs(amount):.2f}")


def parse(pdf_path: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []

    current_date_raw: str = ""
    current_reference: str = ""
    current_remarks_parts: List[str] = []

    current_amounts: List[str] = []  # txn amounts (not balance)
    current_balance_raw: str = ""

    prev_balance: Optional[float] = None

    def flush_current():
        nonlocal current_date_raw, current_reference, current_remarks_parts
        nonlocal current_amounts, current_balance_raw, prev_balance

        if not current_date_raw and not current_balance_raw and not current_amounts:
            current_date_raw = ""
            current_reference = ""
            current_remarks_parts = []
            current_amounts = []
            current_balance_raw = ""
            return

        txn_date = (
            normalize_date(join_date_fragments(current_date_raw))
            or current_date_raw.strip()
        )

        bal_clean = normalize_money(current_balance_raw) if current_balance_raw else ""
        curr_balance = to_float(bal_clean) if bal_clean else None

        debit = "0.00"
        credit = "0.00"

        cleaned_amounts = [
            normalize_money(a) for a in current_amounts if a and a.strip()
        ]
        cleaned_amounts = [a for a in cleaned_amounts if to_float(a) != 0.0]

        if len(cleaned_amounts) >= 2:
            # Kuda: [Money In, Money Out] when both exist
            credit = cleaned_amounts[0]
            debit = cleaned_amounts[1]
        elif len(cleaned_amounts) == 1:
            amt_val = to_float(cleaned_amounts[0])

            # If we can't infer (first txn), default to CREDIT unless amount looked negative
            default_side = "CREDIT"
            # If raw amount had a minus sign somewhere, treat as debit
            raw_amt = current_amounts[0]
            if "-" in raw_amt:
                default_side = "DEBIT"

            d, c = _infer_debit_credit_from_balances(
                amt_val, prev_balance, curr_balance, default_side=default_side
            )
            debit, credit = d, c
        else:
            debit, credit = ("0.00", "0.00")

        remarks = _trim_footer_from_text(
            " ".join([p for p in current_remarks_parts if p and p.strip()])
        )

        row = {
            "TXN_DATE": txn_date,
            "VAL_DATE": txn_date,
            "REFERENCE": _collapse_spaces(
                current_reference
            ).lower(),  # matches your expected output
            "REMARKS": remarks,
            "DEBIT": debit,
            "CREDIT": credit,
            "BALANCE": bal_clean,
            "Check": "",
            "Check 2": "",
        }

        rows.append(row)

        if curr_balance is not None:
            prev_balance = curr_balance

        current_date_raw = ""
        current_reference = ""
        current_remarks_parts = []
        current_amounts = []
        current_balance_raw = ""

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            print(f"(kuda): Processing page {page_num}", file=sys.stderr)

            text = page.extract_text(layout=True) or ""
            if not text.strip():
                continue

            lines = text.splitlines()

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
                if _looks_like_footer(line):
                    continue

                m_date = RX_DATE.match(line)
                if m_date:
                    flush_current()

                    current_date_raw = m_date.group(1)
                    rest = line[m_date.end() :].rstrip()

                    money_tokens = _extract_money_tokens(line)

                    if money_tokens:
                        current_balance_raw = money_tokens[-1]
                        if len(money_tokens) >= 2:
                            current_amounts.extend(money_tokens[:-1])
                        else:
                            current_amounts.append(money_tokens[0])

                    # IMPORTANT: parse Category/ToFrom/Description from spacing, and map correctly
                    rest_no_money = _strip_money_tokens_keep_spacing(rest)
                    ref, rem = _parse_columns_from_rest(rest_no_money)

                    current_reference = ref
                    if rem:
                        current_remarks_parts.append(rem)

                    continue

                # Time line continuation
                m_time = RX_TIME.match(line)
                if m_time and current_date_raw:
                    rest = line[m_time.end() :].rstrip()

                    if _looks_like_footer(rest):
                        continue

                    rest_no_money = _strip_money_tokens_keep_spacing(rest)
                    # Continuation lines can still contain table columns; extract remarks chunk
                    ref, rem = _parse_columns_from_rest(rest_no_money)

                    # Only set reference if it was missing (rare)
                    if not current_reference and ref:
                        current_reference = ref

                    if rem:
                        current_remarks_parts.append(rem)
                    continue

                # Continuation line that includes ₦ tokens
                if RX_NAIRA.search(line) and current_date_raw:
                    if _looks_like_footer(line):
                        continue

                    money_tokens = _extract_money_tokens(line)
                    if money_tokens:
                        current_balance_raw = money_tokens[-1] or current_balance_raw
                        if len(money_tokens) >= 2:
                            current_amounts.extend(money_tokens[:-1])
                        else:
                            current_amounts.append(money_tokens[0])

                    rest_no_money = _strip_money_tokens_keep_spacing(line)
                    ref, rem = _parse_columns_from_rest(rest_no_money)
                    if not current_reference and ref:
                        current_reference = ref
                    if rem:
                        current_remarks_parts.append(rem)
                    continue

                # Other continuation text (wrapped description)
                if current_date_raw:
                    if _looks_like_footer(line):
                        continue
                    cont = _trim_footer_from_text(line)
                    if cont and not RX_JUNK.match(cont):
                        current_remarks_parts.append(cont)

        flush_current()

    rows = [r for r in rows if (r.get("TXN_DATE") or "").strip()]

    return calculate_checks(rows)
