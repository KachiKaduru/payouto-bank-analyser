import re
import sys
import pdfplumber
from typing import List, Dict, Optional

from utils import normalize_date, calculate_checks

ROW_START_RE = re.compile(r"^(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\b")
MONEY_TOKEN_RE = re.compile(r"-?\d[\d,]*\.\d{2}")


def _money_to_str(x: Optional[float]) -> str:
    if x is None:
        return "0.00"
    return f"{x:.2f}"


def _parse_money(s: str) -> float:
    return float(s.replace(",", "").strip())


def _chars_to_lines(chars, y_tol=2.0, space_gap=1.8):
    chars_sorted = sorted(chars, key=lambda c: (c["top"], c["x0"]))
    lines = []
    for ch in chars_sorted:
        if not lines or abs(ch["top"] - lines[-1]["top"]) > y_tol:
            lines.append({"top": ch["top"], "chars": [ch]})
        else:
            lines[-1]["chars"].append(ch)

    out = []
    for ln in lines:
        cs = sorted(ln["chars"], key=lambda c: c["x0"])
        text = ""
        prev_x1 = None
        for c in cs:
            if prev_x1 is not None and (c["x0"] - prev_x1) > space_gap:
                text += " "
            text += c["text"]
            prev_x1 = c["x1"]
        out.append({"top": ln["top"], "text": text.strip(), "chars": cs})
    return out


def _extract_amount_groups(line_chars):
    def is_num_char(t: str) -> bool:
        return t.isdigit() or t in ",.-"

    groups = []
    cur = []
    for ch in sorted(line_chars, key=lambda c: c["x0"]):
        if is_num_char(ch["text"]):
            if cur and (ch["x0"] - cur[-1]["x1"]) > 2.0:
                groups.append(cur)
                cur = []
            cur.append(ch)
        else:
            if cur:
                groups.append(cur)
                cur = []
    if cur:
        groups.append(cur)

    out = []
    for g in groups:
        txt = "".join(c["text"] for c in g).strip()
        if re.fullmatch(r"-?\d[\d,]*\.\d{2}", txt):
            out.append(
                {
                    "text": txt,
                    "x0": min(c["x0"] for c in g),
                    "x1": max(c["x1"] for c in g),
                }
            )
    return sorted(out, key=lambda a: a["x0"])


def _remove_extracted_money_from_remarks(
    remarks: str, debit: float | None, credit: float | None, balance: float | None
) -> str:
    """
    Remove only money tokens that match the extracted debit/credit/balance values,
    wherever they occur in the remarks string.
    """
    targets = []
    if debit is not None and abs(debit) > 1e-9:
        targets.append(debit)
    if credit is not None and abs(credit) > 1e-9:
        targets.append(credit)
    if balance is not None:
        targets.append(balance)

    if not targets:
        return remarks.strip()

    def should_remove(token: str) -> bool:
        try:
            val = _parse_money(token)
        except Exception:
            return False
        # tolerance for float formatting noise
        return any(abs(val - t) < 0.005 for t in targets)

    # rebuild remarks, skipping only matching money tokens
    parts = []
    last = 0
    for m in MONEY_TOKEN_RE.finditer(remarks):
        tok = m.group(0)
        if should_remove(tok):
            parts.append(remarks[last : m.start()])
            last = m.end()
    parts.append(remarks[last:])
    cleaned = "".join(parts)

    # normalize whitespace
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


def parse(
    pdf_path: str,
    password: Optional[str] = None,
) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []

    found_txn_section = False
    current = None  # keep across pages

    with pdfplumber.open(pdf_path, password=password) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            # for page in pdf.pages:
            print(f"(uba:model_02) page {pno}", file=sys.stderr)

            lines = _chars_to_lines(page.chars)

            for ln in lines:
                t = ln["text"]

                # flip on once; keep on for the rest of the doc
                if ("Your Transactions" in t) or t.startswith("Transaction Date"):
                    found_txn_section = True

                if not found_txn_section:
                    continue

                # skip obvious non-table stuff
                if not t or t.startswith("Account Statement") or t.startswith("Page "):
                    continue
                if t.startswith("Transaction Date") or t.startswith("Value Date"):
                    continue

                m = ROW_START_RE.match(t)
                if m:
                    if current:
                        rows.append(current)

                    txn_date, val_date = m.group(1), m.group(2)
                    current = {
                        "_first_line_chars": ln["chars"],
                        "_raw_lines": [t],
                        "TXN_DATE": normalize_date(txn_date),
                        "VAL_DATE": normalize_date(val_date),
                        "REFERENCE": "",
                        "REMARKS": "",
                        "DEBIT": "0.00",
                        "CREDIT": "0.00",
                        "BALANCE": "0.00",
                    }
                else:
                    # continuation line for current txn narration
                    if current and t:
                        current["_raw_lines"].append(t)

        # flush last txn at document end
        if current:
            rows.append(current)

    cleaned: List[Dict[str, str]] = []
    for r in rows:
        raw_joined = " ".join(r["_raw_lines"]).strip()

        # amounts from first physical line of the txn (most stable)
        amounts = _extract_amount_groups(r["_first_line_chars"])

        balance = None
        debit = None
        credit = None

        if amounts:
            balance_grp = max(amounts, key=lambda a: a["x0"])
            balance = _parse_money(balance_grp["text"])

            left_of_balance = [a for a in amounts if a["x0"] < balance_grp["x0"]]
            amt_grp = (
                max(left_of_balance, key=lambda a: a["x0"]) if left_of_balance else None
            )

            if amt_grp:
                amt = _parse_money(amt_grp["text"])

                # threshold separating withdrawal vs deposit columns (tuned from your sample)
                if amt_grp["x0"] < 520:
                    debit = amt
                else:
                    credit = amt

        # build remarks: remove leading dates, then remove only extracted money tokens wherever they appear
        remarks = ROW_START_RE.sub("", raw_joined).strip()
        remarks = _remove_extracted_money_from_remarks(remarks, debit, credit, balance)

        r["REMARKS"] = remarks
        r["DEBIT"] = _money_to_str(debit)
        r["CREDIT"] = _money_to_str(credit)
        r["BALANCE"] = _money_to_str(balance if balance is not None else 0.0)

        # cleanup internals
        r.pop("_first_line_chars", None)
        r.pop("_raw_lines", None)

        cleaned.append(r)

    cleaned.reverse()  # chronological order

    transactions = calculate_checks(cleaned)

    return transactions
