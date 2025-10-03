# banks/opay/universal.py
import sys, re, pdfplumber
from typing import List, Dict, Optional
from utils import normalize_date, normalize_money, to_float, calculate_checks

PRIMARY = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance": 3,
    "join_tolerance": 3,
    "min_words_vertical": 3,
    "min_words_horizontal": 1,
    "text_tolerance": 1,
}
FALLBACK = {
    "vertical_strategy": "text",
    "horizontal_strategy": "text",
    "snap_tolerance": 3,
    "join_tolerance": 3,
    "min_words_vertical": 1,
    "min_words_horizontal": 1,
    "text_tolerance": 1,
}

ALIASES = {
    "TXN_TIME": [
        "trans. time",
        "transaction time",
        "time",
        "txn time",
        "date/time",
        "trans time",
    ],
    "VAL_DATE": ["value date", "val date", "effective date", "value"],
    "REMARKS": [
        "description",
        "narration",
        "transaction details",
        "details",
        "remarks",
    ],
    "AMOUNT": [
        "debit/credit(₦)",
        "debit/credit(ngn)",
        "debit/credit",
        "amount(₦)",
        "amount (ngn)",
        "amount",
    ],
    "BALANCE": ["balance(₦)", "balance (ngn)", "balance", "current balance"],
    "REFERENCE": [
        "transaction reference",
        "reference",
        "transaction id",
        "txn id",
        "ref",
        "ref no",
    ],
}


def _map(headers: List[str]) -> List[str]:
    out = []
    for h in headers:
        key = (h or "").strip().lower()
        found = ""
        for std, opts in ALIASES.items():
            if key in opts:
                found = std
                break
        out.append(found)  # empty = ignored col (e.g., channel/counterparty)
    return out


RX_DATE = re.compile(
    r"(\d{4}-\d{2}-\d{2}|\d{2}\s+[A-Za-z]{3}\s+\d{4}|\d{2}/\d{2}/\d{4})"
)
RX_TIME = re.compile(r"\b\d{2}:\d{2}:\d{2}\b")
RX_SIGNED = re.compile(r"([+-]\s*[\d,]+(?:\.\d{2})?)")
RX_NUM = re.compile(r"(-?\s*[\d,]+(?:\.\d{2})?)")


def _extract_dates_amount_balance(blob: str):
    # Find first two dates in order
    dates = [m.group(0) for m in RX_DATE.finditer(blob)]
    txn_date = normalize_date(dates[0]) if dates else ""
    val_date = normalize_date(dates[1]) if len(dates) > 1 else ""
    # Signed amount (first signed number after dates)
    m_amt = RX_SIGNED.search(blob)
    amt = to_float(m_amt.group(1)) if m_amt else 0.0
    sign = (
        "+"
        if (m_amt and m_amt.group(1).strip().startswith("+"))
        else "-" if (m_amt and m_amt.group(1).strip().startswith("-")) else ""
    )
    # Balance: first plain number AFTER the signed amount
    bal = None
    if m_amt:
        m_bal = RX_NUM.search(blob[m_amt.end() :])
        if m_bal:
            bal = to_float(m_bal.group(1))
    return txn_date, val_date, amt, sign, bal


def _clean_remarks(blob: str):
    # Drop common channel tokens; keep readable text
    blob = re.sub(r"\b(E-Channel|POS|Web|Card)\b", "", blob, flags=re.I)
    return re.sub(r"\s+", " ", blob).strip()


