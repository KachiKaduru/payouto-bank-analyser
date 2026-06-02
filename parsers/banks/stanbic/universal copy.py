# banks/stanbic/universal.py
import sys
import re
import pdfplumber
from typing import List, Dict, Optional

from utils import normalize_date, to_float, parse_text_row, calculate_checks

# Patterns
DATE_TOKEN = re.compile(r"\b\d{2}[-/]\d{2}[-/]\d{4}\b")
DATE_LINE = re.compile(r"\b\d{2}[-/]\d{2}[-/]\d{4}\b.*\b\d{2}[-/]\d{2}[-/]\d{4}\b")
AMOUNT_RE = re.compile(r"\d{1,3}(?:,\d{3})*\.\d{2}(?:\s?(?:CR|DR))?", re.IGNORECASE)

FOOTER_PATTERNS = [
    re.compile(r"^Page\s+\d+\s+of", re.IGNORECASE),
    re.compile(r"You received this electronic Statement", re.IGNORECASE),
    re.compile(r"stanbicibtcbank\.com", re.IGNORECASE),
    re.compile(r"0700 CALL STANBIC", re.IGNORECASE),
]

HEADERS = ["TXN_DATE", "VAL_DATE", "REMARKS", "DEBIT", "CREDIT", "BALANCE"]


def is_footer(line: str) -> bool:
    if not line:
        return False
    for p in FOOTER_PATTERNS:
        if p.search(line):
            return True
    return False


def strip_cr_dr(s: str) -> str:
    return re.sub(r"\s*(CR|DR)\s*$", "", s, flags=re.IGNORECASE).strip()


def find_opening_balance_from_lines(lines: List[str]) -> Optional[float]:
    # Look for a line containing "Opening Balance" and extract the first amount on that line (or next tokens)
    for i, line in enumerate(lines):
        if "Opening Balance" in line:
            m = AMOUNT_RE.search(line)
            if m:
                return to_float(strip_cr_dr(m.group(0)))
            # maybe the next line contains the number
            if i + 1 < len(lines):
                m2 = AMOUNT_RE.search(lines[i + 1])
                if m2:
                    return to_float(strip_cr_dr(m2.group(0)))
    return None

def build_transaction(
    block_lines: List[str],
    date_idx_in_block: int,
    prev_balance: Optional[float],
    debug: bool = False,
) -> Optional[Dict[str, str]]:
    """
    block_lines: contiguous lines for this transaction block (includes desc_lines, date_line, post_lines)
    date_idx_in_block: index inside block_lines for the date_line
    """
    # date tokens
    date_line = block_lines[date_idx_in_block]
    date_tokens = DATE_TOKEN.findall(date_line)
    if len(date_tokens) < 2:
        if debug:
            print(
                f"(stanbic): build_transaction skipped: date_line has <2 dates: {date_line}",
                file=sys.stderr,
            )
        return None

    txn_date_raw = date_tokens[0]
    val_date_raw = date_tokens[1]

    # Collect amounts from date_line + post_lines (the block portion after date_line)
    tail_text = " ".join(block_lines[date_idx_in_block:])
    amounts = AMOUNT_RE.findall(tail_text)

    if not amounts:
        if debug:
            print(
                f"(stanbic): No amounts found in block for date_line: {date_line}",
                file=sys.stderr,
            )
        return None

    # last amount → balance, previous → amount (if available)
    balance_raw = strip_cr_dr(amounts[-1])
    amount_raw = strip_cr_dr(amounts[-2]) if len(amounts) >= 2 else None

    try:
        current_balance = to_float(balance_raw)
    except Exception:
        if debug:
            print(
                f"(stanbic): Could not parse balance '{balance_raw}' in: {tail_text}",
                file=sys.stderr,
            )
        return None

    amt_val = to_float(amount_raw) if amount_raw is not None else 0.0

    # Determine debit / credit using prev_balance if available
    debit = "0.00"
    credit = "0.00"
    if prev_balance is not None:
        # If balance decreased relative to previous balance → debit
        if current_balance < prev_balance:
            debit = f"{abs(amt_val):.2f}"
        else:
            credit = f"{abs(amt_val):.2f}"
    else:
        # If we have no prev_balance, assume debit by default (keeps legacy behaviour)
        debit = f"{abs(amt_val):.2f}"

    # Build remarks: desc lines (before date_idx) + post lines (after date_idx), filtered
    desc_lines = [
        l
        for l in block_lines[:date_idx_in_block]
        if l and not is_footer(l) and "Posting Date" not in l
    ]
    post_lines = [
        l
        for l in block_lines[date_idx_in_block + 1 :]
        if l and not is_footer(l) and "Posting Date" not in l
    ]

    # remove any leading/trailing stray amount tokens from remarks (they'll be parsed from amounts list)
    # join with newline to keep structure
    remarks = "\n".join([ln.strip() for ln in (desc_lines + post_lines)]).strip()

    row = [
        normalize_date(txn_date_raw),
        normalize_date(val_date_raw),
        remarks,
        debit,
        credit,
        f"{current_balance:.2f}",
    ]

    parsed = parse_text_row(row, HEADERS)
    if debug:
        print(
            f"(stanbic DEBUG) Built txn: TXN={parsed['TXN_DATE']} VAL={parsed['VAL_DATE']} AMT={amount_raw} BAL={balance_raw} REMARKS preview={parsed['REMARKS'][:60]!r}",
            file=sys.stderr,
        )
    return parsed


