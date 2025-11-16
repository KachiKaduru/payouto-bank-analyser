# banks/stanbic/universal.py
import sys
import re
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from copy import deepcopy

import pdfplumber

from utils import normalize_date, to_float, parse_text_row, calculate_checks

# ----------------------------
# Patterns & constants
# ----------------------------
DATE_TOKEN = re.compile(r"\b\d{2}[-/]\d{2}[-/]\d{4}\b")
DATE_LINE = re.compile(r"\b\d{2}[-/]\d{2}[-/]\d{4}\b.*\b\d{2}[-/]\d{2}[-/]\d{4}\b")
AMOUNT_RE = re.compile(r"\d{1,3}(?:,\d{3})*\.\d{2}(?:\s?(?:CR|DR))?", re.IGNORECASE)

FOOTER_PATTERNS = [
    re.compile(r"^Page\s+\d+\s+of", re.IGNORECASE),
    re.compile(r"You received this electronic Statement", re.IGNORECASE),
    re.compile(r"stanbicibtcbank\.com", re.IGNORECASE),
    re.compile(r"0700\s*CALL\s*STANBIC", re.IGNORECASE),
    re.compile(r"Customer\s*Contact\s*Centre", re.IGNORECASE),
]

HEADERS = ["TXN_DATE", "VAL_DATE", "REMARKS", "DEBIT", "CREDIT", "BALANCE"]

SKIP_REMARKS = re.compile(
    r"^(BALANCE (BROUGHT FORWARD|AS AT)|STATEMENT OPENING BALANCE)\b",
    re.IGNORECASE,
)


# ----------------------------
# Small helpers
# ----------------------------
def is_footer(line: str) -> bool:
    if not line:
        return False
    for p in FOOTER_PATTERNS:
        if p.search(line):
            return True
    return False


def strip_cr_dr(s: str) -> str:
    return re.sub(r"\s*(CR|DR)\s*$", "", s, flags=re.IGNORECASE).strip()


def _parse_amount(s: Optional[str]) -> Optional[float]:
    """Extract first amount-like token from s and return as float (using to_float)."""
    if not s:
        return None
    s2 = s.replace(" ", "")
    m = AMOUNT_RE.search(s2)
    if not m:
        return None
    try:
        return to_float(strip_cr_dr(m.group(0)))
    except Exception:
        return None


def find_opening_balance_from_lines(lines: List[str]) -> Optional[float]:
    """
    Look for 'Opening Balance' and read the first amount on that line (or the next line).
    """
    for i, line in enumerate(lines):
        if "Opening Balance" in line or "STATEMENT OPENING BALANCE" in line:
            m = AMOUNT_RE.search(line.replace(" ", ""))
            if m:
                return to_float(strip_cr_dr(m.group(0)))
            if i + 1 < len(lines):
                m2 = AMOUNT_RE.search(lines[i + 1].replace(" ", ""))
                if m2:
                    return to_float(strip_cr_dr(m2.group(0)))
    return None


# ----------------------------
# Block-based builder (your original logic)
# ----------------------------
def build_transaction(
    block_lines: List[str],
    date_idx_in_block: int,
    prev_balance: Optional[float],
    debug: bool = False,
) -> Optional[Dict[str, str]]:
    """
    Build a transaction from a contiguous text block, assuming the 'date line' contains two dates.
    """
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

    # Collect amounts from date_line + post_lines
    tail_text = " ".join(block_lines[date_idx_in_block:])
    amounts = AMOUNT_RE.findall(tail_text.replace(" ", ""))

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
        if current_balance < prev_balance:
            debit = f"{abs(amt_val):.2f}"
        else:
            credit = f"{abs(amt_val):.2f}"
    else:
        # default if we can't infer
        debit = f"{abs(amt_val):.2f}"

    # remarks = everything but the date line, minus footers
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


# ----------------------------
# Grid mode (column-aware) — for this Stanbic variant
# ----------------------------
@dataclass
class ColBox:
    name: str
    x0: float
    x1: float


def _line_groups(page) -> List[Tuple[float, List[dict]]]:
    """
    Return list of (y, [word dicts sorted by x0]) sorted by y.
    """
    buckets: Dict[float, List[dict]] = {}
    for w in page.extract_words(x_tolerance=2, y_tolerance=3, keep_blank_chars=True):
        buckets.setdefault(round(w["top"], 1), []).append(w)
    return [(y, sorted(ws, key=lambda x: x["x0"])) for y, ws in sorted(buckets.items())]


# Header matching expects the usual Stanbic words; conservative check
HEADER_KEYS = [
    ("Transaction", "date"),
    ("Value", "Date"),
    ("Transaction", "description"),
    ("Fee",),
    ("Debits",),
    ("Credits",),
    ("Balance",),
]


