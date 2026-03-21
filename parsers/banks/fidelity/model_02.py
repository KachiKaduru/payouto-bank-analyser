# banks/fidelity/model_02.py
import sys
import re
from typing import List, Dict, Optional

import pdfplumber

from utils import (
    MAIN_TABLE_SETTINGS,
    normalize_date,
    normalize_money,
    to_float,
    calculate_checks,
)

# --- Patterns for this Fidelity layout ---
DATE_RE = re.compile(r"\b\d{2}-[A-Za-z]{3}-\d{4}\b")  # 01-Jul-2025
AMT_RE = re.compile(r"\b\d[\d,]*\.\d{2}\b")  # 4,221,845.19 / 53.75


CHANNEL_PATTERNS = {
    "NIP Transfer": ["NIP", "Transfer"],
    "Online Banking": ["Online", "Banking"],
    "Mobile Banking": ["Mobile"],
    "Internet Banking": ["Internet"],
    "POS": ["POS"],
    "ATM": ["ATM"],
    "USSD": ["USSD"],
    "Others": ["Others"],
}


def _is_fidelity_model02_header(row: List[Optional[str]]) -> bool:
    if not row:
        return False
    norm = [(c or "").strip().lower() for c in row]
    required = [
        "tran date",
        "value date",
        "narration",
        "channel",
        "debit",
        "credit",
        "balance",
    ]
    return all(any(req == c for c in norm) for req in required)


def _extract_channel_and_remarks(text: str) -> tuple[str, str]:
    clean = re.sub(r"\s+", " ", text).strip()

    # Try longer canonical channel names first (more specific)
    for channel in sorted(CHANNEL_PATTERNS.keys(), key=len, reverse=True):
        aliases = CHANNEL_PATTERNS[channel]

        for alias in aliases:
            # Match alias at end
            # We'll build a "tail" regex: (.*) <alias>$
            alias_re = _alias_to_regex(alias)
            m = re.match(rf"^(.*)({alias_re.pattern})\s*$", clean, flags=re.IGNORECASE)
            if m:
                remarks = (m.group(1) or "").strip()
                return channel, remarks

    return "", clean


def _alias_to_regex(alias) -> re.Pattern:
    """
    alias can be:
      - a string: "NIP Transfer"
      - a list of words: ["NIP", "Transfer"]
    Matches even if words are split by any whitespace/newlines.
    """
    if isinstance(alias, list):
        words = [re.escape(w) for w in alias if str(w).strip()]
    else:
        words = [re.escape(w) for w in str(alias).split() if w.strip()]

    if not words:
        return re.compile(r"^$")

    return re.compile(r"\b" + r"\s+".join(words) + r"\b", re.IGNORECASE)


def _find_any_channel_in_text(text: str) -> str:
    for channel in sorted(CHANNEL_PATTERNS.keys(), key=len, reverse=True):
        for alias in CHANNEL_PATTERNS[channel]:
            if _alias_to_regex(alias).search(text):
                return channel
    return ""


def _parse_compact_row(cell: str) -> Optional[Dict[str, str]]:
    """
    More robust Fidelity model_02 collapsed-row parser.

    Improvements:
      - preserves text BEFORE the first date (some PDFs place narration/channel there)
      - still extracts AMOUNT/BALANCE from after_dates (same logic as before)
      - uses CHANNEL_PATTERNS-driven rescue instead of hardcoded NIP/Transfer
    """
    if not cell or not str(cell).strip():
        return None

    raw = str(cell)
    # Keep a whitespace-normalized version for slicing + regex searching
    all_text = re.sub(r"\s+", " ", raw.replace("\n", " ")).strip()

    date_iters = list(DATE_RE.finditer(all_text))
    if len(date_iters) < 2:
        return None

    txn_date_raw = date_iters[0].group(0)
    val_date_raw = date_iters[1].group(0)

    # Text before the first date (can contain narration/channel fragments in some PDFs)
    before_first_date = all_text[: date_iters[0].start()].strip()

    # Slice the string to what's after the 2nd date (narration + channel + numbers)
    after_dates = all_text[date_iters[1].end() :].strip()

    # Detect parentheses-based negative balance BEFORE extraction
    is_balance_negative = False
    paren_balance_match = re.search(r"\(\s*\d[\d,]*\.\d{2}\s*\)", after_dates)
    if paren_balance_match:
        is_balance_negative = True

    # Pull all money values from after_dates first (fallback to whole text)
    amts = AMT_RE.findall(after_dates)
    if len(amts) < 2:
        amts = AMT_RE.findall(all_text)
    if len(amts) < 2:
        return None

    amount_raw = amts[-2]
    balance_raw = amts[-1]

    if is_balance_negative:
        balance_raw = f"({balance_raw})"

    # Remove trailing balance and amount from the text (from the right)
    tmp = after_dates

    bpos = tmp.rfind(balance_raw)
    if bpos != -1:
        tmp = (tmp[:bpos] + tmp[bpos + len(balance_raw) :]).strip()

    apos = tmp.rfind(amount_raw)
    if apos != -1:
        tmp = (tmp[:apos] + tmp[apos + len(amount_raw) :]).strip()

    # NEW: concatenate before-first-date + tmp so we don't lose any “first line” info
    combined = " ".join([before_first_date, tmp]).strip()

    # Extract channel and remarks based on channel being at the END
    channel, remarks = _extract_channel_and_remarks(combined)

    # Rescue: if channel is still empty, try finding any channel anywhere in the original cell
    if not channel:
        found = _find_any_channel_in_text(raw) or _find_any_channel_in_text(all_text)
        if found:
            channel = found
            # Best-effort cleanup: if remarks ends with that channel, strip it
            # (handles cases where channel exists but isn't neatly at end)
            remarks = re.sub(
                rf"\b{re.escape(found)}\b\s*$",
                "",
                remarks,
                flags=re.IGNORECASE,
            ).strip()

    return {
        "TXN_DATE": normalize_date(txn_date_raw),
        "VAL_DATE": normalize_date(val_date_raw),
        "REFERENCE": channel.strip() or "",
        "REMARKS": remarks.strip(),
        "AMOUNT": normalize_money(amount_raw),
        "BALANCE": normalize_money(balance_raw),
    }