def parse(path: str, debug: bool = False) -> List[Dict[str, str]]:
    transactions: List[Dict[str, str]] = []
    prev_balance: Optional[float] = None

    try:
        with pdfplumber.open(path) as pdf:
            # Pre-scan entire document for Opening Balance (safe seed for prev_balance)
            all_lines_for_opening: List[str] = []
            for p in pdf.pages[
                :3
            ]:  # usually opening balance is on first page - check first 3 pages to be safe
                word_lines = {}
                for w in p.extract_words(
                    x_tolerance=2, y_tolerance=3, keep_blank_chars=True
                ):
                    word_lines.setdefault(round(w["top"], 1), []).append(w)
                page_lines = [
                    " ".join(w["text"] for w in sorted(ws, key=lambda x: x["x0"]))
                    for _, ws in sorted(word_lines.items())
                ]
                all_lines_for_opening.extend(page_lines)
            opening = find_opening_balance_from_lines(all_lines_for_opening)
            if opening is not None:
                prev_balance = opening
                if debug:
                    print(
                        f"(stanbic): Found Opening Balance = {prev_balance:.2f}",
                        file=sys.stderr,
                    )

            for page_num, page in enumerate(pdf.pages, start=1):
                if debug:
                    print(f"(stanbic): Processing page {page_num}", file=sys.stderr)

                # build visual lines ordered by Y coordinate
                word_lines = {}
                for w in page.extract_words(
                    x_tolerance=2, y_tolerance=3, keep_blank_chars=True
                ):
                    word_lines.setdefault(round(w["top"], 1), []).append(w)

                lines = [
                    " ".join(w["text"] for w in sorted(ws, key=lambda x: x["x0"]))
                    for y, ws in sorted(word_lines.items())
                ]

                # find transactions header
                header_idx = None
                for i, ln in enumerate(lines):
                    if "Posting Date" in ln and "Balance" in ln:
                        header_idx = i
                        break
                    if "TRANSACTIONS" in ln:
                        header_idx = i
                        break

                if header_idx is None:
                    # no transaction header on this page — skip unless there are date-lines anyway
                    # but to avoid pulling page summaries, we skip pages without header
                    if debug:
                        print(
                            f"(stanbic): No transaction header on page {page_num}, skipping",
                            file=sys.stderr,
                        )
                    continue

                start = header_idx + 1
                # build date indices (lines containing two date tokens)
                date_indices = [
                    i for i in range(start, len(lines)) if DATE_LINE.search(lines[i])
                ]

                if not date_indices:
                    if debug:
                        print(
                            f"(stanbic): No date-lines found on page {page_num}",
                            file=sys.stderr,
                        )
                    continue

                # build blocks and parse
                for pos, date_idx in enumerate(date_indices):
                    block_start = start if pos == 0 else date_indices[pos - 1] + 1
                    block_end = (
                        date_indices[pos + 1] - 1
                        if pos + 1 < len(date_indices)
                        else len(lines) - 1
                    )

                    # trim footer lines at block_end
                    while block_end >= date_idx and is_footer(lines[block_end]):
                        block_end -= 1

                    block_lines = [
                        lines[i]
                        for i in range(block_start, block_end + 1)
                        if lines[i].strip() and not is_footer(lines[i])
                    ]

                    # find index of date line inside block_lines
                    # date_idx_in_block = index of the line containing the two dates
                    # (map global index to block index)
                    try:
                        date_idx_in_block = next(
                            idx
                            for idx, _ in enumerate(block_lines)
                            if DATE_LINE.search(block_lines[idx])
                        )
                    except StopIteration:
                        # fallback: try to locate by matching the original global date line
                        # compute global line for this date_idx and find it
                        global_date_line = lines[date_idx]
                        try:
                            date_idx_in_block = block_lines.index(global_date_line)
                        except ValueError:
                            if debug:
                                print(
                                    f"(stanbic): Could not locate date-line inside its block (page {page_num}), skipping block.",
                                    file=sys.stderr,
                                )
                            continue

                    txn = build_transaction(
                        block_lines, date_idx_in_block, prev_balance, debug=debug
                    )
                    if txn:
                        transactions.append(txn)
                        try:
                            prev_balance = to_float(txn["BALANCE"])
                        except Exception:
                            # leave prev_balance unchanged if parse fails
                            pass

    except Exception as e:
        print(f"Error processing Stanbic statement: {e}", file=sys.stderr)
        return []

    # final checks and normalization
    return calculate_checks(transactions)
