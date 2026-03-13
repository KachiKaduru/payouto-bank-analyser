# app/parsers/banks/stanbic_ibtc/model_02.py
import re
import sys
from typing import List, Dict, Optional

import pdfplumber

from utils import (
    STANDARDIZED_ROW,
    normalize_date,
    clean_money,
    calculate_checks,
)

# ----------------------------
# Regex
# ----------------------------

RX_PAGE = re.compile(r"^Page\s+\d+\s+of\s+\d+$", re.I)

# Full date on one line: 09 Mar 2026
RX_FULL_DATE = re.compile(r"^\d{2}\s+[A-Z][a-z]{2}\s+\d{4}$")

# Split date across 2 lines:
# 09 Mar
# 2026
RX_DAY_MON = re.compile(r"^\d{2}\s+[A-Z][a-z]{2}$")
RX_YEAR = re.compile(r"^\d{4}$")

# Same-row compact pattern:
# 01 Mar 2026 01 Mar 2026 VAT|| 291.97 - 1,057,411.47
RX_SINGLE_LINE_ROW = re.compile(
    r"^(?P<posted>\d{2}\s+[A-Z][a-z]{2}\s+\d{4})\s+"
    r"(?P<created>\d{2}\s+[A-Z][a-z]{2}\s+\d{4})\s+"
    r"(?P<narration>.*?)\s+"
    r"(?P<debit>-|[\d,]+\.\d{2})\s+"
    r"(?P<credit>-|[\d,]+\.\d{2})\s+"
    r"(?P<balance>[\d,]+\.\d{2})$"
)

# Tail money parser for buffered multiline rows
RX_MONEY_TAIL = re.compile(
    r"(?P<debit>-|[\d,]+\.\d{2})\s+"
    r"(?P<credit>-|[\d,]+\.\d{2})\s+"
    r"(?P<balance>[\d,]+\.\d{2})$"
)

# Header / noise
RX_SKIP_LINE = re.compile(
    r"^(?:"
    r"POSTED\s*$|DATE\s*$|CREATE\s*$|NARRATION\s+DEBIT\s+CREDIT\s+BALANCE\s*$|"
    r"ACCOUNT NUMBER:.*|"
    r"Inflow:.*|Outflow:.*|"
    r"INFLOW VS OUTFLOW.*|"
    r"FROM\s*$|TO\s*$|"
    r"Opening Balance\s*$|Closing Balance\s*$|"
    r"Current Balance\s*$|"
    r"\d{1,3}(?:,\d{3})*\.\d{2}\s*$"
    r")$",
    re.I,
)


# ----------------------------
# Helpers
# ----------------------------


def _clean_line(line: str) -> str:
    return re.sub(r"\s+", " ", (line or "").strip())


def _is_noise(line: str) -> bool:
    line = _clean_line(line)
    if not line:
        return True
    if RX_PAGE.match(line):
        return True
    if RX_SKIP_LINE.match(line):
        return True
    return False


def _combine_split_dates(lines: List[str]) -> List[str]:
    """
    Convert:
      09 Mar
      2026
    into:
      09 Mar 2026
    """
    out: List[str] = []
    i = 0
    while i < len(lines):
        cur = _clean_line(lines[i])

        if i + 1 < len(lines):
            nxt = _clean_line(lines[i + 1])
            if RX_DAY_MON.match(cur) and RX_YEAR.match(nxt):
                out.append(f"{cur} {nxt}")
                i += 2
                continue

        out.append(cur)
        i += 1

    return out


def _extract_reference(narration: str) -> str:
    """
    Stanbic often embeds references at the end of narration:
    ...|000012260305100246115715860480
    """
    parts = [p.strip() for p in narration.split("|") if p.strip()]
    if not parts:
        return ""

    last = parts[-1]
    if re.fullmatch(r"[A-Z0-9_/-]{10,}", last):
        return last

    m = re.search(r"\|([A-Z0-9_/-]{10,})$", narration)
    if m:
        return m.group(1)

    return ""