def _match_header(words: List[dict]) -> Optional[List[Tuple[float, float, str]]]:
    """
    Try to match the 7-column Stanbic header on a single 'line' of words.
    Return [(x0, x1, label_text), ...] or None.
    """
    text = " ".join(w["text"] for w in words)
    must_have = ["Transaction", "Value", "description", "Debits", "Credits", "Balance"]
    if not all(k.lower() in text.lower() for k in must_have):
        return None

    groups = []
    i = 0
    for keys in HEADER_KEYS:
        seg = []
        acc = ""
        while i < len(words):
            nxt = words[i]
            test = (acc + " " + nxt["text"]).strip()
            if all(k.lower() in test.lower() for k in keys):
                seg.append(nxt)
                acc = test
                i += 1
                break
            seg.append(nxt)
            acc = test
            i += 1
        if not seg:
            return None
        groups.append((seg[0]["x0"], seg[-1]["x1"], " ".join(w["text"] for w in seg)))
    if len(groups) != 7:
        return None
    return groups


def _build_col_boxes(header_groups: List[Tuple[float, float, str]]) -> List[ColBox]:
    bounds = sorted(header_groups, key=lambda t: t[0])
    boxes: List[ColBox] = []
    for idx, (x0, x1, _label) in enumerate(bounds):
        left = x0 if idx == 0 else (bounds[idx - 1][1] + x0) / 2
        right = x1 if idx == len(bounds) - 1 else (x1 + bounds[idx + 1][0]) / 2
        name = ["TXN_DATE", "VAL_DATE", "REMARKS", "FEE", "DEBIT", "CREDIT", "BALANCE"][
            idx
        ]
        boxes.append(ColBox(name=name, x0=left, x1=right))
    return boxes


def _slice_col_text(words: List[dict], col: ColBox) -> str:
    parts = [w["text"] for w in words if w["x0"] >= col.x0 and w["x1"] <= col.x1]
    return " ".join(parts).strip()


def _grid_mode_parse_page(
    page,
    prev_balance: Optional[float],
    debug: bool = False,
) -> Tuple[List[Dict[str, str]], Optional[float]]:
    """
    Column-aware parse for Stanbic 7-column layout.
    Returns (rows, new_prev_balance)
    """
    rows: List[Dict[str, str]] = []
    lines = _line_groups(page)

    # 1) header + columns
    header_idx = None
    header_groups = None
    for idx, (_y, words) in enumerate(lines):
        header_groups = _match_header(words)
        if header_groups:
            header_idx = idx
            break
    if header_idx is None:
        if debug:
            print("(stanbic grid): header not found on page", file=sys.stderr)
        return rows, prev_balance

    col_boxes = _build_col_boxes(header_groups)
    colmap = {c.name: c for c in col_boxes}

    def has_two_dates(txn_txt: str, val_txt: str) -> bool:
        return bool(DATE_TOKEN.search(txn_txt)) and bool(DATE_TOKEN.search(val_txt))

    current: Optional[Dict[str, str]] = None

    # 2) iterate lines after header
    for _y, words in lines[header_idx + 1 :]:
        c_txn = _slice_col_text(words, colmap["TXN_DATE"])
        c_val = _slice_col_text(words, colmap["VAL_DATE"])
        c_remarks = _slice_col_text(words, colmap["REMARKS"])
        c_debit = _slice_col_text(words, colmap["DEBIT"])
        c_credit = _slice_col_text(words, colmap["CREDIT"])
        c_balance = _slice_col_text(words, colmap["BALANCE"])

        line_join = " ".join(
            [c_txn, c_val, c_remarks, c_debit, c_credit, c_balance]
        ).strip()
        if not line_join:
            continue
        if is_footer(line_join):
            continue

        # Opening / Balance summary lines
        if "Opening Balance" in c_remarks or "STATEMENT OPENING BALANCE" in c_remarks:
            ob = (
                _parse_amount(c_balance)
                or _parse_amount(c_credit)
                or _parse_amount(c_debit)
            )
            if ob is not None:
                prev_balance = ob
            continue
        if SKIP_REMARKS.search(c_remarks):
            continue

        if has_two_dates(c_txn, c_val):
            # flush previous buffer
            if current:
                rows.append(current)
                current = None

            txn_date = DATE_TOKEN.search(c_txn).group(0)
            val_date = DATE_TOKEN.search(c_val).group(0)

            bal = _parse_amount(c_balance)
            dval = _parse_amount(c_debit) or 0.0
            cval = _parse_amount(c_credit) or 0.0

            # infer debit/credit from balance movement if needed
            if (
                bal is not None
                and dval == 0.0
                and cval == 0.0
                and prev_balance is not None
            ):
                diff = round(bal - prev_balance, 2)
                if diff < 0:
                    dval = abs(diff)
                elif diff > 0:
                    cval = abs(diff)

            current = {
                "TXN_DATE": normalize_date(txn_date),
                "VAL_DATE": normalize_date(val_date),
                "REMARKS": c_remarks.strip(),
                "DEBIT": f"{dval:.2f}" if dval else "0.00",
                "CREDIT": f"{cval:.2f}" if cval else "0.00",
                "BALANCE": (
                    f"{bal:.2f}"
                    if bal is not None
                    else (f"{prev_balance:.2f}" if prev_balance is not None else "0.00")
                ),
            }

            if bal is not None:
                prev_balance = bal

        else:
            # continuation → append to current REMARKS and capture amounts if present
            if current:
                if c_remarks:
                    current["REMARKS"] = (current["REMARKS"] + "\n" + c_remarks).strip()
                bal2 = _parse_amount(c_balance)
                if bal2 is not None:
                    current["BALANCE"] = f"{bal2:.2f}"
                    prev_balance = bal2
                d2 = _parse_amount(c_debit)
                c2 = _parse_amount(c_credit)
                if d2:
                    current["DEBIT"] = f"{d2:.2f}"
                if c2:
                    current["CREDIT"] = f"{c2:.2f}"
            else:
                # orphan non-date line — ignore
                continue

    if current:
        rows.append(current)

    return rows, prev_balance