def parse(path: str) -> List[Dict[str, str]]:
    txns: List[Dict[str, str]] = []

    try:
        with pdfplumber.open(path) as pdf:
            for pg, page in enumerate(pdf.pages, 1):
                print(f"(opay): Processing page {pg}", file=sys.stderr)
                tables = page.extract_tables(PRIMARY) or []
                if not tables:
                    tables = page.extract_tables(FALLBACK) or []

                # If we still have nothing, do text fallback later
                if not tables:
                    text = page.extract_text() or ""
                    lines = [ln for ln in text.splitlines() if ln.strip()]
                    # naive block collector: flush when we see second date + signed amt + balance
                    block = []
                    for ln in lines:
                        block.append(ln)
                        blob = " ".join(block)
                        td, vd, amt, sgn, bal = _extract_dates_amount_balance(blob)
                        if (td or vd) and (amt != 0 or sgn) and bal is not None:
                            debit = credit = 0.0
                            if sgn == "-":
                                debit = abs(amt)
                            elif sgn == "+":
                                credit = abs(amt)
                            txns.append(
                                {
                                    "TXN_DATE": td or vd,
                                    "VAL_DATE": vd,
                                    "REFERENCE": "",
                                    "REMARKS": _clean_remarks(blob),
                                    "DEBIT": f"{debit:.2f}",
                                    "CREDIT": f"{credit:.2f}",
                                    "BALANCE": f"{bal:.2f}",
                                    "Check": "",
                                    "Check 2": "",
                                }
                            )
                            block = []
                    continue

                header_map: Optional[List[str]] = None
                for tbl in tables:
                    if not tbl:
                        continue
                    first = tbl[0]
                    mapped = _map(first)

                    if any(mapped) and header_map is None:
                        header_map = mapped
                        data = tbl[1:]
                    elif any(mapped) and header_map is not None:
                        data = tbl[1:] if mapped == header_map else tbl
                    else:
                        data = tbl if header_map else []
                    if not header_map:
                        continue

                    idx = {
                        name: header_map.index(name) if name in header_map else None
                        for name in [
                            "TXN_TIME",
                            "VAL_DATE",
                            "REMARKS",
                            "AMOUNT",
                            "BALANCE",
                            "REFERENCE",
                        ]
                    }

                    for r in data:
                        if len(r) < len(header_map):
                            r = r + [""] * (len(header_map) - len(r))

                        # collapsed row: almost everything empty but one big blob
                        nonempty = [c for c in r if (c or "").strip()]
                        if len(nonempty) == 1:
                            blob = nonempty[0]
                            td, vd, amt, sgn, bal = _extract_dates_amount_balance(blob)
                            debit = credit = 0.0
                            if sgn == "-":
                                debit = abs(amt)
                            elif sgn == "+":
                                credit = abs(amt)
                            txns.append(
                                {
                                    "TXN_DATE": td or vd,
                                    "VAL_DATE": vd,
                                    "REFERENCE": "",
                                    "REMARKS": _clean_remarks(blob),
                                    "DEBIT": f"{debit:.2f}",
                                    "CREDIT": f"{credit:.2f}",
                                    "BALANCE": f"{bal:.2f}" if bal is not None else "",
                                    "Check": "",
                                    "Check 2": "",
                                }
                            )
                            continue

                        def cell(name: str) -> str:
                            i = idx[name]
                            return (r[i] if i is not None and i < len(r) else "") or ""

                        raw_time = cell("TXN_TIME")
                        raw_val = cell("VAL_DATE")
                        raw_desc = cell("REMARKS")
                        raw_amt = cell("AMOUNT")
                        raw_bal = cell("BALANCE")
                        raw_ref = cell("REFERENCE")

                        # If row looks empty except desc → continuation; append to last remarks
                        if (
                            not raw_time.strip()
                            and not raw_val.strip()
                            and not raw_amt.strip()
                            and not raw_bal.strip()
                            and raw_desc.strip()
                            and txns
                        ):
                            prev = txns[-1]
                            prev["REMARKS"] = _clean_remarks(
                                prev.get("REMARKS", "") + " " + raw_desc
                            )
                            continue

                        # Normal path
                        td, vd, amt, sgn, bal = _extract_dates_amount_balance(
                            " ".join([raw_time, raw_val, raw_amt, raw_bal])
                        )
                        # Prefer explicit mapping if the header cells are clean
                        if not td and raw_time:
                            td = normalize_date(raw_time)
                        if not vd and raw_val:
                            vd = normalize_date(raw_val)

                        debit = credit = 0.0
                        if sgn == "-":
                            debit = abs(amt)
                        elif sgn == "+":
                            credit = abs(amt)

                        txns.append(
                            {
                                "TXN_DATE": td or vd,
                                "VAL_DATE": vd,
                                "REFERENCE": raw_ref.strip(),
                                "REMARKS": _clean_remarks(raw_desc),
                                "DEBIT": f"{debit:.2f}",
                                "CREDIT": f"{credit:.2f}",
                                "BALANCE": (
                                    f"{to_float(raw_bal):.2f}"
                                    if raw_bal.strip()
                                    else (f"{bal:.2f}" if bal is not None else "")
                                ),
                                "Check": "",
                                "Check 2": "",
                            }
                        )

        # Infer unsigned amounts using balance delta
        prev = None
        for t in txns:
            d = to_float(t["DEBIT"])
            c = to_float(t["CREDIT"])
            cur = to_float(t.get("BALANCE", ""))
            if d == 0 and c == 0 and prev is not None and t.get("BALANCE"):
                if cur > prev:
                    t["CREDIT"] = normalize_money(str(cur - prev))
                elif cur < prev:
                    t["DEBIT"] = normalize_money(str(prev - cur))
            t["DEBIT"] = normalize_money(t["DEBIT"])
            t["CREDIT"] = normalize_money(t["CREDIT"])
            prev = cur if t.get("BALANCE") else prev

        return calculate_checks([t for t in txns if t["TXN_DATE"] or t["VAL_DATE"]])

    except Exception as e:
        print(f"Error processing Opay statement: {e}", file=sys.stderr)
        return []
