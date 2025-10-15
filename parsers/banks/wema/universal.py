# banks/wema/universal.py
import sys
import re
import pdfplumber
from typing import List, Dict, Optional, Tuple

from utils import normalize_date, to_float, calculate_checks, STANDARDIZED_ROW

# --- Month pattern: only real months (prevents matching words like "salary") ---
MONTH_PATTERN = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"

# Regex helpers (more strict than before)
FULL_DATE_RE = re.compile(
    rf"\b(\d{{1,2}})[-/ ]*({MONTH_PATTERN})[-/ ]*(?:20\d{{2}}|19\d{{2}})\b",
    re.I,
)
DATE_START_RE = re.compile(rf"^\s*(\d{{1,2}})[-/ ]*({MONTH_PATTERN})\b", re.I)
YEAR_RE = re.compile(r"\b(20\d{2}|19\d{2}|\d{2})\b")
MONEY_RE = re.compile(r"[\d,]+\.\d{2}")
REF_RE = re.compile(r"\b([A-Za-z]\d{3,})\b", re.I)


def parse(path: str) -> List[Dict[str, str]]:
    transactions: List[Dict[str, str]] = []
    prev_balance: Optional[float] = None
    opening_balance: Optional[float] = None
    current_row_lines: Optional[List[str]] = None

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                print(f"(wema): Processing page {page_num}", file=sys.stderr)
                text = page.extract_text()
                if not text:
                    print(f"(wema): No text on page {page_num}", file=sys.stderr)
                    continue

                # Normalize Naira symbol and split into lines
                lines = [ln.replace("\u20a6", "₦") for ln in text.split("\n")]

                # --- Extract Opening Balance (page 1) if present ---
                if page_num == 1 and opening_balance is None:
                    for ln in lines:
                        if "Opening Balance" in ln:
                            match = re.search(r"Opening Balance\s+([\d,]+\.\d{2})", ln)
                            if match:
                                opening_balance = to_float(match.group(1))
                                prev_balance = opening_balance
                                print(
                                    f"(wema): Found Opening Balance = {opening_balance}",
                                    file=sys.stderr,
                                )
                                break

                # --- Find the transaction header block on this page ---
                header_idx = None
                for i, ln in enumerate(lines):
                    low = ln.lower()
                    if "transaction details" in low and "balance" in low:
                        header_idx = i
                        break

                # Strict page-1 guard: skip page 1 until header appears
                if page_num == 1 and header_idx is None:
                    print(
                        "(wema): page 1 header not found yet — skipping front matter",
                        file=sys.stderr,
                    )
                    continue

                # determine where to start scanning lines on this page
                if header_idx is not None:
                    start_idx = None
                    for k in range(header_idx + 1, len(lines)):
                        if DATE_START_RE.match(lines[k].strip()):
                            start_idx = k
                            break
                    if start_idx is None:
                        print(
                            f"(wema): header found on page {page_num} but no date-line after it; skipping page",
                            file=sys.stderr,
                        )
                        continue
                else:
                    start_idx = 0

                # --- Build transaction buffers from lines[start_idx:] ---
                for ln in lines[start_idx:]:
                    ln_stripped = ln.strip()
                    if not ln_stripped:
                        continue

                    if DATE_START_RE.match(ln_stripped):
                        # finalize previous buffer
                        if current_row_lines:
                            txn = _build_transaction(current_row_lines, prev_balance)
                            if txn:
                                prev_balance = to_float(txn["BALANCE"])
                                transactions.append(txn)
                        # start a fresh buffer
                        current_row_lines = [ln_stripped]
                    else:
                        if current_row_lines is None:
                            # ignore noise before the first date (shouldn't normally happen)
                            continue
                        current_row_lines.append(ln_stripped)

            # flush final buffered transaction
            if current_row_lines:
                txn = _build_transaction(current_row_lines, prev_balance)
                if txn:
                    transactions.append(txn)

        if transactions:
            print(f"(wema): Parsed {len(transactions)} transactions", file=sys.stderr)
            print(f"(wema): First sample: {transactions[0]}", file=sys.stderr)
        else:
            print("(wema): No transactions parsed", file=sys.stderr)

        # run checks (adds Check/Check 2) and return
        return calculate_checks(transactions)

    except Exception as e:
        print(f"(wema): Error processing Wema statement: {e}", file=sys.stderr)
        return []