def _build_row(
    posted_date: str,
    created_date: str,
    narration_lines: List[str],
    money_line: str,
) -> Optional[Dict[str, str]]:
    narration = _clean_line(" ".join(narration_lines))
    money_line = _clean_line(money_line)

    m = RX_MONEY_TAIL.search(money_line)
    if not m:
        # Sometimes money may already be attached at end of narration string
        combined = _clean_line(f"{narration} {money_line}")
        m = RX_MONEY_TAIL.search(combined)
        if not m:
            print(
                f"(stanbic:model_02): Could not parse money tail: {combined}",
                file=sys.stderr,
            )
            return None
        narration = _clean_line(combined[: m.start()])

    debit_raw = m.group("debit")
    credit_raw = m.group("credit")
    balance_raw = m.group("balance")

    row = STANDARDIZED_ROW.copy()
    row["TXN_DATE"] = normalize_date(posted_date)
    row["VAL_DATE"] = normalize_date(created_date)
    row["REFERENCE"] = _extract_reference(narration)
    row["REMARKS"] = narration
    row["DEBIT"] = "0.00" if debit_raw == "-" else clean_money(debit_raw)
    row["CREDIT"] = "0.00" if credit_raw == "-" else clean_money(credit_raw)
    row["BALANCE"] = clean_money(balance_raw)
    row["Check"] = ""
    row["Check 2"] = ""

    return row


# ----------------------------
# Main parser
# ----------------------------


def parse(path: str) -> List[Dict[str, str]]:
    transactions: List[Dict[str, str]] = []

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                print(
                    f"(stanbic:model_02): Processing page {page_num}", file=sys.stderr
                )

                text = page.extract_text() or ""
                if not text.strip():
                    continue

                raw_lines = [_clean_line(x) for x in text.split("\n")]
                raw_lines = [x for x in raw_lines if not _is_noise(x)]
                lines = _combine_split_dates(raw_lines)

                i = 0
                while i < len(lines):
                    line = lines[i]

                    # Fast path for one-line rows
                    m_single = RX_SINGLE_LINE_ROW.match(line)
                    if m_single:
                        row = STANDARDIZED_ROW.copy()
                        narration = _clean_line(m_single.group("narration"))
                        row["TXN_DATE"] = normalize_date(m_single.group("posted"))
                        row["VAL_DATE"] = normalize_date(m_single.group("created"))
                        row["REFERENCE"] = _extract_reference(narration)
                        row["REMARKS"] = narration
                        row["DEBIT"] = (
                            "0.00"
                            if m_single.group("debit") == "-"
                            else clean_money(m_single.group("debit"))
                        )
                        row["CREDIT"] = (
                            "0.00"
                            if m_single.group("credit") == "-"
                            else clean_money(m_single.group("credit"))
                        )
                        row["BALANCE"] = clean_money(m_single.group("balance"))
                        row["Check"] = ""
                        row["Check 2"] = ""
                        transactions.append(row)
                        i += 1
                        continue

                    # Multiline row starts with posted date + created date
                    if RX_FULL_DATE.match(line):
                        if i + 1 < len(lines) and RX_FULL_DATE.match(lines[i + 1]):
                            posted_date = line
                            created_date = lines[i + 1]
                            i += 2

                            narration_buf: List[str] = []
                            money_line = ""

                            while i < len(lines):
                                cur = lines[i]

                                # next row starts
                                if RX_FULL_DATE.match(cur):
                                    # if next line is another date, stop row
                                    if i + 1 < len(lines) and RX_FULL_DATE.match(
                                        lines[i + 1]
                                    ):
                                        break

                                # money tail line
                                if RX_MONEY_TAIL.search(cur):
                                    money_line = cur
                                    i += 1
                                    break

                                narration_buf.append(cur)
                                i += 1

                            if narration_buf or money_line:
                                row = _build_row(
                                    posted_date=posted_date,
                                    created_date=created_date,
                                    narration_lines=narration_buf,
                                    money_line=money_line,
                                )
                                if row:
                                    transactions.append(row)
                            continue

                    i += 1

        # Statement is newest-first in the PDF, reverse to chronological order
        transactions.reverse()

        # Drop empty artifacts
        transactions = [
            t
            for t in transactions
            if t.get("TXN_DATE") or t.get("REMARKS") or t.get("BALANCE")
        ]

        return calculate_checks(transactions)

    except Exception as e:
        print(f"(stanbic:model_02): Fatal parse error: {e}", file=sys.stderr)
        return []
