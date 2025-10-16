# parsers/main_metadata_extractor.py
import re
import pdfplumber
from typing import Dict, Optional, List

from utils import to_float

RX_MONEY = re.compile(r"(?:₦|NGN)?\s?[-\d,]+\.\d{2}")
RX_DATE_ISO = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
RX_DATE_DMY = re.compile(
    r"\b\d{2}[/-][A-Za-z]{3}[/-]\d{4}\b|\b\d{2}\s[A-Za-z]{3}\s\d{4}\b"
)  # 01-Mar-2025 | 01 Mar 2025
RX_DATE_DSL = re.compile(r"\b\d{2}[/-]\d{2}[/-]\d{4}\b")  # 01/03/2025 or 01-03-2025

LABELS = {
    "bank": [
        "ZENITH BANK",
        "ZENITH BANK PLC",
        "ACCESS BANK",
        "FIRST BANK",
        "FIRSTBANK",
        "UNITED BANK FOR AFRICA",
        "UBA",
        "GTBANK",
        "GUARANTY TRUST BANK",
        "GTCO",
        "FIDELITY BANK",
        "FCMB",
    ],
    "account_name": ["Account Name", "ACCOUNT NAME", "Account Holder", "Customer Name"],
    "account_number": [
        "Account No",
        "ACCOUNT No.",
        "Account Number",
        "ACCOUNT NUMBER",
        "Acct No",
        "ACCOUNT NO.",
        "Account:",
    ],
    "currency": ["Currency", "CURRENCY"],
    "account_type": ["Account Type", "ACCOUNT TYPE", "Account Class"],
    "period": [
        "Period",
        "Statement Period",
        "Period Covered",
        "Period:",
        "Period  :",
        "Summary statement for",
        "Summary statement",
        "Summary statement\nfor",
    ],  # GTB uses "Statement Period  :"
    "start_date": ["Start Date", "From", "Period From"],
    "end_date": ["End Date", "To", "Period To"],
    "opening_balance": ["Opening Balance", "Opening Bal", "Opening"],
    "closing_balance": ["Closing Balance", "Closing Bal", "Closing"],
    "current_balance": [
        "Current Balance",
        "Available Balance",
        "Usable Balance",
        "Balance",
    ],
    "date_printed": [
        "Date Printed",
        "Print Date",
        "Print. Date",
        "Printed",
        "Generated",
        "Generated on",
        "Create Date",
    ],
}