# ----------------------------
# Text-mode fallback for unstructured Stanbic PDFs
# ----------------------------
def _text_mode_parse_page(page, prev_balance: Optional[float], debug: bool = False):
    """
    Parse Stanbic variants that lack grid alignment.
    Relies only on extract_text() and TXN_DATE..BALANCE pattern logic.
    """
    rows: List[Dict[str, str]] = []
    text = page.extract_text() or ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return rows, prev_balance

    # find header
    header_idx = None
    for i, ln in enumerate(lines):
        if "Posting Date" in ln and "Balance" in ln:
            header_idx = i
            break
        if "Transaction" in ln and "Balance" in ln:
            header_idx = i
            break
    if header_idx is None:
        return rows, prev_balance

    data_lines = lines[header_idx + 1 :]

    # group by transaction start (line starting with TXN_DATE pattern)
    blocks = []
    current = []
    for ln in data_lines:
        if is_footer(ln):
            continue
        # txn rows start with a date token (txn date)
        if re.match(r"^\d{2}[-/]\d{2}[-/]\d{4}", ln):
            if current:
                blocks.append(current)
            current = [ln]
        else:
            if current:
                current.append(ln)
            else:
                # sometimes the first few lines before first date are noise; ignore
                continue
    if current:
        blocks.append(current)

    for block in blocks:
        # join to make parsing robust
        joined = " ".join(block)
        dates = DATE_TOKEN.findall(joined)
        if len(dates) < 2:
            # skip malformed block
            if debug:
                print(
                    f"(stanbic text): skipping block no 2 dates: {joined[:80]!r}",
                    file=sys.stderr,
                )
            continue
        txn_date, val_date = dates[:2]

        amounts = AMOUNT_RE.findall(joined.replace(" ", ""))
        if not amounts:
            if debug:
                print(
                    f"(stanbic text): skipping block no amounts: {joined[:80]!r}",
                    file=sys.stderr,
                )
            continue

        balance_raw = strip_cr_dr(amounts[-1])
        amount_raw = strip_cr_dr(amounts[-2]) if len(amounts) >= 2 else None
        try:
            current_balance = to_float(balance_raw)
        except Exception:
            if debug:
                print(
                    f"(stanbic text): could not parse balance '{balance_raw}' in block",
                    file=sys.stderr,
                )
            continue

        amt_val = to_float(amount_raw) if amount_raw else 0.0

        debit = "0.00"
        credit = "0.00"
        if prev_balance is not None:
            # check arithmetic to determine side
            if abs((prev_balance - amt_val) - current_balance) < 0.01:
                debit = f"{amt_val:.2f}"
            elif abs((prev_balance + amt_val) - current_balance) < 0.01:
                credit = f"{amt_val:.2f}"
            else:
                # fallback: compare balances
                if current_balance < prev_balance:
                    debit = f"{amt_val:.2f}"
                else:
                    credit = f"{amt_val:.2f}"
        else:
            debit = f"{amt_val:.2f}"

        # remarks = everything between val_date occurrence and the balance token
        try:
            # find first appearance of val_date after txn_date
            idx_val = joined.index(val_date)
            idx_bal = joined.rfind(balance_raw)
            remarks = joined[idx_val + len(val_date) : idx_bal].strip()
        except Exception:
            remarks = joined

        # clean extra spacing
        remarks = re.sub(r"\s{2,}", " ", remarks).strip()

        row = [
            normalize_date(txn_date),
            normalize_date(val_date),
            remarks,
            debit,
            credit,
            f"{current_balance:.2f}",
        ]
        parsed = parse_text_row(row, HEADERS)
        rows.append(parsed)
        prev_balance = current_balance

        if debug:
            print(
                f"(stanbic text): built {parsed['TXN_DATE']} {parsed['VAL_DATE']} BAL={parsed['BALANCE']} REMARKS={parsed['REMARKS'][:60]!r}",
                file=sys.stderr,
            )

    return rows, prev_balance


