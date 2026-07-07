import sys
import re
import pdfplumber
from typing import List, Dict, Optional

from utils import (
    normalize_date,
    normalize_money,
    to_float,
    calculate_checks,
)

# Matches: 25/Aug/2025
RX_ROW_START = re.compile(r"^\s*(\d{2}/[A-Za-z]{3}/\d{4})\b")

RX_HEADER_STRICT = re.compile(
    r"^\s*DATE\s+NARRATION\s+MONEY\s+OUT\s+MONEY\s+IN\s+BALANCE\s*$",
    re.IGNORECASE,
)

RX_FOOTER = re.compile(
    r"^\s*(Address Help Lines|Licensed by|Powered by)\b",
    re.IGNORECASE,
)

RX_MONEY = re.compile(r"[-]?\d{1,3}(?:,\d{3})*\.\d{2}|\b[-]?\d+\.\d{2}\b")

RX_OPENING_BALANCE = re.compile(
    r"\bOpening\s+Balanced?\s+([-]?\d{1,3}(?:,\d{3})*\.\d{2}|[-]?\d+\.\d{2})",
    re.IGNORECASE,
)


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _norm_altpro_date(d: str) -> str:
    return normalize_date((d or "").replace("/", "-"))


def _clean_narration(text: str) -> str:
    t = _norm_ws(text)
    t = RX_HEADER_STRICT.sub("", t).strip()
    return t


def _header_window_size(lines: List[str], i: int) -> int:
    """
    AltPro headers can extract as:
      DATE NARRATION MONEY OUT MONEY IN BALANCE

    or as:
      MONEY
      DATE NARRATION MONEY IN BALANCE
      OUT

    Return number of header lines to skip, or 0 if not a header.
    """
    for size in (1, 2, 3):
        window = _norm_ws(" ".join(lines[i : i + size]))
        upper = window.upper()

        if RX_HEADER_STRICT.search(window):
            return size

        required = ("DATE", "NARRATION", "MONEY", "OUT", "IN", "BALANCE")
        if all(token in upper for token in required):
            return size

    return 0


def _infer_direction_from_delta(
    prev_bal: Optional[float], bal: float, amt: float
) -> tuple[str, str]:
    if prev_bal is None:
        return "0.00", "0.00"

    delta = round(bal - prev_bal, 2)

    if delta < 0:
        return f"{abs(amt):.2f}", "0.00"

    if delta > 0:
        return "0.00", f"{abs(amt):.2f}"

    return "0.00", "0.00"


def _parse_txn_block(
    block_lines: List[str],
    prev_balance: Optional[float],
) -> tuple[Optional[Dict[str, str]], Optional[float]]:
    if not block_lines:
        return None, prev_balance

    date_idx = next(
        (idx for idx, ln in enumerate(block_lines) if RX_ROW_START.search(ln or "")),
        None,
    )

    if date_idx is None:
        return None, prev_balance

    pre_date_narration = " ".join(
        ln.strip() for ln in block_lines[:date_idx] if ln and ln.strip()
    ).strip()

    first_line = (block_lines[date_idx] or "").strip()
    post_lines = block_lines[date_idx + 1 :]

    m = RX_ROW_START.search(first_line)
    if not m:
        return None, prev_balance

    raw_date = m.group(1)
    txn_date = _norm_altpro_date(raw_date)
    val_date = txn_date

    after_date_first = first_line[m.end() :].strip()

    money_matches = list(RX_MONEY.finditer(after_date_first))
    if len(money_matches) < 2:
        return None, prev_balance

    bal_raw = money_matches[-1].group(0)
    amt_raw = money_matches[-2].group(0)

    bal = to_float(bal_raw)
    amt = to_float(amt_raw)

    first_money_start = money_matches[0].start()
    narration_first = after_date_first[:first_money_start].strip()

    continuation = " ".join(
        ln.strip() for ln in post_lines if ln and ln.strip()
    ).strip()

    narration = _clean_narration(
        f"{pre_date_narration} {narration_first} {continuation}".strip()
    )

    debit, credit = _infer_direction_from_delta(prev_balance, bal, amt)

    row = {
        "TXN_DATE": txn_date,
        "VAL_DATE": val_date,
        "REFERENCE": "",
        "REMARKS": narration,
        "DEBIT": normalize_money(debit),
        "CREDIT": normalize_money(credit),
        "BALANCE": f"{bal:.2f}",
        "Check": "",
        "Check 2": "",
    }

    return row, bal


def parse(path: str) -> List[Dict[str, str]]:
    txns: List[Dict[str, str]] = []
    prev_balance: Optional[float] = None

    in_table = False
    current_block: List[str] = []
    pending_narration: List[str] = []

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                print(
                    f"(altpro_model_01): Processing page {page_num}",
                    file=sys.stderr,
                )

                text = page.extract_text() or ""

                if prev_balance is None:
                    opening_match = RX_OPENING_BALANCE.search(text)
                    if opening_match:
                        prev_balance = to_float(opening_match.group(1))

                lines = text.splitlines()
                i = 0

                while i < len(lines):
                    line = lines[i]

                    if RX_FOOTER.search(line):
                        if current_block:
                            row, prev_balance = _parse_txn_block(
                                current_block,
                                prev_balance,
                            )
                            if row:
                                txns.append(row)
                            current_block = []

                        in_table = False
                        pending_narration = []
                        i += 1
                        continue

                    header_size = _header_window_size(lines, i)
                    if header_size:
                        if current_block:
                            row, prev_balance = _parse_txn_block(
                                current_block,
                                prev_balance,
                            )
                            if row:
                                txns.append(row)
                            current_block = []

                        in_table = True
                        pending_narration = []
                        i += header_size
                        continue

                    if not in_table:
                        i += 1
                        continue

                    if not line or not line.strip():
                        i += 1
                        continue

                    if RX_ROW_START.search(line):
                        if current_block:
                            row, prev_balance = _parse_txn_block(
                                current_block,
                                prev_balance,
                            )
                            if row:
                                txns.append(row)

                        current_block = pending_narration + [line]
                        pending_narration = []
                    else:
                        if current_block:
                            current_block.append(line)
                        else:
                            pending_narration.append(line)

                    i += 1

                if current_block:
                    row, prev_balance = _parse_txn_block(
                        current_block,
                        prev_balance,
                    )
                    if row:
                        txns.append(row)
                    current_block = []

        cleaned = [t for t in txns if t.get("TXN_DATE")]
        return calculate_checks(cleaned)

    except Exception as e:
        print(
            f"(altpro_model_01): Error processing statement: {e}",
            file=sys.stderr,
        )
        return []