# ----------------- Helper internals -----------------
def _extract_trailing_year_and_clean(
    lines: List[str],
) -> Tuple[Optional[str], List[str]]:
    """
    Look at the last 2 lines for a standalone year token (e.g. "2025" or "2025 OYENEYE -").
    If found, remove that year token from the lines and return it.
    This avoids picking up wrong years (like day digits or amounts).
    """
    lines_copy = list(lines)
    trailing_year = None
    # Check last up to 2 lines (safe for typical Wema layout)
    for i in range(1, min(3, len(lines_copy) + 1)):
        ln = lines_copy[-i].strip()
        # If the line starts with a clean 4-digit year (or 2-digit)
        m = re.match(r"^\s*(20\d{2}|19\d{2}|\d{2})\b", ln)
        if m:
            trailing_year = m.group(1)
            # remove the year token from that line
            new_ln = re.sub(
                r"^\s*(20\d{2}|19\d{2}|\d{2})\b", "", lines_copy[-i]
            ).strip()
            if new_ln:
                lines_copy[-i] = new_ln
            else:
                # line became empty after removing year → drop it
                lines_copy.pop(-i)
            break
    return trailing_year, lines_copy


def _repair_money_tokens(remainder: str) -> List[str]:
    """
    Return money tokens found in remainder. If not enough tokens are found,
    attempt to repair split tokens by combining adjacent tokens that together
    match the MONEY_RE (e.g. '25,' + '500.00' -> '25,500.00').
    """
    found = MONEY_RE.findall(remainder)
    if len(found) >= 2:
        return found

    # token-level attempt to combine adjacent tokens
    tokens = remainder.split()
    combined = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        # if token itself matches, take it
        if MONEY_RE.match(t):
            combined.append(t)
            i += 1
            continue

        # attempt to combine with next token
        if i + 1 < len(tokens):
            cand = t + tokens[i + 1]
            if MONEY_RE.match(cand):
                combined.append(cand)
                i += 2
                continue
            # sometimes there is a comma separated split (e.g. "25," "500.00")
            cand2 = (
                (t + "," + tokens[i + 1])
                if not t.endswith(",")
                else (t + tokens[i + 1])
            )
            if MONEY_RE.match(cand2):
                combined.append(cand2)
                i += 2
                continue

        # otherwise move on
        i += 1

    # if repair produced tokens, return them; else return original found (maybe empty)
    return combined if combined else found


def _clean_remarks_from(remainder_no_money: str, reference: str) -> str:
    """
    Remove extra whitespace, reference token, and standalone year tokens from remarks.
    """
    r = remainder_no_money
    if reference:
        r = re.sub(re.escape(reference), " ", r, flags=re.I)
    # remove leftover standalone 4-digit years like 2024/2025
    r = re.sub(r"\b20\d{2}\b", " ", r)
    # collapse whitespace and strip
    r = re.sub(r"\s+", " ", r).strip()
    return r