def _find_first_label_line(text: str, labels: list[str]) -> Optional[str]:
    for lbl in labels:
        m = re.search(rf"{re.escape(lbl)}\s*[:\uFF1A]?\s*(.+)", text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def _first_money(line: Optional[str]) -> Optional[str]:
    if not line:
        return None
    m = RX_MONEY.search(line)
    return m.group(0).replace("NGN", "").replace("₦", "").strip() if m else None


def _first_date(line: Optional[str]) -> Optional[str]:
    if not line:
        return None
    for rx in (RX_DATE_ISO, RX_DATE_DMY, RX_DATE_DSL):
        m = rx.search(line)
        if m:
            return _norm_date(m.group(0))
    return None


def _norm_date(s: str) -> str:
    # Normalize to YYYY-MM-DD when possible; otherwise return original.
    # Accepts: 2025-03-01, 01/03/2025, 01-03-2025, 01 Mar 2025, 01-Mar-2025
    try:
        from datetime import datetime

        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d-%b-%Y"):
            try:
                return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
            except ValueError:
                pass
    except Exception:
        pass
    return s


def _peek_bank(text: str) -> Optional[str]:
    # quick bank guess by banner words on header/footer
    head = "\n".join(text.splitlines()[:20]).upper()
    for b in LABELS["bank"]:
        if b in head:
            return b
    return None


def _period(text: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    raw = _find_first_label_line(text, LABELS["period"])
    if raw:
        # Example: "01-Mar-2025 TO 12-Aug-2025" | "01/03/2025 to 12/08/2025"
        m = re.search(r"(.+?)\s+(?:to|TO|-|–)\s+(.+)", raw)
        if m:
            return _norm_date(m.group(1).strip()), _norm_date(m.group(2).strip()), raw
    # Fallback to separate labels
    start = _first_date(_find_first_label_line(text, LABELS["start_date"]))
    end = _first_date(_find_first_label_line(text, LABELS["end_date"]))
    return start, end, raw


def extract_metadata(path: str) -> Dict:
    meta: Dict[str, Optional[str]] = {
        "bank": None,
        "account_name": None,
        "account_number": None,
        "currency": None,
        "account_type": None,
        "start_date": None,
        "end_date": None,
        "opening_balance": None,
        "closing_balance": None,
        "current_balance": None,
        "date_printed": None,
        "period_text": None,
        "raw_header": None,
    }

    with pdfplumber.open(path) as pdf:
        if not pdf.pages:
            return meta
        first = pdf.pages[0]
        text = (first.extract_text() or "").strip()
        meta["raw_header"] = "\n".join(
            text.splitlines()[:60]
        )  # keep small slice for debug
        meta["bank"] = _peek_bank(text)

        # Simple keyed fields (same line after label)
        meta["account_name"] = _find_first_label_line(text, LABELS["account_name"])
        meta["account_number"] = (
            (_find_first_label_line(text, LABELS["account_number"]) or "")
            .replace(" ", "")
            .replace(":", "")
        )
        meta["currency"] = _find_first_label_line(text, LABELS["currency"])
        meta["account_type"] = _find_first_label_line(text, LABELS["account_type"])

        start, end, raw_period = _period(text)
        if start:
            meta["start_date"] = start
        if end:
            meta["end_date"] = end
        meta["period_text"] = raw_period

        meta["date_printed"] = _first_date(
            _find_first_label_line(text, LABELS["date_printed"])
        )

        # balances
        meta["opening_balance"] = _first_money(
            _find_first_label_line(text, LABELS["opening_balance"])
        )
        meta["closing_balance"] = _first_money(
            _find_first_label_line(text, LABELS["closing_balance"])
        )
        meta["current_balance"] = _first_money(
            _find_first_label_line(text, LABELS["current_balance"])
        )

    # final cleanups
    meta["account_number"] = (meta["account_number"] or "").strip() or None
    meta["currency"] = (meta["currency"] or "NGN").replace("NIGERIAN NAIRA", "NGN")
    return meta


# add to main_metadata.py (below extract_metadata)


def _is_nuban_10_digits(acct: Optional[str]) -> bool:
    if not acct:
        return False
    new_acct = to_float(acct)

    return new_acct.is_integer() and len(acct) == 10


def _money_to_float(s: Optional[str]) -> float:
    if not s:
        return 0.0
    return float(s.replace("NGN", "").replace("₦", "").replace(",", "").strip())


def verify_legitimacy(
    meta: Dict, transactions: List[Dict], raw_header: Optional[str]
) -> List[Dict]:
    checks = []

    # 1. Account number basic sanity (NUBAN format: 10 digits)
    ok_acct = _is_nuban_10_digits(meta.get("account_number"))
    checks.append(
        {
            "id": "acct_nuban_format",
            "ok": ok_acct,
            "severity": "good" if ok_acct else "fail",
            "message": "Account number should be 10 digits (NUBAN).",
            "details": {"account_number": (meta.get("account_number"))},
        }
    )

    # 2. Date window present
    has_dates = bool(meta.get("start_date") and meta.get("end_date"))
    checks.append(
        {
            "id": "period_present",
            "ok": has_dates,
            "severity": "good" if has_dates else "fail",
            "message": "Statement period (start/end) should be present.",
            "details": {"start": meta.get("start_date"), "end": meta.get("end_date")},
        }
    )

    # 3. Running balance monotonic math (when BALANCE present)
    math_ok = True
    prev_bal = None
    for i, r in enumerate(transactions):
        bal = r.get("BALANCE")
        if not bal:
            continue
        try:
            balf = float(bal.replace(",", ""))
        except:
            math_ok = False
            break
        if prev_bal is not None:
            # optional directional check; we don't know DR/CR mapping exactly across banks
            pass
        prev_bal = balf
    checks.append(
        {
            "id": "balance_numeric",
            "ok": math_ok,
            "severity": "warn" if math_ok else "fail",
            "message": "Transaction balances must be numeric and parseable.",
        }
    )

    # 4. Opening/closing vs pages (if present)
    opening = _money_to_float(meta.get("opening_balance"))
    closing = _money_to_float(meta.get("closing_balance"))
    if transactions:
        first_bal = None
        last_bal = None
        # grab first non-empty BALANCE and last non-empty BALANCE
        for r in transactions:
            if r.get("BALANCE"):
                first_bal = float(r["BALANCE"].replace(",", ""))
                break
        for r in reversed(transactions):
            if r.get("BALANCE"):
                last_bal = float(r["BALANCE"].replace(",", ""))
                break
        comp_ok = True
        reasons = {}
        if first_bal is not None and opening and abs(first_bal - opening) > 0.01:
            comp_ok = False
            reasons["first_vs_opening_diff"] = round(first_bal - opening, 2)
        if last_bal is not None and closing and abs(last_bal - closing) > 0.01:
            comp_ok = False
            reasons["last_vs_closing_diff"] = round(last_bal - closing, 2)

        checks.append(
            {
                "id": "opening_closing_consistency",
                "ok": comp_ok,
                "severity": "pass" if comp_ok else "fail",
                "message": "Opening/closing balance mismatch versus first/last page balances.",
                "details": reasons or None,
            }
        )
    else:
        checks.append(
            {
                "id": "no_transactions",
                "ok": False,
                "severity": "fail",
                "message": "No transactions parsed; cannot cross-check opening/closing.",
            }
        )

    # 5. Header markers found (“computer generated” messages that many banks include)
    header_ok = False
    if raw_header:
        t = raw_header.upper()
        if "THIS IS A COMPUTER GENERATED" in t or "CUSTOMER STATEMENT" in t:
            header_ok = True
    checks.append(
        {
            "id": "bank_header_watermark",
            "ok": header_ok,
            "severity": "info" if header_ok else "warn",
            "message": "Common bank statement watermark/header text seen.",
        }
    )

    return checks
