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
RX_HEADER = re.compile(
    r"^\s*DATE\s+NARRATION\s+MONEY\s+OUT\s+MONEY\s+IN\s+BALANCE\s*$", re.IGNORECASE
)
RX_FOOTER = re.compile(
    r"^\s*(Address Help Lines|Licensed by|Powered by)\b", re.IGNORECASE
)

# Money tokens like 1,234.56 or 50.00 or 0.75
RX_MONEY = re.compile(r"[-]?\d{1,3}(?:,\d{3})*\.\d{2}|\b[-]?\d+\.\d{2}\b")


def _norm_altpro_date(d: str) -> str:
    """
    AltPro uses dd/Mon/yyyy (e.g., 25/Aug/2025).
    Your normalize_date supports %d-%b-%Y, so convert slash to dash first.
    """
    return normalize_date((d or "").replace("/", "-"))


def _clean_narration(text: str) -> str:
    # Collapse whitespace, remove repeated headers if they leak in
    t = re.sub(r"\s+", " ", text or "").strip()
    t = re.sub(RX_HEADER, "", t).strip()
    return t


def _infer_direction_from_delta(
    prev_bal: Optional[float], bal: float, amt: float
) -> tuple[str, str]:
    """
    Returns (debit, credit) as strings.
    If we have prev balance, use delta sign. Otherwise default 0.00/0.00 (safe for checks).
    """
    if prev_bal is None:
        return "0.00", "0.00"

    delta = round(bal - prev_bal, 2)
    # Amount should match abs(delta) but we trust amt from PDF and just use delta sign
    if delta < 0:
        return f"{abs(amt):.2f}", "0.00"
    elif delta > 0:
        return "0.00", f"{abs(amt):.2f}"
    else:
        # No movement
        return "0.00", "0.00"


def _parse_txn_block(
    block_lines: List[str], prev_balance: Optional[float]
) -> tuple[Optional[Dict[str, str]], Optional[float]]:
    """
    AltPro rows behave like:
      FIRST LINE:  DATE + NARRATION + (MONEY OUT or MONEY IN) + BALANCE
      NEXT LINES:  narration continuation (no reliable column demarcation in extracted text)

    Fix: parse numeric tokens ONLY from the first line of the block.
    - BALANCE = last money token on first line (after the date)
    - AMOUNT  = money token immediately before BALANCE
    - REMARKS = text between date and first money token on first line + continuation lines
    """
    if not block_lines:
        return None, prev_balance

    first_line = (block_lines[0] or "").strip()
    if not first_line:
        return None, prev_balance

    m = RX_ROW_START.search(first_line)
    if not m:
        return None, prev_balance

    raw_date = m.group(1)
    txn_date = _norm_altpro_date(raw_date)
    val_date = txn_date  # no VAL_DATE column

    # Work only on the portion after the date on the FIRST line
    after_date_first = first_line[m.end() :].strip()

    # Find money tokens WITH SPANS so we can slice narration safely
    money_matches = list(RX_MONEY.finditer(after_date_first))
    if len(money_matches) < 2:
        # Not enough numeric structure to be a transaction row
        return None, prev_balance

    bal_match = money_matches[-1]
    amt_match = money_matches[-2]

    bal_raw = bal_match.group(0)
    amt_raw = amt_match.group(0)

    bal = to_float(bal_raw)
    amt = to_float(amt_raw)

    # Narration on first line is everything BEFORE the first money token
    first_money_start = money_matches[0].start()
    narration_first = after_date_first[:first_money_start].strip()

    # Continuation narration lines (if any) — do NOT attempt numeric parsing on them
    continuation = " ".join(
        ln.strip() for ln in block_lines[1:] if ln and ln.strip()
    ).strip()

    narration = _clean_narration(f"{narration_first} {continuation}".strip())

    # Debit/Credit via balance delta sign (reliable)
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
    """
    AltPro statement parser (model_01):
    - Text-table parsing using date-led row blocks
    - TXN_DATE used as VAL_DATE
    """
    txns: List[Dict[str, str]] = []
    prev_balance: Optional[float] = None

    in_table = False
    current_block: List[str] = []

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                print(f"(altpro_model_01): Processing page {page_num}", file=sys.stderr)

                text = page.extract_text() or ""
                lines = text.splitlines()

                for line in lines:
                    if RX_FOOTER.search(line):
                        # End parsing when footer section starts
                        in_table = False
                        continue

                    if RX_HEADER.search(line):
                        # Flush any pending block before resetting
                        if current_block:
                            row, prev_balance = _parse_txn_block(
                                current_block, prev_balance
                            )
                            if row:
                                txns.append(row)
                            current_block = []
                        in_table = True
                        continue

                    if not in_table:
                        continue

                    # Skip repeated header lines that appear mid-stream
                    if RX_HEADER.search(line):
                        continue

                    if RX_ROW_START.search(line):
                        # New transaction starts; flush old block
                        if current_block:
                            row, prev_balance = _parse_txn_block(
                                current_block, prev_balance
                            )
                            if row:
                                txns.append(row)
                        current_block = [line]
                    else:
                        # Continuation of narration, or spacing artifacts
                        if current_block:
                            current_block.append(line)

                # End of page flush (keep prev_balance across pages)
                if current_block:
                    row, prev_balance = _parse_txn_block(current_block, prev_balance)
                    if row:
                        txns.append(row)
                    current_block = []

        # Final normalization and check computation
        # Only keep rows with a parsed date
        cleaned = [t for t in txns if t.get("TXN_DATE")]
        return calculate_checks(cleaned)

    except Exception as e:
        print(f"(altpro_model_01): Error processing statement: {e}", file=sys.stderr)
        return []
