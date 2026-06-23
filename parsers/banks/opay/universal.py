import re
import sys
from typing import Dict, List, Optional

import pdfplumber

from utils import (
    calculate_checks,
    normalize_date,
    normalize_money,
    to_float,
)

DATE_TIME_OLD = r"\d{4}\s+[A-Za-z]{3}\s+\d{2}\s+\d{2}:\d{2}(?::\d{2})?"
DATE_TIME_NEW = r"\d{2}\s+[A-Za-z]{3}\s+\d{4}\s+\d{2}:\d{2}:\d{2}"
VALUE_DATE = r"\d{2}\s+[A-Za-z]{3}\s+\d{4}"
CHANNEL = r"(?:E-Channel|Mobile|USSD|POS)"
MONEY = r"[+-]?\d{1,3}(?:,\d{3})*(?:\.\d{2})|[+-]?\d+(?:\.\d{2})"
AMT_OR_DASH = rf"(?:--|-|{MONEY})"

RX_OLD_DT = re.compile(DATE_TIME_OLD)
RX_NEW_DT = re.compile(DATE_TIME_NEW)
RX_VALUE_DATE = re.compile(VALUE_DATE)
RX_WS = re.compile(r"\s+")

# New Opay layout: Debit and Credit are separate columns.
RX_NEW_TAIL = re.compile(
    rf"^(?P<desc>.*?)(?:\s+)?(?P<debit>{AMT_OR_DASH})\s+(?P<credit>{AMT_OR_DASH})\s+"
    rf"(?P<balance>{MONEY})\s+(?P<channel>{CHANNEL})(?:\s+(?P<ref>.*))?$",
    re.IGNORECASE | re.DOTALL,
)

# Old Opay layout: one signed Debit/Credit amount column.
RX_OLD_TAIL = re.compile(
    rf"^(?P<desc>.*?)(?:\s+)?(?P<amount>[+-]\d{{1,3}}(?:,\d{{3}})*(?:\.\d{{2}})|[+-]\d+(?:\.\d{{2}}))\s+"
    rf"(?P<balance>{MONEY})\s+(?P<channel>{CHANNEL})(?:\s+(?P<ref>.*))?$",
    re.IGNORECASE | re.DOTALL,
)

HEADER_WORDS = (
    "account statement",
    "summary - wallet balance",
    "trans. time",
    "value date",
    "opening balance",
    "closing balance",
    "current balance",
    "total debit",
    "total credit",
    "debit count",
    "credit count",
    "account name",
    "account number",
    "wallet account",
    "generated on",
    "note: current balance",
    "balance after",
)


def _clean_text(value: Optional[str]) -> str:
    if not value:
        return ""
    return RX_WS.sub(" ", str(value).replace("\x00", " ")).strip()


def _money(value: Optional[str]) -> str:
    value = _clean_text(value)
    if value in {"", "-", "--", "—"}:
        return "0.00"
    return normalize_money(value)


def _reference(*parts: str) -> str:
    joined = " ".join(_clean_text(p) for p in parts if _clean_text(p))
    return joined.strip()


def _blank_row() -> Dict[str, str]:
    return {
        "TXN_DATE": "",
        "VAL_DATE": "",
        "REFERENCE": "",
        "REMARKS": "",
        "DEBIT": "0.00",
        "CREDIT": "0.00",
        "BALANCE": "0.00",
        "Check": "",
        "Check 2": "",
    }


def _is_noise(text: str) -> bool:
    low = _clean_text(text).lower()
    if not low:
        return True
    if any(word in low for word in HEADER_WORDS):
        # Do not reject a real row just because the narration contains “wallet account”; only
        # reject lines that are mostly heading/summary text and have no transaction datetime.
        return not (RX_OLD_DT.search(text) or RX_NEW_DT.search(text))
    return False


def _normalise_txn_date(raw: str) -> str:
    raw = _clean_text(raw)
    # Opay old format: 2025 Mar 15 06:22:57 -> 15 Mar 2025
    m = re.match(r"^(\d{4})\s+([A-Za-z]{3})\s+(\d{2})", raw)
    if m:
        y, mon, d = m.groups()
        return normalize_date(f"{d} {mon} {y}")
    # New format already starts as DD Mon YYYY.
    return normalize_date(raw[:11])


def _parse_text_blob(
    blob: str, prefer_new: Optional[bool] = None
) -> Optional[Dict[str, str]]:
    text = _clean_text(blob)
    if _is_noise(text):
        return None

    matches = list(RX_NEW_DT.finditer(text)) + list(RX_OLD_DT.finditer(text))
    if not matches:
        return None
    first = sorted(matches, key=lambda m: m.start())[0]

    prefix_ref = text[: first.start()].strip()
    txn_raw = first.group(0)
    after_txn = text[first.end() :].strip()

    val_match = RX_VALUE_DATE.search(after_txn)
    if not val_match:
        return None
    val_raw = val_match.group(0)
    tail = after_txn[val_match.end() :].strip()

    # Try the correct shape first, then the other one. This is safer across wrapped rows.
    order = [prefer_new, not prefer_new] if prefer_new is not None else [True, False]
    for use_new in order:
        if use_new:
            m = RX_NEW_TAIL.match(tail)
            if not m:
                continue
            row = _blank_row()
            row["TXN_DATE"] = _normalise_txn_date(txn_raw)
            row["VAL_DATE"] = normalize_date(val_raw)
            row["REMARKS"] = _clean_text(m.group("desc")) or _clean_text(prefix_ref)
            row["DEBIT"] = _money(m.group("debit"))
            row["CREDIT"] = _money(m.group("credit"))
            row["BALANCE"] = _money(m.group("balance"))
            row["REFERENCE"] = _reference(prefix_ref, m.group("ref") or "")
            return row
        else:
            m = RX_OLD_TAIL.match(tail)
            if not m:
                continue
            amount_raw = _clean_text(m.group("amount"))
            amount = to_float(amount_raw)
            row = _blank_row()
            row["TXN_DATE"] = _normalise_txn_date(txn_raw)
            row["VAL_DATE"] = normalize_date(val_raw)
            row["REMARKS"] = _clean_text(m.group("desc")) or _clean_text(prefix_ref)
            row["DEBIT"] = f"{abs(amount):.2f}" if amount < 0 else "0.00"
            row["CREDIT"] = f"{abs(amount):.2f}" if amount > 0 else "0.00"
            row["BALANCE"] = _money(m.group("balance"))
            row["REFERENCE"] = _reference(prefix_ref, m.group("ref") or "")
            return row

    return None


