# banks/alternative/universal.py
import sys
import re
import pdfplumber
from typing import List, Dict, Optional

from utils import normalize_date, to_float, calculate_checks, STANDARDIZED_ROW

# Patterns
FULL_DATE_SEARCH = re.compile(r"(\d{1,2}-[A-Za-z]{3}-\d{4})")  # e.g. 17-Jul-2025
PARTIAL_MONTH_YEAR_AT_START = re.compile(
    r"^[-]?[A-Za-z]{3}-\d{4}\b"
)  # -Jan-2025 or Jan-2025
AMOUNT_RE = re.compile(r"[\d,]+\.\d{2}")
NUMERIC_REF = re.compile(r"^\d{4,}$")  # numeric-only reference (4+ digits)

JUNK_PHRASES = [
    "opening balance",
    "closing balance",
    "total debit",
    "total credit",
    "settlement approve",
    "bank atm pos others",
    "for internal use",
    "scan to verify",
    "licensed by",
]


def _merge_split_date_lines(raw_lines: List[str]) -> List[str]:
    """If a date has been split (day on one line, '-Jan-2025' on the next),
    merge them so we have a single '01-Jan-2025' token on one line.
    This avoids inventing days from distant transactions."""
    merged = []
    i = 0
    n = len(raw_lines)
    while i < n:
        line = raw_lines[i]
        if i + 1 < n:
            nxt = raw_lines[i + 1]
            # next line looks like '-Jan-2025' or 'Jan-2025' at the start
            if PARTIAL_MONTH_YEAR_AT_START.match(nxt.strip()):
                # current line ends with a standalone day (like '01' or '1' possibly trailing '-')
                m = re.search(r"(\b\d{1,2})[-]?\s*$", line)
                if m:
                    combined = line.rstrip() + " " + nxt.lstrip()
                    merged.append(combined)
                    i += 2
                    continue
        merged.append(line)
        i += 1
    return merged


def _repair_money_tokens(remainder: str) -> List[str]:
    """Try to extract money tokens; if split across tokens, attempt to combine."""
    found = AMOUNT_RE.findall(remainder)
    if len(found) >= 2:
        return found

    tokens = remainder.split()
    combined = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if AMOUNT_RE.match(t):
            combined.append(t)
            i += 1
            continue
        # attempt to join with next token(s) to make a money token
        if i + 1 < len(tokens):
            cand = t + tokens[i + 1]
            if AMOUNT_RE.match(cand):
                combined.append(cand)
                i += 2
                continue
            # try with comma insertion for cases '25' + '500.00' -> '25,500.00'
            cand2 = (
                (t + "," + tokens[i + 1])
                if not t.endswith(",")
                else (t + tokens[i + 1])
            )
            if AMOUNT_RE.match(cand2):
                combined.append(cand2)
                i += 2
                continue
        i += 1

    return combined if combined else found


