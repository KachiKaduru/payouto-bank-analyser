import pdfplumber
import re
import sys
from typing import List, Dict, Optional
from utils import (
    normalize_date,
    normalize_money,
    calculate_checks,
    merge_and_drop_year_artifacts,
)

# === Regex patterns ===
RX_TXN_DATE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b")  # 3/26/2025
RX_TIME = re.compile(r"\d{1,2}:\d{2}:\d{2}\s*(?:AM|PM|am|pm)?")  # 3:46:29 PM
RX_ALPHA_MONTH_SLASH = re.compile(r"(\d{1,2})/([A-Za-z]{3})/(\d{4})")  # 17/Oct/2025
RX_VAL_DATE = re.compile(r"\b\d{1,2}[-/][A-Za-z]{3}[-/]\d{2,4}\b")  # 26-Mar-2025
RX_AMOUNT = re.compile(r"[-]?\d{1,3}(?:,\d{3})*(?:\.\d{2})?")
RX_REF = re.compile(r"^'?\s*[\dA-Za-z\-/]{3,}")  # relaxed reference detection
RX_FOOTER = re.compile(
    r"(statement summary|closing balance|account summary|please address|opening balance|total|balance carried forward)",
    re.I,
)


# === helpers ===
def _clean_date(token: str) -> str:
    if not token:
        return token
    token = RX_TIME.sub("", token).strip()
    token = RX_ALPHA_MONTH_SLASH.sub(r"\1-\2-\3", token)
    return token


def _is_amount_line(line: str) -> bool:
    # amount line usually has at least 2 numeric groups (debit/credit or amount+balance)
    found = RX_AMOUNT.findall(line)
    return len(found) >= 2


def _likely_ref(line: str) -> bool:
    return bool(RX_REF.match(line)) or "ref" in line.lower()


def _is_footer(line: str) -> bool:
    return bool(RX_FOOTER.search(line))


def _strip_header_artifacts(line: str) -> bool:
    """
    Return True if this line looks like a header artifact (contains date/trans/value words
    but doesn't contain any real date token) — those should be ignored.
    """
    low = line.lower()
    if ("trans" in low or "txn" in low or "value" in low or "date" in low) and not (
        RX_TXN_DATE.search(line) or RX_VAL_DATE.search(line)
    ):
        # also ignore very short header pieces like "Date Date" or "Value Date"
        return True
    return False


