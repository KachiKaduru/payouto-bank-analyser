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

# --------------------------------------------------
# Regex
# --------------------------------------------------

RX_PAGE = re.compile(r"^Page\s+\d+\s+of\s+\d+$", re.I)

# Repeated table header
RX_HEADER = re.compile(r"POSTED\s+CREATE\s+NARRATION\s+DEBIT\s+CREDIT\s+BALANCE", re.I)
RX_HEADER_DATES = re.compile(r"^DATE\s+DATE$", re.I)

# Transaction start:
#   09 Mar 09 Mar ...
#   27 Feb 2026 26 Feb ...
#   01 Jan 2026 01 Jan 2026 ...
RX_ROW_START = re.compile(
    r"^(?P<posted>\d{2}\s+[A-Z][a-z]{2}(?:\s+\d{4})?)\s+"
    r"(?P<created>\d{2}\s+[A-Z][a-z]{2}(?:\s+\d{4})?)\s+"
    r"(?P<rest>.*)$"
)

# Tail money parser.
# Handles:
#   50.00 - 5,333.76
#   - 640,000.00 645,025.28
#   516.37-581,739.69
RX_MONEY_TAIL = re.compile(
    r"(?P<debit>-|[\d,]+\.\d{2})\s*"
    r"(?P<credit>-|[\d,]+\.\d{2})\s*"
    r"(?P<balance>[\d,]+\.\d{2})$"
)

RX_YEAR_ONLY = re.compile(r"^\d{4}$")

# Summary/noise lines before the first table header on page 1
RX_SKIP_PRE_TABLE = re.compile(
    r"^(?:"
    r"MS\..*|"
    r"ACCOUNT NUMBER:.*|"
    r"INFLOW VS OUTFLOW.*|"
    r"Inflow:.*|"
    r"Outflow:.*|"
    r"FROM\s+TO|"
    r"Opening Balance.*|"
    r"Closing Balance.*|"
    r"Current Balance.*|"
    r"\d{1,3}(?:,\d{3})*\.\d{2}|"
    r"\d{2}\s+[A-Z][a-z]{2}\s+\d{4}"
    r")$",
    re.I,
)


# --------------------------------------------------
# Helpers
# --------------------------------------------------


def _clean_line(line: str) -> str:
    return re.sub(r"\s+", " ", (line or "").replace("\xa0", " ").strip())


def _starts_new_row(line: str) -> bool:
    return bool(RX_ROW_START.match(_clean_line(line)))


def _extract_lines_after_header(page_text: str) -> List[str]:
    """
    Return only lines after the repeated transaction header on the page.
    This avoids page-1 summary blocks entirely.
    """
    raw_lines = [_clean_line(x) for x in (page_text or "").split("\n")]
    raw_lines = [x for x in raw_lines if x]

    found_header = False
    out: List[str] = []

    for line in raw_lines:
        if RX_HEADER.search(line):
            found_header = True
            continue

        if not found_header:
            continue

        if RX_HEADER_DATES.match(line):
            continue

        if RX_PAGE.match(line):
            continue

        out.append(line)

    return out


def _append_continuation(
    narration_parts: List[str],
    continuation_lines: List[str],
    posted_stub: str,
    created_stub: str,
) -> tuple[str, str, str]:
    """
    Use continuation lines to:
    - fill in missing years for posted/created date stubs
    - append narration continuation text
    """
    posted_has_year = bool(re.search(r"\b\d{4}$", posted_stub))
    created_has_year = bool(re.search(r"\b\d{4}$", created_stub))

    for line in continuation_lines:
        line = _clean_line(line)
        if not line:
            continue

        tokens = line.split()
        idx = 0

        # Fill missing years only from the start of continuation lines
        if (
            not posted_has_year
            and idx < len(tokens)
            and RX_YEAR_ONLY.match(tokens[idx])
        ):
            posted_stub = f"{posted_stub} {tokens[idx]}"
            posted_has_year = True
            idx += 1

        if (
            not created_has_year
            and idx < len(tokens)
            and RX_YEAR_ONLY.match(tokens[idx])
        ):
            created_stub = f"{created_stub} {tokens[idx]}"
            created_has_year = True
            idx += 1

        remainder = " ".join(tokens[idx:]).strip()
        if remainder:
            narration_parts.append(remainder)

    narration = _clean_line(" ".join(narration_parts))
    return posted_stub, created_stub, narration