def _header_is_new(header: List[Optional[str]]) -> bool:
    joined = " ".join(_clean_text(c).lower() for c in header)
    return (
        ("debit/credit" not in joined)
        and ("debit" in joined)
        and ("credit" in joined)
        and ("balance after" in joined or "balance" in joined)
    )


def _parse_structured_row(
    row: List[Optional[str]], prefer_new: bool
) -> Optional[Dict[str, str]]:
    cells = [_clean_text(c) for c in row]
    non_empty = [c for c in cells if c]
    if not non_empty:
        return None

    # Wrapped rows often land in a single populated cell. Re-parse the whole row text.
    if len(non_empty) == 1 or not (
        RX_OLD_DT.search(cells[0]) or RX_NEW_DT.search(cells[0])
    ):
        return _parse_text_blob(" ".join(non_empty), prefer_new=prefer_new)

    if prefer_new and len(cells) >= 8:
        row_out = _blank_row()
        row_out["TXN_DATE"] = _normalise_txn_date(cells[0])
        row_out["VAL_DATE"] = normalize_date(cells[1])
        row_out["REMARKS"] = cells[2]
        row_out["DEBIT"] = _money(cells[3])
        row_out["CREDIT"] = _money(cells[4])
        row_out["BALANCE"] = _money(cells[5])
        row_out["REFERENCE"] = _reference(cells[7])
        return row_out if row_out["TXN_DATE"] and row_out["VAL_DATE"] else None

    if not prefer_new and len(cells) >= 7:
        amount = to_float(cells[3])
        row_out = _blank_row()
        row_out["TXN_DATE"] = _normalise_txn_date(cells[0])
        row_out["VAL_DATE"] = normalize_date(cells[1])
        row_out["REMARKS"] = cells[2]
        row_out["DEBIT"] = f"{abs(amount):.2f}" if amount < 0 else "0.00"
        row_out["CREDIT"] = f"{abs(amount):.2f}" if amount > 0 else "0.00"
        row_out["BALANCE"] = _money(cells[4])
        row_out["REFERENCE"] = _reference(cells[6], cells[7] if len(cells) > 7 else "")
        return row_out if row_out["TXN_DATE"] and row_out["VAL_DATE"] else None

    return _parse_text_blob(" ".join(non_empty), prefer_new=prefer_new)


def _dedupe(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    out = []
    for r in rows:
        key = (
            r.get("TXN_DATE"),
            r.get("VAL_DATE"),
            r.get("REMARKS"),
            r.get("DEBIT"),
            r.get("CREDIT"),
            r.get("BALANCE"),
            r.get("REFERENCE"),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def parse(path: str) -> List[Dict[str, str]]:
    transactions: List[Dict[str, str]] = []

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                print(f"(opay_universal): Processing page {page_num}", file=sys.stderr)
                page_rows: List[Dict[str, str]] = []
                tables = page.extract_tables(
                    {
                        "vertical_strategy": "lines",
                        "horizontal_strategy": "lines",
                        "snap_tolerance": 3,
                        "join_tolerance": 3,
                        "text_tolerance": 1,
                        "intersection_tolerance": 3,
                    }
                )

                for table in tables or []:
                    if not table:
                        continue
                    header = table[0] or []
                    prefer_new = _header_is_new(header)
                    data_rows = (
                        table[1:] if any(_clean_text(c) for c in header) else table
                    )
                    for raw_row in data_rows:
                        parsed = _parse_structured_row(raw_row, prefer_new=prefer_new)
                        if parsed:
                            page_rows.append(parsed)

                # Text fallback catches rows table extraction misses at page breaks.
                if not page_rows:
                    text = page.extract_text(x_tolerance=1, y_tolerance=3) or ""
                    # Segment before each transaction datetime, preserving any reference that appears before it.
                    starts = sorted(
                        [m.start() for m in RX_NEW_DT.finditer(text)]
                        + [m.start() for m in RX_OLD_DT.finditer(text)]
                    )
                    for i, start in enumerate(starts):
                        # Include a small prefix because Opay sometimes puts reference above the date.
                        prefix_start = max(0, start - 80)
                        end = starts[i + 1] if i + 1 < len(starts) else len(text)
                        parsed = _parse_text_blob(
                            text[prefix_start:end], prefer_new=None
                        )
                        if parsed:
                            page_rows.append(parsed)

                transactions.extend(page_rows)

        transactions = _dedupe(
            [
                r
                for r in transactions
                if r.get("TXN_DATE")
                and r.get("VAL_DATE")
                and r.get("REMARKS")
                and (to_float(r.get("DEBIT", "0")) or to_float(r.get("CREDIT", "0")))
            ]
        )
        return calculate_checks(transactions)

    except Exception as exc:
        print(f"(opay): Error processing PDF: {exc}", file=sys.stderr)
        return []
