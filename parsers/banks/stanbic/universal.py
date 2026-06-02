# banks/stanbic/universal.py  (optimized)
import sys
import re
import pdfplumber
from typing import List, Dict, Optional, Tuple

from utils import normalize_date, to_float, calculate_checks

# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------
DATE_TOKEN = re.compile(r"\b\d{2}[-/]\d{2}[-/]\d{4}\b")
# Requires exactly two date tokens on the same line
DATE_LINE = re.compile(r"\b(\d{2}[-/]\d{2}[-/]\d{4})\b.+?\b(\d{2}[-/]\d{2}[-/]\d{4})\b")
AMOUNT_RE = re.compile(r"\d{1,3}(?:,\d{3})*\.\d{2}(?:\s?(?:CR|DR))?", re.IGNORECASE)
STRIP_CR_DR = re.compile(r"\s*(CR|DR)\s*$", re.IGNORECASE)

# Single combined footer pattern (one RE is faster than iterating four)
_FOOTER_PAT = re.compile(
    r"Page\s+\d+\s+of"
    r"|You received this electronic Statement"
    r"|stanbicibtcbank\.com"
    r"|0700 CALL STANBIC",
    re.IGNORECASE,
)

# Header sentinel patterns
_HEADER_PAT = re.compile(r"Posting Date.*Balance|TRANSACTIONS", re.IGNORECASE)

HEADERS = ["TXN_DATE", "VAL_DATE", "REMARKS", "DEBIT", "CREDIT", "BALANCE"]

# ---------------------------------------------------------------------------
# Tiny helpers
# ---------------------------------------------------------------------------


def is_footer(line: str) -> bool:
    return bool(line and _FOOTER_PAT.search(line))


def strip_cr_dr(s: str) -> str:
    return STRIP_CR_DR.sub("", s).strip()


# ---------------------------------------------------------------------------
# Word-line extraction  (shared utility, called once per page)
# ---------------------------------------------------------------------------


def _extract_lines(page) -> List[str]:
    """Return visual text lines sorted by Y, words sorted by X."""
    buckets: Dict[float, list] = {}
    for w in page.extract_words(x_tolerance=2, y_tolerance=3, keep_blank_chars=True):
        key = round(w["top"], 1)
        try:
            buckets[key].append(w)
        except KeyError:
            buckets[key] = [w]

    return [
        " ".join(w["text"] for w in sorted(ws, key=lambda x: x["x0"]))
        for ws in (v for _, v in sorted(buckets.items()))
    ]


# ---------------------------------------------------------------------------
# Opening-balance scan
# ---------------------------------------------------------------------------


def _find_opening_balance(lines: List[str]) -> Optional[float]:
    """Return the first monetary amount after an 'Opening Balance' marker."""
    for i, line in enumerate(lines):
        if "Opening Balance" not in line:
            continue
        m = AMOUNT_RE.search(line)
        if m:
            return to_float(strip_cr_dr(m.group(0)))
        if i + 1 < len(lines):
            m2 = AMOUNT_RE.search(lines[i + 1])
            if m2:
                return to_float(strip_cr_dr(m2.group(0)))
    return None


# ---------------------------------------------------------------------------
# Transaction builder
# ---------------------------------------------------------------------------