def parse(path: str) -> List[Dict[str, str]]:
    transactions: List[Dict[str, str]] = []
    prev_balance: Optional[float] = None

    with pdfplumber.open(path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            print(f"(fidelity model_02): Processing page {page_num}", file=sys.stderr)

            tables = page.extract_tables(MAIN_TABLE_SETTINGS)
            if not tables:
                continue

            for table in tables:
                if not table or len(table) < 2:
                    continue

                header = table[0]
                if not _is_fidelity_model02_header(header):
                    continue

                data_rows = table[1:]

                for row in data_rows:
                    if not row:
                        continue

                    # CASE A: Collapsed body rows (everything in first cell, rest None/empty)
                    first_cell = row[0] if len(row) > 0 else None
                    others_empty = all(
                        (c is None or str(c).strip() == "")
                        for c in (row[1:] if len(row) > 1 else [])
                    )

                    if first_cell and others_empty:
                        parsed = _parse_compact_row(first_cell)
                        if not parsed:
                            continue

                        bal = to_float(parsed["BALANCE"])
                        amt = to_float(parsed["AMOUNT"])

                        debit = "0.00"
                        credit = "0.00"

                        # infer direction from balance movement
                        if prev_balance is not None:
                            if bal < prev_balance - 0.0001:
                                debit = f"{abs(amt):.2f}"
                                credit = "0.00"
                            elif bal > prev_balance + 0.0001:
                                debit = "0.00"
                                credit = f"{abs(amt):.2f}"

                        prev_balance = bal

                        transactions.append(
                            {
                                "TXN_DATE": parsed["TXN_DATE"],
                                "VAL_DATE": parsed["VAL_DATE"],
                                "REFERENCE": parsed["REFERENCE"],
                                "REMARKS": parsed["REMARKS"],
                                "DEBIT": debit,
                                "CREDIT": credit,
                                "BALANCE": parsed["BALANCE"],
                                # "BALANCE": f"{bal:.2f}",
                                "Check": "",
                                "Check 2": "",
                            }
                        )
                        continue

                    # CASE B: If some pages return proper 7 columns, support it too
                    txn_date = (
                        normalize_date((row[0] or "").strip()) if len(row) > 0 else ""
                    )
                    val_date = (
                        normalize_date((row[1] or "").strip()) if len(row) > 1 else ""
                    )
                    narration = (row[2] or "").strip() if len(row) > 2 else ""
                    channel = (
                        (row[3] or "").replace("\n", " ").strip()
                        if len(row) > 3
                        else ""
                    )
                    debit = (
                        normalize_money(row[4] or "0.00") if len(row) > 4 else "0.00"
                    )
                    credit = (
                        normalize_money(row[5] or "0.00") if len(row) > 5 else "0.00"
                    )
                    balance = normalize_money(row[6] or "") if len(row) > 6 else ""

                    if balance:
                        prev_balance = to_float(balance)

                    transactions.append(
                        {
                            "TXN_DATE": txn_date,
                            "VAL_DATE": val_date,
                            "REFERENCE": channel,
                            "REMARKS": narration,
                            "DEBIT": debit,
                            "CREDIT": credit,
                            "BALANCE": balance,
                            "Check": "",
                            "Check 2": "",
                        }
                    )

    # drop empty-date rows + compute checks
    transactions = [t for t in transactions if t["TXN_DATE"] or t["VAL_DATE"]]
    return calculate_checks(transactions)
