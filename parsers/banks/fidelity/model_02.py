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


CHANNEL_PATTERNS = [
    "NIP Transfer",
    "Online Banking",
    "Mobile Banking",
    "Internet Banking",
    "POS",
    "ATM",
    "USSD",
    "Others",
    "NIP",  # keep NIP after "NIP Transfer" so it doesn't steal the match
]


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


def _extract_channel_and_remarks(text: str) -> (str, str):
    """
    Given a text that looks like:
      "ELECTRONIC MONEY TRANSFER LEVY - 01-07-2025 Others"
    or:
      "MSURSHIMA COMFO/kitchen /AT68_TRF2MPTankma19400932 NIP Transfer"
    return (channel, remarks).
    """
    clean = re.sub(r"\s+", " ", text).strip()

    # Try longest / most specific channels first
    for ch in sorted(CHANNEL_PATTERNS, key=len, reverse=True):
        # match channel at very end
        pat = re.compile(rf"(.*)\b{re.escape(ch)}\s*$", re.IGNORECASE)
        m = pat.match(clean)
        if m:
            remarks = (m.group(1) or "").strip()
            # normalize casing to your canonical labels
            channel = ch
            return channel, remarks

    # If no channel match, keep all as remarks
    return "", clean


def _parse_compact_row(cell: str) -> Optional[Dict[str, str]]:
    """
    More robust Fidelity model_02 collapsed-row parser.

    Works for:
      - multi-line rows where channel is split ("NIP" + "Transfer")
      - rows that start with narration text (not channel)
      - one-line rows (no linebreaks)
    """
    if not cell or not str(cell).strip():
        return None

    raw = str(cell)
    all_text = re.sub(r"\s+", " ", raw.replace("\n", " ")).strip()

    # Find the first two dates anywhere in the cell
    dates = DATE_RE.findall(all_text)
    if len(dates) < 2:
        return None

    txn_date_raw, val_date_raw = dates[0], dates[1]

    # Slice the string to what's after the 2nd date (narration + channel + numbers)
    date_iters = list(DATE_RE.finditer(all_text))
    after_dates = (
        all_text[date_iters[1].end() :].strip() if len(date_iters) >= 2 else all_text
    )

    # Pull all money values from after_dates first (fallback to whole text)
    amts = AMT_RE.findall(after_dates)
    if len(amts) < 2:
        amts = AMT_RE.findall(all_text)
    if len(amts) < 2:
        return None

    balance_raw = amts[-1]
    amount_raw = amts[-2]

    # Remove trailing balance and amount from the text
    # (we remove from the right to avoid killing earlier similar numbers)
    tmp = after_dates
    # remove balance
    bpos = tmp.rfind(balance_raw)
    if bpos != -1:
        tmp = (tmp[:bpos] + tmp[bpos + len(balance_raw) :]).strip()
    # remove amount
    apos = tmp.rfind(amount_raw)
    if apos != -1:
        tmp = (tmp[:apos] + tmp[apos + len(amount_raw) :]).strip()

    # Whatever remains should end with the channel label
    channel, remarks = _extract_channel_and_remarks(tmp)

    # If channel is empty but the ORIGINAL cell contains "Transfer" and "NIP" split oddly,
    # try a small rescue:
    if not channel:
        if re.search(r"\bNIP\b", all_text, re.IGNORECASE) and re.search(
            r"\bTransfer\b", all_text, re.IGNORECASE
        ):
            channel = "NIP Transfer"
            # remove those words from remarks if they appear at end
            remarks = re.sub(
                r"\bNIP\s+Transfer\b\s*$", "", remarks, flags=re.IGNORECASE
            ).strip()

    return {
        "TXN_DATE": normalize_date(txn_date_raw),
        "VAL_DATE": normalize_date(val_date_raw),
        "REFERENCE": channel.strip() or "",  # channel goes into REFERENCE
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
                                "BALANCE": f"{bal:.2f}",
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