def _build_transaction(
    block_lines: List[str],
    date_idx_in_block: int,
    prev_balance: Optional[float],
    debug: bool,
) -> Optional[Dict[str, str]]:
    date_line = block_lines[date_idx_in_block]

    # Use capturing-group DATE_LINE to avoid a second findall
    m = DATE_LINE.search(date_line)
    if not m:
        if debug:
            print(f"(stanbic): skipped – <2 dates: {date_line}", file=sys.stderr)
        return None

    txn_date_raw, val_date_raw = m.group(1), m.group(2)

    # Scan only the tail portion (date line onward) for amounts
    tail_lines = block_lines[date_idx_in_block:]
    amounts = []
    for ln in tail_lines:
        amounts.extend(AMOUNT_RE.findall(ln))

    if not amounts:
        if debug:
            print(f"(stanbic): no amounts for: {date_line}", file=sys.stderr)
        return None

    balance_raw = strip_cr_dr(amounts[-1])
    amount_raw = strip_cr_dr(amounts[-2]) if len(amounts) >= 2 else None

    try:
        current_balance = float(balance_raw.replace(",", ""))
    except ValueError:
        try:
            current_balance = to_float(balance_raw)
        except Exception:
            if debug:
                print(f"(stanbic): bad balance '{balance_raw}'", file=sys.stderr)
            return None

    amt_val = to_float(amount_raw) if amount_raw is not None else 0.0

    if prev_balance is not None:
        if current_balance < prev_balance:
            debit = f"{abs(amt_val):.2f}"
            credit = "0.00"
        else:
            debit = "0.00"
            credit = f"{abs(amt_val):.2f}"
    else:
        debit = f"{abs(amt_val):.2f}"
        credit = "0.00"

    # Remarks: lines before + after the date line, footers excluded
    desc_lines = [
        l.strip()
        for l in block_lines[:date_idx_in_block]
        if l and not is_footer(l) and "Posting Date" not in l
    ]
    post_lines = [
        l.strip()
        for l in block_lines[date_idx_in_block + 1 :]
        if l and not is_footer(l) and "Posting Date" not in l
    ]
    remarks = "\n".join(desc_lines + post_lines).strip()

    # normalize_date already called on raw strings – do it once here
    txn_date = normalize_date(txn_date_raw)
    val_date = normalize_date(val_date_raw)
    bal_str = f"{current_balance:.2f}"

    row = {
        "TXN_DATE": txn_date,
        "VAL_DATE": val_date,
        "REFERENCE": "",
        "REMARKS": remarks,
        "DEBIT": debit,
        "CREDIT": credit,
        "BALANCE": bal_str,
        "Check": "",
        "Check 2": "",
    }

    if debug:
        print(
            f"(stanbic DEBUG) TXN={txn_date} VAL={val_date} "
            f"AMT={amount_raw} BAL={balance_raw} REM={remarks[:60]!r}",
            file=sys.stderr,
        )
    return row


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def parse(path: str, debug: bool = False) -> List[Dict[str, str]]:
    transactions: List[Dict[str, str]] = []
    prev_balance: Optional[float] = None

    # Cache extracted lines per page index so pages 0-2 are not re-extracted
    # during the opening-balance pre-scan and the main loop.
    page_lines_cache: Dict[int, List[str]] = {}

    try:
        with pdfplumber.open(path) as pdf:
            n_pages = len(pdf.pages)

            # ── Opening-balance pre-scan (first ≤3 pages) ──────────────────
            prescan_lines: List[str] = []
            for i in range(min(3, n_pages)):
                lines = _extract_lines(pdf.pages[i])
                page_lines_cache[i] = lines  # reuse below
                prescan_lines.extend(lines)

            opening = _find_opening_balance(prescan_lines)
            if opening is not None:
                prev_balance = opening
                if debug:
                    print(
                        f"(stanbic): Opening Balance = {prev_balance:.2f}",
                        file=sys.stderr,
                    )

            # ── Main page loop ──────────────────────────────────────────────
            for page_num in range(n_pages):
                if debug:
                    print(f"(stanbic): Processing page {page_num + 1}", file=sys.stderr)

                # Use cached lines when available
                lines = page_lines_cache.get(page_num) or _extract_lines(
                    pdf.pages[page_num]
                )

                # Locate transaction-header line
                header_idx: Optional[int] = None
                for i, ln in enumerate(lines):
                    if _HEADER_PAT.search(ln):
                        header_idx = i
                        break

                if header_idx is None:
                    if debug:
                        print(
                            f"(stanbic): No header on page {page_num + 1}, skipping",
                            file=sys.stderr,
                        )
                    continue

                start = header_idx + 1

                # Collect indices of lines that contain two date tokens
                date_indices: List[int] = [
                    i for i in range(start, len(lines)) if DATE_LINE.search(lines[i])
                ]

                if not date_indices:
                    if debug:
                        print(
                            f"(stanbic): No date-lines on page {page_num + 1}",
                            file=sys.stderr,
                        )
                    continue

                n_dates = len(date_indices)

                for pos in range(n_dates):
                    date_idx = date_indices[pos]
                    block_start = start if pos == 0 else date_indices[pos - 1] + 1
                    block_end = (
                        date_indices[pos + 1] - 1
                        if pos + 1 < n_dates
                        else len(lines) - 1
                    )

                    # Trim trailing footer lines
                    while block_end >= date_idx and is_footer(lines[block_end]):
                        block_end -= 1

                    # Build block, filtering empties and footers in one pass
                    block_lines: List[str] = []
                    date_idx_in_block: Optional[int] = None

                    for gi in range(block_start, block_end + 1):
                        ln = lines[gi]
                        if not ln.strip() or is_footer(ln):
                            continue
                        if gi == date_idx:
                            date_idx_in_block = len(block_lines)
                        block_lines.append(ln)

                    # Fallback: scan for first DATE_LINE inside block
                    if date_idx_in_block is None:
                        for idx, bl in enumerate(block_lines):
                            if DATE_LINE.search(bl):
                                date_idx_in_block = idx
                                break

                    if date_idx_in_block is None:
                        if debug:
                            print(
                                f"(stanbic): date-line missing from block (page {page_num + 1}), skipping",
                                file=sys.stderr,
                            )
                        continue

                    txn = _build_transaction(
                        block_lines, date_idx_in_block, prev_balance, debug
                    )
                    if txn:
                        transactions.append(txn)
                        try:
                            prev_balance = float(txn["BALANCE"].replace(",", ""))
                        except ValueError:
                            prev_balance = to_float(txn["BALANCE"])

    except Exception as e:
        print(f"Error processing Stanbic statement: {e}", file=sys.stderr)
        return []

    return calculate_checks(transactions)
