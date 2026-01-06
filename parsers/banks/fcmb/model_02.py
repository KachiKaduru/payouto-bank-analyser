# banks/fcmb/model_02.py
import re
import sys
import pdfplumber
from typing import List, Dict, Optional

from app.parsers.utils import normalize_date, to_float, calculate_checks

DATE_RX = re.compile(r"^(?P<d>\d{2}\s+[A-Za-z]{3}\s+\d{4})\b")
MONEY_RX = re.compile(r"^-?\d{1,3}(?:,\d{3})*(?:\.\d{2})?$")


def _norm_space_date(s: str) -> str:
    # normalize_date() already supports "%d %b %Y" in your utils.py
    return normalize_date(s)


def _clean_money_token(tok: str) -> str:
    return (tok or "").replace("{", "").replace("}", "").strip()


def parse(path: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    prev_balance: Optional[float] = None

    with pdfplumber.open(path) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            print(f"(fcmb:model_02) page {pno}", file=sys.stderr)
            text = page.extract_text() or ""
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue

                # must start with "DD Mon YYYY"
                m = DATE_RX.match(line)
                if not m:
                    continue

                parts = line.split()
                if len(parts) < 3:
                    continue

                txn_raw = " ".join(parts[:3])
                txn_date = _norm_space_date(txn_raw)

                # value date may follow
                val_date = ""
                rest_tokens = parts[3:]
                if len(rest_tokens) >= 3 and DATE_RX.match(" ".join(rest_tokens[:3])):
                    val_raw = " ".join(rest_tokens[:3])
                    val_date = _norm_space_date(val_raw)
                    rest_tokens = rest_tokens[3:]

                # peel trailing money tokens
                money: List[str] = []
                i = len(rest_tokens) - 1
                while i >= 0:
                    tok = _clean_money_token(rest_tokens[i])
                    if MONEY_RX.match(tok):
                        money.append(tok)
                        i -= 1
                    else:
                        break
                money = list(reversed(money))
                narration = " ".join(rest_tokens[: i + 1]).strip().lower()

                if not money:
                    continue

                # Opening balance / carried forward lines
                if "opening balance" in narration:
                    prev_balance = to_float(money[-1])
                    continue
                if "balance carried forward" in narration:
                    prev_balance = to_float(money[-1])
                    continue

                balance_f = to_float(money[-1])
                amount_f = to_float(money[-2]) if len(money) >= 2 else 0.0

                debit = "0.00"
                credit = "0.00"
                if prev_balance is not None and len(money) >= 2:
                    if balance_f < prev_balance:
                        debit = f"{abs(amount_f):.2f}"
                    else:
                        credit = f"{abs(amount_f):.2f}"

                # keep original narration (not lowercased) if you want:
                narration_original = " ".join(rest_tokens[: i + 1]).strip()

                rows.append(
                    {
                        "TXN_DATE": txn_date,
                        "VAL_DATE": val_date,
                        "REFERENCE": "",
                        "REMARKS": narration_original,
                        "DEBIT": debit,
                        "CREDIT": credit,
                        "BALANCE": f"{balance_f:.2f}",
                    }
                )
                prev_balance = balance_f

    return calculate_checks(rows)