def _build_row(row_lines: List[str]) -> Optional[Dict[str, str]]:
    """
    A transaction buffer always begins with a line matching RX_ROW_START.
    Example row buffers:

      09 Mar 09 Mar CBN STAMPDUTY09MAR2026/ 50.00 - 5,333.76
      2026 2026 01151223|20260309_ 01151223_
      1_NG13907108|Org. Amt: 639319

    or

      01 Jan 2026 01 Jan 2026 VAT|| 516.37-581,739.69

    or carried across pages:
      24 Dec 24 Dec NIP-FEE FOR EOLBI-250.00-282,429.46
      2025 2025 25122421540743372|EOLWI25122422050220684|E
      OLWI25122422050220684
    """
    if not row_lines:
        return None

    first_line = _clean_line(row_lines[0])
    m = RX_ROW_START.match(first_line)
    if not m:
        return None

    posted_stub = m.group("posted")
    created_stub = m.group("created")
    first_rest = _clean_line(m.group("rest"))

    money_match = RX_MONEY_TAIL.search(first_rest)
    if not money_match:
        print(
            f"(stanbic:model_02): Could not parse money tail from first row line: {first_line}",
            file=sys.stderr,
        )
        return None

    narration_parts = [_clean_line(first_rest[: money_match.start()])]
    continuation_lines = row_lines[1:]

    posted_stub, created_stub, narration = _append_continuation(
        narration_parts=narration_parts,
        continuation_lines=continuation_lines,
        posted_stub=posted_stub,
        created_stub=created_stub,
    )

    debit_raw = money_match.group("debit")
    credit_raw = money_match.group("credit")
    balance_raw = money_match.group("balance")

    row = STANDARDIZED_ROW.copy()
    row["TXN_DATE"] = normalize_date(posted_stub)
    row["VAL_DATE"] = normalize_date(created_stub)

    # Keep blank for this model unless you later decide to mine reference IDs.
    row["REFERENCE"] = ""

    row["REMARKS"] = narration
    row["DEBIT"] = "0.00" if debit_raw == "-" else clean_money(debit_raw)
    row["CREDIT"] = "0.00" if credit_raw == "-" else clean_money(credit_raw)
    row["BALANCE"] = clean_money(balance_raw)
    row["Check"] = ""
    row["Check 2"] = ""

    return row


# --------------------------------------------------
# Main parser
# --------------------------------------------------


def parse(path: str) -> List[Dict[str, str]]:
    transactions: List[Dict[str, str]] = []
    current_row_lines: List[str] = []

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                print(
                    f"(stanbic:model_02): Processing page {page_num}", file=sys.stderr
                )

                text = page.extract_text() or ""
                if not text.strip():
                    continue

                lines = _extract_lines_after_header(text)

                for line in lines:
                    line = _clean_line(line)
                    if not line:
                        continue

                    # New transaction row begins
                    if _starts_new_row(line):
                        if current_row_lines:
                            row = _build_row(current_row_lines)
                            if row:
                                transactions.append(row)

                        current_row_lines = [line]
                        continue

                    # Continuation of previous row, including page-carryover rows
                    if current_row_lines:
                        current_row_lines.append(line)
                    else:
                        # Stray text after header before any valid row start
                        # ignore safely
                        continue

        # Flush last buffered row
        if current_row_lines:
            row = _build_row(current_row_lines)
            if row:
                transactions.append(row)

        # Statement is newest -> oldest in the PDF
        transactions.reverse()

        # Remove obvious empty artifacts
        transactions = [
            t
            for t in transactions
            if t.get("TXN_DATE")
            or t.get("VAL_DATE")
            or t.get("REMARKS")
            or t.get("BALANCE")
        ]

        return calculate_checks(transactions)

    except Exception as e:
        print(f"(stanbic:model_02): Fatal parse error: {e}", file=sys.stderr)
        return []
