# banks/fidelity/parser_summary.py
import sys
import re
import pdfplumber
from typing import List, Dict
from utils import normalize_date, calculate_checks

AMOUNT_RE = re.compile(r"\d{1,3}(?:,\d{3})*\.\d{2}")
TXN_LINE_RE = re.compile(
    r"^(?P<txn>\d{1,2}-[A-Za-z]{3}-\d{2,4})\s+(?P<val>\d{1,2}-[A-Za-z]{3}-\d{2,4})\b"
)
FOOTER_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
PAGE_OF_RE = re.compile(r"^\d+\s+of\s+\d+$")

# Heals common PDF token splits inside amounts like "9 011,290.41" → "9,011,290.41",
# ", 000" → ",000", and "50 .00" → "50.00"
SPLIT_HEALERS = [
    # 1–3 digits + space + 3digits[,3digits]*.dd  → insert a comma
    (re.compile(r"(?<!\d)(\d{1,3})\s(?=\d{3}(?:,\d{3})*\.\d{2}\b)"), r"\1,"),
    # comma + space + 3digits → remove the space
    (re.compile(r"(?<=,)\s(?=\d{3}\b)"), r""),
    # "50 .00" → "50.00"
    (re.compile(r"(?<=\d)\s\.(?=\d{2}\b)"), r"."),
    (re.compile(r"(?<=\.)\s(?=\d{2}\b)"), r""),
]


def _heal_amount_splits(s: str) -> str:
    out = s
    for pat, repl in SPLIT_HEALERS:
        out = pat.sub(repl, out)
    return out


def _extract_amounts(s: str):
    return [m.group(0) for m in AMOUNT_RE.finditer(s)]


def _to_float(num: str) -> float:
    return float(num.replace(",", ""))


def _strip_last_amounts(s: str, k: int = 2) -> str:
    matches = list(AMOUNT_RE.finditer(s))
    if not matches:
        return s.strip()
    spans = [m.span() for m in matches[-k:]]
    out = s
    for start, end in sorted(spans, key=lambda x: x[0], reverse=True):
        out = out[:start].rstrip() + " " + out[end:].lstrip()
    return re.sub(r"\s{2,}", " ", out).strip()


def parse(path: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    prev_balance = None
    pending = None
    in_summary = False
    summary_done = False

    def flush_pending():
        nonlocal prev_balance, pending
        if not pending:
            return
        combined = _heal_amount_splits(pending["rest"].strip())

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
        elif amount is not None:
            if re.search(r"\bFROM\b", details, re.I):
                credit = amount
            else:
                debit = amount

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

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                print(
                    f"(fidelity:summary): Processing page {page_num}", file=sys.stderr
                )
                text = page.extract_text(x_tolerance=1, y_tolerance=1) or ""
                for raw in text.splitlines():
                    line = raw.strip()
                    if not line:
                        continue
                    if FOOTER_DATE_RE.match(line) or PAGE_OF_RE.match(line):
                        continue

                    # Enter SUMMARY block if seen on page 1 and not yet done
                    if (
                        not summary_done
                        and page_num == 1
                        and (
                            line.upper().startswith("SUMMARY")
                            or line.upper().startswith("SUMMARY ")
                        )
                    ):
                        in_summary = True
                        continue

                    if in_summary:
                        # Capture beginning balance
                        if line.upper().startswith("BEGINNING BALANCE"):
                            nums = _extract_amounts(line)
                            if nums:
                                prev_balance = _to_float(nums[-1])
                            continue

                        # SUMMARY ends when we hit the transaction header or a txn line
                        if (
                            line.lower().startswith(("transaction", "transactions"))
                            or "value date" in line.lower()
                        ):
                            in_summary = False
                            summary_done = True
                            continue
                        m_txn = TXN_LINE_RE.match(line)
                        if m_txn:
                            in_summary = False
                            summary_done = True
                            # fall through to normal parsing for this same line

                        else:
                            # still inside summary matrix (ATM/POS/Online Banking/etc.)
                            continue  # ignore these rows entirely

                    # Normal skip lines (outside summary)
                    if line in ("Transactions", "Transaction", "Date"):
                        continue
                    if line.startswith(
                        ("From ", "Account:", "Currency:", "Type:", "www.", "OREGUN")
                    ):
                        continue
                    if line.startswith("Closing Balance"):
                        continue

                    # Transaction begin?
                    m = TXN_LINE_RE.match(line)
                    if m:
                        flush_pending()
                        rest = line[m.end() :].strip()
                        pending = {
                            "txn_date": m.group("txn"),
                            "val_date": m.group("val"),
                            "rest": rest,
                        }
                    else:
                        if pending:
                            pending["rest"] += " " + line

            flush_pending()

        return calculate_checks([r for r in rows if r["TXN_DATE"] or r["VAL_DATE"]])

    except Exception as e:
        print(f"Error processing Fidelity (summary variant): {e}", file=sys.stderr)
        return []