def _build_transaction_from_lines(
    lines: List[str], prev_balance: Optional[float]
) -> Optional[Dict[str, str]]:
    """Given the buffered lines for one transaction, extract date/ref/remarks/amounts/balance."""
    try:
        full_text = " ".join(lines).strip()
        # find the first full date in the combined text
        dmatch = FULL_DATE_SEARCH.search(full_text)
        date_str = dmatch.group(1) if dmatch else ""
        txn_date = normalize_date(date_str) if date_str else ""

        # substring after the first date (used to find reference)
        after_date = full_text[dmatch.end() :].strip() if dmatch else full_text

        # pick reference if the first token after the date is numeric (4+ digits)
        reference = ""
        if after_date:
            first_tok = after_date.split()[0]
            if NUMERIC_REF.match(first_tok):
                reference = first_tok
            else:
                # try alphanumeric ref fallback (short)
                m_ref = re.search(r"\b[A-Za-z0-9]{3,}\b", after_date)
                if m_ref and not m_ref.group(0).lower() in (
                    "from",
                    "to",
                    "nip",
                    "transfer",
                ):
                    reference = m_ref.group(0)

        # extract money tokens (prefer repaired tokens)
        money_tokens = _repair_money_tokens(full_text)
        if len(money_tokens) < 2:
            # fallback: native findall (maybe we repaired nothing)
            money_tokens = AMOUNT_RE.findall(full_text)
        if not money_tokens:
            # try last line specifically (sometimes amounts are single-line below narration)
            money_tokens = AMOUNT_RE.findall(lines[-1])

        if len(money_tokens) < 1:
            print(
                "(alternative): skipping txn (no money tokens) ->",
                lines,
                file=sys.stderr,
            )
            return None

        # Generally last token is balance, the token just before is the transaction amount
        # If only one token is found we'll assume it's balance (but that's less ideal)
        if len(money_tokens) == 1:
            balance_str = money_tokens[-1].replace(",", "")
            amount_str = "0.00"
        else:
            amount_str = money_tokens[-2].replace(",", "")
            balance_str = money_tokens[-1].replace(",", "")

        amt_val = to_float(amount_str)
        bal_val = to_float(balance_str)

        # build remarks: remove date fragment, reference and money tokens for a cleaner narration
        # Remove first occurrence of date and first occurrence of reference if present
        remainder = full_text
        if dmatch:
            remainder = remainder[: dmatch.start()] + remainder[dmatch.end() :]
        if reference:
            remainder = re.sub(re.escape(reference), " ", remainder, count=1)
        # remove money tokens text
        remainder = AMOUNT_RE.sub(" ", remainder)
        # strip weird chars left behind, collapse whitespace
        remarks = re.sub(r"[^\w\s.,&/()-]", " ", remainder)
        remarks = re.sub(r"\s+", " ", remarks).strip()

        # debit/credit decision by previous balance change
        debit, credit = "0.00", "0.00"
        if prev_balance is not None:
            # compare floats with rounding tolerance
            prev = round(prev_balance, 2)
            bal = round(bal_val, 2)
            if bal < prev:
                debit = f"{amt_val:.2f}"
            elif bal > prev:
                credit = f"{amt_val:.2f}"
            # if equal: leave both zero
        else:
            # no previous balance known (opening region) — leave both at 0.00
            debit = "0.00"
            credit = "0.00"

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
            f"(alternative): failed to build txn from lines {lines} — {e}",
            file=sys.stderr,
        )
        return None


def parse(path: str) -> List[Dict[str, str]]:
    transactions: List[Dict[str, str]] = []
    prev_balance: Optional[float] = None

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                print(f"(alternative): Processing page {page_num}", file=sys.stderr)
                text = page.extract_text()
                if not text:
                    print(
                        f"(alternative): page {page_num} has no text", file=sys.stderr
                    )
                    continue

                # normalize weird symbols and split into lines
                raw_lines = [
                    ln.replace("\u2022", " ")
                    .replace("", " ")
                    .replace("\u20a6", "₦")
                    .rstrip()
                    for ln in text.split("\n")
                ]

                # Merge split-date lines (day on one line, '-Jan-2025' on next)
                lines = _merge_split_date_lines(raw_lines)

                # remove empty lines and strip
                lines = [ln.strip() for ln in lines if ln and ln.strip()]

                # Build transaction buffers (start when a full date token is seen)
                current_buf: List[str] = []
                for ln in lines:
                    low = ln.lower()
                    if any(phrase in low for phrase in JUNK_PHRASES):
                        # skip obvious junk lines
                        continue

                    if FULL_DATE_SEARCH.search(ln):
                        # found a new transaction start
                        if current_buf:
                            txn = _build_transaction_from_lines(
                                current_buf, prev_balance
                            )
                            if txn:
                                transactions.append(txn)
                                prev_balance = to_float(txn["BALANCE"])
                        current_buf = [ln]
                    else:
                        # continuation line
                        if not current_buf:
                            # noise before the first identified date — ignore
                            continue
                        current_buf.append(ln)

                # flush last buffer on this page
                if current_buf:
                    txn = _build_transaction_from_lines(current_buf, prev_balance)
                    if txn:
                        transactions.append(txn)
                        prev_balance = to_float(txn["BALANCE"])

        # post-clean remarks
        for t in transactions:
            t["REMARKS"] = re.sub(r"\s+", " ", t["REMARKS"]).strip()

        # keep only transactions with a date (we try to avoid inventing dates)
        final_txns = [t for t in transactions if t["TXN_DATE"]]

        print(
            f"(alternative): Parsed {len(final_txns)} transactions (kept only dated rows).",
            file=sys.stderr,
        )
        if final_txns:
            print(f"(alternative): Example txn: {final_txns[0]}", file=sys.stderr)

        return calculate_checks(final_txns)

    except Exception as e:
        print(f"(alternative): Error processing statement: {e}", file=sys.stderr)
        return []
