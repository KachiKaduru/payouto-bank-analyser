# banks/fidelity/universal.py
import sys
import re
import pdfplumber
from typing import List, Dict
from utils import normalize_date, calculate_checks

AMOUNT_RE = re.compile(r"\d{1,3}(?:,\d{3})*\.\d{2}")


def _extract_amounts(s: str):
    """Return list of all decimal currency-like numbers as strings, in order."""
    return [m.group(0) for m in AMOUNT_RE.finditer(s)]


def _to_float(num: str) -> float:
    return float(num.replace(",", ""))


def _strip_last_amounts(s: str, k: int = 2) -> str:
    """Remove up to the last k decimal amounts (e.g., '50.00 377.91') anywhere near the end."""
    matches = list(AMOUNT_RE.finditer(s))
    if not matches:
        return s.strip()
    spans = [m.span() for m in matches[-k:]]
    out = s
    # Remove from right to left so indices don’t shift
    for start, end in sorted(spans, key=lambda x: x[0], reverse=True):
        out = out[:start].rstrip() + " " + out[end:].lstrip()
    return re.sub(r"\s{2,}", " ", out).strip()


def parse(path: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    prev_balance = None
    pending = None  # {'txn_date', 'val_date', 'rest'}

    def flush_pending():
        nonlocal prev_balance, pending
        if not pending:
            return
        combined = pending["rest"].strip()

        nums = _extract_amounts(combined)
        amount = balance = None
        if nums:
            balance = _to_float(nums[-1])
            if len(nums) >= 2:
                amount = _to_float(nums[-2])

        details = _strip_last_amounts(combined, k=2)

        debit = credit = 0.0
        if balance is not None and prev_balance is not None and amount is not None:
            delta = round(balance - prev_balance, 2)
            if delta > 0:
                credit = amount
            elif delta < 0:
                debit = amount
            # if delta == 0: leave both at 0.00
        elif amount is not None:
            # Heuristic fallback if opening balance missing in text segment
            # Bias towards 'FROM' => credit; else debit
            if re.search(r"\bFROM\b", details, re.I):
                credit = amount
            else:
                debit = amount

        # Update prev_balance if we parsed one
        if balance is not None:
            prev_balance = balance

        rows.append(
            {
                "TXN_DATE": normalize_date(pending["txn_date"]),
                "VAL_DATE": normalize_date(pending["val_date"]),
                "REFERENCE": "",
                "REMARKS": details,
                "DEBIT": f"{debit:.2f}",
                "CREDIT": f"{credit:.2f}",
                "BALANCE": f"{balance:.2f}" if balance is not None else "",
                "Check": "",
                "Check 2": "",
            }
        )
        pending = None

    # Patterns / skips
    txn_start_re = re.compile(
        r"^(?P<txn>\d{1,2}-[A-Za-z]{3}-\d{2})\s+(?P<val>\d{1,2}-[A-Za-z]{3}-\d{2})\b"
    )
    footer_date_re = re.compile(r"^\d{2}/\d{2}/\d{4}$")  # e.g., 14/08/2025
    page_of_re = re.compile(r"^\d+\s+of\s+\d+$")  # e.g., 1 of 5

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                print(f"(fidelity): Processing page {page_num}", file=sys.stderr)
                text = page.extract_text(x_tolerance=1, y_tolerance=1) or ""
                for raw in text.splitlines():
                    line = raw.strip()

                    # Skip headers/footers
                    if not line:
                        continue
                    if line in ("Transactions", "Transaction", "Date"):
                        continue
                    if line.startswith(("From ", "Account:", "Currency:", "Type:")):
                        continue
                    if footer_date_re.match(line) or page_of_re.match(line):
                        continue
                    if line.startswith("Opening Balance"):
                        # Initialize prev_balance from opening balance if present
                        nums = _extract_amounts(line)
                        if nums:
                            prev_balance = _to_float(nums[-1])
                        continue
                    if line.startswith("Closing Balance"):
                        # Ignore; not a transaction
                        continue

                    # New row?
                    m = txn_start_re.match(line)
                    if m:
                        # flush previous txn if any
                        flush_pending()
                        # start new
                        rest = line[m.end() :].strip()
                        pending = {
                            "txn_date": m.group("txn"),
                            "val_date": m.group("val"),
                            "rest": rest,
                        }
                    else:
                        # continuation / wrapped detail line
                        if pending:
                            pending["rest"] += " " + line

            # flush last txn
            flush_pending()

        # Only return rows with at least one of the dates present
        return calculate_checks([r for r in rows if r["TXN_DATE"] or r["VAL_DATE"]])

    except Exception as e:
        print(f"Error processing Fidelity Bank statement: {e}", file=sys.stderr)
        return []