def _build_transaction(
    lines: List[str], prev_balance: Optional[float]
) -> Optional[Dict[str, str]]:
    """
    Reconstruct a single transaction from the lines belonging to it.

    ✅ Handles both single-line and split-date formats (e.g. '03-Mar-2025' and '03-Mar-\n2025')
    ✅ Uses Opening Balance when available
    ✅ Falls back gracefully on the first transaction (no prev_balance)
    Returns a STANDARDIZED_ROW-like dict or None on failure.
    """
    try:
        # 1. Build a joined version of all text lines (makes regex easier)
        lines_copy = list(lines)
        full_text = " ".join(lines_copy).strip()

        # 2. Try to match a full date like "03-Mar-2025" directly
        dmatch = FULL_DATE_RE.search(full_text)
        date_str = ""
        trailing_year = None
        lines_cleaned = list(lines_copy)

        if dmatch:
            # Found a single-line full date → perfect
            date_str = dmatch.group(0)
        else:
            # No single-line full date → handle split layout ("03-Mar-\n2025")
            trailing_year, lines_cleaned = _extract_trailing_year_and_clean(
                lines_cleaned
            )
            full_text = " ".join(lines_cleaned).strip()

            # Try to combine day+month + trailing year
            first_line = lines_cleaned[0] if lines_cleaned else ""
            m0 = DATE_START_RE.match(first_line)
            year_token = trailing_year
            if not year_token:
                # Prefer a 4-digit year found anywhere
                y_match = re.findall(r"\b(20\d{2}|19\d{2})\b", full_text)
                if y_match:
                    year_token = y_match[-1]
                else:
                    # fallback: last 2-digit year token
                    y2 = re.findall(r"\b(\d{2})\b", full_text)
                    if y2:
                        year_token = y2[-1]

            if m0 and year_token:
                if len(year_token) == 2:
                    year_token = f"20{year_token}"
                date_str = f"{m0.group(1)}-{m0.group(2)}-{year_token}"

        # Normalize to consistent ISO date format (YYYY-MM-DD)
        txn_date = normalize_date(date_str) if date_str else ""

        # 3. Remove the date and year fragments from the text to simplify remainder parsing
        remainder = full_text
        if dmatch:
            remainder = remainder.replace(dmatch.group(0), " ", 1)
        else:
            m0 = DATE_START_RE.match(lines_cleaned[0]) if lines_cleaned else None
            if m0:
                remainder = remainder.replace(m0.group(0), " ", 1)
            if trailing_year:
                remainder = re.sub(
                    rf"\b{re.escape(trailing_year)}\b", " ", remainder, count=1
                )

        # 4. Extract money values (should be [amount, balance]) — auto-repair if tokens are split
        money_tokens = _repair_money_tokens(remainder)
        if len(money_tokens) < 2:
            # fallback: native regex
            money_tokens = MONEY_RE.findall(remainder)
        if len(money_tokens) < 2:
            print(f"(wema): skipping txn (bad money tokens) {lines}", file=sys.stderr)
            return None

        # Normalize numeric tokens → remove spaces/commas
        money_tokens = [t.replace(" ", "") for t in money_tokens]
        amount_str = money_tokens[-2].replace(",", "")
        balance_str = money_tokens[-1].replace(",", "")

        amt_val = to_float(amount_str)
        bal_val = to_float(balance_str)

        # 5. Extract reference (alphanumeric code like S95223404)
        ref_match = REF_RE.search(remainder)
        reference = ref_match.group(1).upper() if ref_match else ""

        # 6. Clean up remarks (remove money tokens, references, and standalone years)
        remainder_no_money = MONEY_RE.sub(" ", remainder)
        remarks = _clean_remarks_from(remainder_no_money, reference)

        # 7. Determine DEBIT or CREDIT value
        debit, credit = "0.00", "0.00"

        if prev_balance is not None:
            # ✅ Compare new balance with previous → direction of transaction
            if bal_val < prev_balance:
                debit = f"{amt_val:.2f}"
            elif bal_val > prev_balance:
                credit = f"{amt_val:.2f}"
        else:
            # 🧠 First transaction — no previous balance yet
            # Try to infer likely direction using context keywords
            if (
                "vat" in remarks.lower()
                or "fee" in remarks.lower()
                or "charge" in remarks.lower()
                or "transfer" in remarks.lower()
            ):
                # Charges, fees, and VATs are usually debits
                debit = f"{amt_val:.2f}"
            else:
                # Otherwise assume incoming credit (e.g., salary, transfer, deposit)
                credit = f"{amt_val:.2f}"

        # 8️⃣ Construct standardized transaction dict
        txn = STANDARDIZED_ROW.copy()
        txn.update(
            {
                "TXN_DATE": txn_date,
                "VAL_DATE": txn_date,
                "REFERENCE": reference,
                "REMARKS": remarks,
                "DEBIT": debit,
                "CREDIT": credit,
                "BALANCE": f"{bal_val:.2f}",
            }
        )

        return txn

    except Exception as e:
        print(
            f"(wema): Failed to build transaction from lines {lines} — {e}",
            file=sys.stderr,
        )
        return None