# === main ===
def parse(pdf_path: str) -> List[Dict[str, str]]:
    print("(gtb_model_01): Parsing GTBank Primelog statement...", file=sys.stderr)
    txns: List[Dict[str, str]] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            print(f"(gtb_model_01): Page {page_no}", file=sys.stderr)
            raw = page.extract_text() or ""
            lines = [ln.rstrip() for ln in raw.splitlines() if ln.strip()]
            if not lines:
                continue

            # merge broken date/time/value fragments
            merged = []
            i = 0
            while i < len(lines):
                ln = lines[i].strip()

                # header-like lines may be split: merge the next line if it helps make a date
                if (
                    RX_TXN_DATE.search(ln)
                    and i + 1 < len(lines)
                    and RX_TIME.search(lines[i + 1])
                ):
                    merged.append(f"{ln} {lines[i+1].strip()}")
                    i += 2
                    continue

                # join value-date split like "26-Mar-" + "2025"
                if (
                    ln.endswith("-")
                    and i + 1 < len(lines)
                    and re.match(r"^\d{4}$", lines[i + 1].strip())
                ):
                    merged.append(ln + lines[i + 1].strip())
                    i += 2
                    continue

                # If current line is a short header fragment like "Trans" and next line "Date", merge them
                if ln.lower() in (
                    "trans",
                    "value",
                    "date",
                    "trans date",
                    "value date",
                ) and i + 1 < len(lines):
                    merged.append(ln + " " + lines[i + 1].strip())
                    i += 2
                    continue

                merged.append(ln)
                i += 1

            # locate header row (the visual header "Trans\nDate ... Remarks")
            start = 0
            for idx, ln in enumerate(merged):
                low = ln.lower()
                if ("trans" in low or "txn" in low) and (
                    "remark" in low or "remarks" in low or "remarks" in low
                ):
                    start = idx + 1
                    break

            # parse after header
            current = {
                "TXN_DATE": "",
                "VAL_DATE": "",
                "REFERENCE": "",
                "REMARKS": "",
                "DEBIT": "0.00",
                "CREDIT": "0.00",
                "BALANCE": "",
            }

            for ln in merged[start:]:
                if _is_footer(ln):
                    break

                # drop header artifacts that don't contain real date tokens (fix for "Date Date")
                if _strip_header_artifacts(ln):
                    # do not treat as remarks; skip
                    continue

                # transaction date: if found, start a new transaction boundary
                tdm = RX_TXN_DATE.search(ln)
                if tdm:
                    token = _clean_date(tdm.group())
                    # push previous if it has any meaningful content
                    if (
                        current["BALANCE"]
                        or (current["DEBIT"] and current["DEBIT"] != "0.00")
                        or (current["CREDIT"] and current["CREDIT"] != "0.00")
                        or current["REMARKS"].strip()
                        or current["REFERENCE"].strip()
                    ):
                        txns.append(current)
                        current = {
                            "TXN_DATE": "",
                            "VAL_DATE": "",
                            "REFERENCE": "",
                            "REMARKS": "",
                            "DEBIT": "0.00",
                            "CREDIT": "0.00",
                            "BALANCE": "",
                        }
                    current["TXN_DATE"] = normalize_date(token)
                    # sometimes the same line also contains ref/amounts after the date — process remainder
                    remainder = ln[tdm.end() :].strip()
                    if remainder:
                        ln = remainder  # fall through to process amounts/ref on same line
                    else:
                        continue

                # value date (like '26-Mar-2025') might appear on its own or on amount line
                vd = RX_VAL_DATE.search(ln)
                if vd:
                    token = _clean_date(vd.group())
                    current["VAL_DATE"] = normalize_date(token)
                    # remove the found token from the line so it doesn't pollute narration
                    ln = ln[: vd.start()] + ln[vd.end() :]

                # If this line looks like an amount line (2+ numeric groups), parse numbers and treat the
                # surrounding text as reference/remarks
                if _is_amount_line(ln):
                    nums = RX_AMOUNT.findall(ln)
                    # map numeric groups -> debit/credit/balance heuristics
                    if len(nums) >= 3:
                        # common: [debit or credit, maybe fee, balance] OR [credit, ?, balance]
                        # We'll take last as balance, first as debit or credit depending on minus sign
                        balance_raw = nums[-1]
                        first_raw = nums[0]
                        middle_raw = nums[1] if len(nums) >= 3 else None

                        current["BALANCE"] = normalize_money(balance_raw)
                        # determine sign context for first amount
                        if "-" in first_raw or re.search(
                            r"\bwithdraw|debit|dr\b", ln, re.I
                        ):
                            current["DEBIT"] = normalize_money(first_raw)
                        else:
                            current["CREDIT"] = normalize_money(first_raw)

                        # if a middle number looks like a second amount (sometimes it's credit), try to fill it
                        if middle_raw:
                            # if first number already assigned as credit, middle likely debit (rare)
                            if (
                                current["CREDIT"] != "0.00"
                                and current["DEBIT"] == "0.00"
                            ):
                                current["DEBIT"] = normalize_money(middle_raw)
                            elif (
                                current["DEBIT"] != "0.00"
                                and current["CREDIT"] == "0.00"
                            ):
                                current["CREDIT"] = normalize_money(middle_raw)
                    elif len(nums) == 2:
                        # interpret as [amount, balance] or [debit/credit, balance]
                        amt_raw, bal_raw = nums[0], nums[1]
                        current["BALANCE"] = normalize_money(bal_raw)
                        # choose debit vs credit by presence of minus or 'BR' 'DR' context
                        if "-" in amt_raw or re.search(
                            r"\bwithdraw|debit|dr\b", ln, re.I
                        ):
                            current["DEBIT"] = normalize_money(amt_raw)
                        else:
                            current["CREDIT"] = normalize_money(amt_raw)

                    # extract the textual pieces around the numeric groups as reference/remarks
                    # remove the numeric substrings to get pure text
                    text_only = RX_AMOUNT.sub(" ", ln).strip()
                    # often the reference is at the start (e.g. "'24747419..." or "'BR"), use that
                    text_only = re.sub(r"\s{2,}", " ", text_only).strip()
                    if text_only:
                        # split typical patterns: leading token as reference if short, rest as remarks
                        parts = text_only.split(" ", 1)
                        first_part = parts[0].strip()
                        rest = parts[1].strip() if len(parts) > 1 else ""

                        # clean leading apostrophes in references
                        cleaned_first = first_part.lstrip("'").strip()
                        # heuristics to decide if first token is a reference (numbers/short alpha)
                        if len(cleaned_first) <= 20 and re.search(
                            r"[0-9A-Za-z]", cleaned_first
                        ):
                            # assign as reference and append rest to remarks
                            if not current["REFERENCE"]:
                                current["REFERENCE"] = cleaned_first
                            if rest:
                                current["REMARKS"] += " " + rest
                        else:
                            current["REMARKS"] += " " + text_only

                    continue  # processed this line as amount+text; continue to next

                # references (lines starting with apostrophe or REF token)
                if _likely_ref(ln):
                    clean = ln.strip().lstrip("'").strip()
                    if not current["REFERENCE"]:
                        current["REFERENCE"] = clean
                    else:
                        current["REMARKS"] += " " + clean
                    continue

                # ignore standalone AM/PM or very short tokens that got mis-extracted
                if re.fullmatch(r"(AM|PM|am|pm|:|,|-)+", ln.strip()):
                    continue

                # otherwise treat as narration/remarks
                current["REMARKS"] += " " + ln.strip()

            # flush last txn from this page if it has meaningful content
            if (
                current["BALANCE"]
                or (current["DEBIT"] and current["DEBIT"] != "0.00")
                or (current["CREDIT"] and current["CREDIT"] != "0.00")
                or current["REMARKS"].strip()
                or current["REFERENCE"].strip()
            ):
                txns.append(current)

    # Final cleaning & checks
    txns = merge_and_drop_year_artifacts(txns)
    txns = calculate_checks(txns)

    print(f"(gtb_model_01): ✅ Parsed {len(txns)} transactions", file=sys.stderr)
    return txns