# ----------------------------
# Main parse (existing logic + text fallback)
# ----------------------------
def parse(path: str, debug: bool = False) -> List[Dict[str, str]]:
    transactions: List[Dict[str, str]] = []
    prev_balance: Optional[float] = None

    try:
        with pdfplumber.open(path) as pdf:
            # Seed Opening Balance (scan first 3 pages)
            all_lines_for_opening: List[str] = []
            for p in pdf.pages[:3]:
                # prefer raw text for opening balance
                t = p.extract_text() or ""
                all_lines_for_opening.extend(t.splitlines())
            opening = find_opening_balance_from_lines(all_lines_for_opening)
            if opening is not None:
                prev_balance = opening
                if debug:
                    print(
                        f"(stanbic): Found Opening Balance = {prev_balance:.2f}",
                        file=sys.stderr,
                    )

            # Per-page parsing: block -> grid -> text fallback
            for page_num, page in enumerate(pdf.pages, start=1):
                if debug:
                    print(f"(stanbic): Processing page {page_num}", file=sys.stderr)

                # ---------- block approach (line-based using extract_words) ----------
                word_lines: Dict[float, List[dict]] = {}
                for w in page.extract_words(
                    x_tolerance=2, y_tolerance=3, keep_blank_chars=True
                ):
                    word_lines.setdefault(round(w["top"], 1), []).append(w)

                lines: List[str] = [
                    " ".join(w["text"] for w in sorted(ws, key=lambda x: x["x0"]))
                    for _y, ws in sorted(word_lines.items())
                ]

                header_idx = None
                for i, ln in enumerate(lines):
                    if ("Posting Date" in ln and "Balance" in ln) or (
                        "Transaction" in ln and "Balance" in ln
                    ):
                        header_idx = i
                        break

                page_txns: List[Dict[str, str]] = []

                if header_idx is not None:
                    start = header_idx + 1
                    date_indices = [
                        i
                        for i in range(start, len(lines))
                        if DATE_LINE.search(lines[i])
                    ]
                    if date_indices:
                        for pos, date_idx in enumerate(date_indices):
                            block_start = (
                                start if pos == 0 else date_indices[pos - 1] + 1
                            )
                            block_end = (
                                (date_indices[pos + 1] - 1)
                                if (pos + 1 < len(date_indices))
                                else (len(lines) - 1)
                            )
                            while block_end >= date_idx and is_footer(lines[block_end]):
                                block_end -= 1

                            block_lines = [
                                lines[i]
                                for i in range(block_start, block_end + 1)
                                if lines[i].strip() and not is_footer(lines[i])
                            ]

                            # locate date line inside block_lines
                            try:
                                date_idx_in_block = next(
                                    idx
                                    for idx, _ in enumerate(block_lines)
                                    if DATE_LINE.search(block_lines[idx])
                                )
                            except StopIteration:
                                continue

                            txn = build_transaction(
                                block_lines,
                                date_idx_in_block,
                                prev_balance,
                                debug=debug,
                            )
                            if txn:
                                page_txns.append(txn)
                                try:
                                    prev_balance = to_float(txn["BALANCE"])
                                except Exception:
                                    pass

                # ---------- grid fallback ----------
                need_grid = (not page_txns) or all(
                    (
                        t.get("DEBIT") == "0.00"
                        and t.get("CREDIT") == "0.00"
                        and (t.get("BALANCE") in ("0.00", "", None))
                    )
                    for t in page_txns
                )

                if need_grid:
                    grid_rows, prev_balance = _grid_mode_parse_page(
                        page, prev_balance, debug=debug
                    )
                    if grid_rows:
                        page_txns = deepcopy(grid_rows)
                        if debug:
                            print(
                                f"(stanbic grid): used grid mode for page {page_num} ({len(grid_rows)} rows)",
                                file=sys.stderr,
                            )

                # ---------- text-mode fallback (only if still empty) ----------
                if not page_txns:
                    text_rows, prev_balance = _text_mode_parse_page(
                        page, prev_balance, debug=debug
                    )
                    if text_rows:
                        page_txns = text_rows
                        if debug:
                            print(
                                f"(stanbic text): used text mode for page {page_num} ({len(text_rows)} rows)",
                                file=sys.stderr,
                            )

                transactions.extend(page_txns)

    except Exception as e:
        print(f"Error processing Stanbic statement: {e}", file=sys.stderr)
        return []

    # Final normalization & checks
    return calculate_checks(transactions)
