# banks/opay/universal.py
import sys
import re
from typing import List, Dict

import pdfplumber

from utils import STANDARDIZED_ROW, normalize_date, calculate_checks

# A transaction block starts with: "2025 Mar 15 06:22:57 15 Mar 2025 ..."
START_RE = re.compile(
    r"^\s*\d{4}\s+\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+\d{1,2}\s+\w{3}\s+\d{4}"
)

# Amount + balance pair, allow +, -, or plain positive numbers
AMOUNT_BAL_RE = re.compile(r"([+-]?\d[\d,]*\.\d{2})\s+([\d,]+\.\d{2})")

# Channel keywords between balance and reference
CHANNEL_RE = re.compile(
    r"\b(E-Channel|POS|OPay|Palmpay|MONIE POINT|ATM|WebTB)\b",
    flags=re.IGNORECASE,
)


def parse(path: str) -> List[Dict[str, str]]:
    """
    Parse an Opay PDF statement where each transaction may span multiple lines.
    Returns a list of standardized rows (STANDARDIZED_ROW shape) and runs calculate_checks().
    """
    transactions: List[Dict[str, str]] = []

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                print(f"(opay): Processing page {page_num}", file=sys.stderr)
                text = page.extract_text(x_tolerance=2, y_tolerance=2)
                if not text:
                    continue

                # normalize lines and drop empty lines
                lines = [ln for ln in text.splitlines() if ln.strip()]

                # group lines into transaction blocks (new block when START_RE matches)
                blocks = []
                current_block = []
                for ln in lines:
                    if START_RE.match(ln):
                        if current_block:
                            blocks.append("\n".join(current_block))
                        current_block = [ln]
                    else:
                        current_block.append(ln)
                if current_block:
                    blocks.append("\n".join(current_block))

                # parse each block
                for block in blocks:
                    s = re.sub(r"\s+", " ", block).strip()

                    # Skip non-transaction blocks (cover info, headers)
                    if not START_RE.match(s):
                        continue

                    # Find the last amount+balance occurrence
                    matches = list(AMOUNT_BAL_RE.finditer(s))
                    if not matches:
                        continue  # silently skip if no amount+balance
                    m = matches[-1]
                    amount_str = m.group(1)
                    balance_str = m.group(2)

                    # Split prefix/suffix around amount-balance
                    prefix = s[: m.start()].strip()
                    suffix = s[m.end() :].strip()

                    # Extract value date + remarks
                    header_re = re.compile(
                        r"^(?P<trans_time>\d{4}\s+\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+(?P<val_date>\d{1,2}\s+\w{3}\s+\d{4})\s*(?P<rest>.*)$"
                    )
                    hm = header_re.match(prefix)
                    if hm:
                        val_date = hm.group("val_date")
                        remarks = hm.group("rest").strip()
                    else:
                        vd = re.search(r"\d{1,2}\s+\w{3}\s+\d{4}", prefix)
                        val_date = vd.group(0) if vd else ""
                        remarks = prefix

                    # Reference: after channel keyword OR last long number
                    ref = ""
                    ch = CHANNEL_RE.search(suffix)
                    if ch:
                        tail = suffix[ch.end() :].strip()
                        tk = re.search(r"([A-Za-z0-9\-]{6,})", tail)
                        if tk:
                            ref = tk.group(1)
                    if not ref:
                        nums = re.findall(r"\b\d{6,}\b", s)
                        if nums:
                            ref = nums[-1]

                    # Clean remarks: remove any trailing channel fragments
                    remarks = re.sub(
                        r"\s*(E-Channel|POS|OPay|Palmpay|MONIE POINT|ATM|WebTB)\b.*$",
                        "",
                        remarks,
                        flags=re.IGNORECASE,
                    ).strip()

                    # Build standardized row
                    row = STANDARDIZED_ROW.copy()
                    row["TXN_DATE"] = normalize_date(val_date)
                    row["VAL_DATE"] = normalize_date(val_date)
                    row["REFERENCE"] = ref or ""
                    row["REMARKS"] = remarks

                    amt = amount_str.replace(",", "")
                    if amt.startswith("-"):
                        row["DEBIT"] = amt.lstrip("-")
                        row["CREDIT"] = "0.00"
                    else:
                        row["DEBIT"] = "0.00"
                        row["CREDIT"] = amt.lstrip("+")

                    row["BALANCE"] = balance_str.replace(",", "")

                    transactions.append(row)

        # run balance checks and return
        return calculate_checks(transactions)

    except Exception as e:
        print(f"Error processing Opay statement: {e}", file=sys.stderr)
        return []
