# banks/wema/universal.py
import sys
import re
import pdfplumber
from typing import List, Dict, Optional

from utils import normalize_date, to_float, calculate_checks, STANDARDIZED_ROW

# --- Regex helpers ---
FULL_DATE_RE = re.compile(r"(\d{1,2}[-/ ]*[A-Za-z]{3,9}[-/ ]*\d{2,4})", re.I)
MONTH_RE = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)

# FULL_DATE_RE = re.compile(rf"(\d{{1,2}}[-/ ]*{MONTH_RE}[-/ ]*\d{{2,4}})", re.I)

DATE_START_RE = re.compile(r"^\s*(\d{1,2})[-/ ]*([A-Za-z]{3,9})", re.I)
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

                lines = [ln.replace("\u20a6", "₦") for ln in text.split("\n")]

                # --- Get Opening Balance on page 1 ---
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

                # --- Find header block ---
                header_idx = None
                for i, ln in enumerate(lines):
                    low = ln.lower()
                    if "transaction details" in low and "balance" in low:
                        header_idx = i
                        break

                if page_num == 1 and header_idx is None:
                    print(
                        "(wema): page 1 header not found yet — skipping front matter",
                        file=sys.stderr,
                    )
                    continue

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

                # --- Process lines into transaction buffers ---
                for ln in lines[start_idx:]:
                    ln_stripped = ln.strip()
                    if not ln_stripped:
                        continue

                    if DATE_START_RE.match(ln_stripped):
                        if current_row_lines:
                            txn = _build_transaction(current_row_lines, prev_balance)
                            if txn:
                                prev_balance = to_float(txn["BALANCE"])
                                transactions.append(txn)
                        current_row_lines = [ln_stripped]
                    else:
                        if current_row_lines is None:
                            continue
                        current_row_lines.append(ln_stripped)

            # --- Flush last transaction ---
            if current_row_lines:
                txn = _build_transaction(current_row_lines, prev_balance)
                if txn:
                    transactions.append(txn)

        if transactions:
            print(f"(wema): Parsed {len(transactions)} transactions", file=sys.stderr)
            print(f"(wema): First sample: {transactions[0]}", file=sys.stderr)
        else:
            print("(wema): No transactions parsed", file=sys.stderr)

        return calculate_checks(transactions)

    except Exception as e:
        print(f"(wema): Error processing Wema statement: {e}", file=sys.stderr)
        return []


def _build_transaction(
    lines: List[str], prev_balance: Optional[float]
) -> Optional[Dict[str, str]]:
    try:
        full_text = " ".join(lines).strip()

        # --- Extract proper date ---
        dmatch = FULL_DATE_RE.search(full_text)
        date_str = ""
        if dmatch:
            date_str = dmatch.group(1)
        else:
            # If no contiguous date, fallback: use first line’s day+month, last valid year
            first_line = lines[0] if lines else ""
            m0 = DATE_START_RE.match(first_line)
            years = YEAR_RE.findall(full_text)
            if m0 and years:
                year = years[-1]  # use the LAST year token
                if len(year) == 2:
                    year = f"20{year}"
                day, month = m0.group(1), m0.group(2)
                date_str = f"{day}-{month}-{year}"

        txn_date = normalize_date(date_str) if date_str else ""

        # --- Remove date fragments for cleaner parsing ---
        remainder = full_text
        if dmatch:
            remainder = remainder.replace(dmatch.group(1), " ", 1)
        else:
            if lines:
                m0 = DATE_START_RE.match(lines[0])
                if m0:
                    remainder = remainder.replace(m0.group(0), " ", 1)
            years = YEAR_RE.findall(full_text)
            if years:
                remainder = remainder.replace(years[-1], " ", 1)

        # --- Extract money tokens ---
        money_tokens = MONEY_RE.findall(remainder)
        if len(money_tokens) < 2:
            print(f"(wema): skipping txn (bad money tokens) {lines}", file=sys.stderr)
            return None

        # Clean up broken tokens like 18,500,0 .38 → 18,500,000.38
        money_tokens = [t.replace(" ", "") for t in money_tokens]

        amount_str = money_tokens[-2].replace(",", "")
        balance_str = money_tokens[-1].replace(",", "")

        amt_val = to_float(amount_str)
        bal_val = to_float(balance_str)

        # --- Reference token ---
        ref_match = REF_RE.search(remainder)
        reference = ref_match.group(1).upper() if ref_match else ""

        # --- Remarks (strip money + years + reference) ---
        remainder_no_money = MONEY_RE.sub(" ", remainder)
        if reference:
            remainder_no_money = re.sub(
                re.escape(reference), " ", remainder_no_money, flags=re.I
            )
        remarks = re.sub(r"\s+", " ", remainder_no_money).strip()
        remarks = re.sub(r"\b20\d{2}\b", "", remarks).strip()  # remove stray years

        # --- Debit/Credit via balance movement ---
        debit, credit = "0.00", "0.00"
        if prev_balance is not None:
            if bal_val < prev_balance:
                debit = f"{amt_val:.2f}"
            elif bal_val > prev_balance:
                credit = f"{amt_val:.2f}"

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
