# banks/access/parser_003.py
import re
import sys
import pdfplumber
from typing import List, Dict, Optional

from utils import (
    normalize_column_name,
    MAIN_TABLE_SETTINGS,
    parse_text_row,
    normalize_date,
    normalize_money,
    calculate_checks,
)

# Known header layout (we'll use normalized form for parse_text_row when possible)
KNOWN_HEADERS = [
    "S/NO",
    "DATE",
    "TRANSACTION DETAILS",
    "REF. NO",
    "VALUE DATE",
    "WITHDRAWAL",
    "LODGEMENT",
    "BALANCE",
]

# Regex helpers
# Access statements often show 01-APR-25, 01-Apr-2025, or 1 Apr 25
RX_TXN_DATE = re.compile(r"\b\d{1,2}[-/\s][A-Za-z]{3}[-/\s]?\d{2,4}\b", re.IGNORECASE)
RX_VAL_DATE = re.compile(r"\b\d{1,2}[-/\s][A-Za-z]{3}[-/\s]?\d{2,4}\b", re.IGNORECASE)

RX_AMOUNT = re.compile(r"-?\d{1,3}(?:,\d{3})*(?:\.\d{2})?")  # amounts with commas
# RX_AMOUNT_LIKE = re.compile(r"^\s*[-\d,]+(?:\.\d{2})?\s*$")

RX_REF_DIGITS = re.compile(r"\b\d{6,}\b")
RX_REF_ALNUM = re.compile(r"\b[A-Z0-9_]{6,}\b", re.IGNORECASE)

RX_REFERENCE = re.compile(
    r"(PP_[A-Z0-9_]{3,}(?:\s*\d+[A-Z0-9_]*\s*){0,3}_+)",  # Handles multi-line, like "PP_SUSP_1655 47_1063874174 _"
    re.IGNORECASE,
)


def _join_cells(row: List[Optional[str]]) -> str:
    return " ".join((str(c or "")).strip() for c in row if (c or "").strip())


def _extract_amounts_from_text(text: str) -> List[str]:
    return RX_AMOUNT.findall(text)


def _pick_reference(text: str) -> Optional[str]:
    # prefer long digit-only refs
    digit_cands = RX_REF_DIGITS.findall(text or "")
    if digit_cands:
        return digit_cands[0]
    alnum = RX_REFERENCE.findall(text or "")
    return alnum[0] if alnum else None


def _parse_freestyle_row(row_cells: List[Optional[str]]) -> Dict[str, str]:
    """
    Parse a single table row by joining cells and extracting fields by content.
    This is the fallback used for misaligned rows (page 1 issues).
    """
    joined = _join_cells(row_cells)
    out = {
        "TXN_DATE": "",
        "VAL_DATE": "",
        "REFERENCE": "",
        "REMARKS": "",
        "DEBIT": "0.00",
        "CREDIT": "0.00",
        "BALANCE": "",
    }

    # 1) TXN_DATE: prefer a mm/dd/yyyy at start, else first occurrence
    m_tx = RX_TXN_DATE.search(joined)
    if m_tx:
        out["TXN_DATE"] = normalize_date(m_tx.group(0))
        if not out["TXN_DATE"] and row_cells:
            first = (row_cells[0] or "").strip()
            # sometimes the first cell literally contains '01-Apr-25' or '1-Apr-2025'
            if RX_TXN_DATE.match(first):
                out["TXN_DATE"] = normalize_date(first)

    # 2) VAL_DATE: look for dd-Mmm-YYYY anywhere
    m_val = RX_VAL_DATE.search(joined)
    if m_val:
        out["VAL_DATE"] = normalize_date(m_val.group(0))

    # 3) Amounts: pick last 3 monetary tokens from the joined text
    amounts = [a for a in _extract_amounts_from_text(joined) if a.strip()]
    if len(amounts) >= 3:
        # last three map to (debit, credit, balance) normally in this statement's display
        # But sometimes statement uses Withdrawals (debit) then Lodgement (credit)
        last3 = amounts[-3:]
        out["DEBIT"] = normalize_money(last3[0])
        out["CREDIT"] = normalize_money(last3[1])
        out["BALANCE"] = normalize_money(last3[2])
    elif len(amounts) == 2:
        # ambiguous — assume (debit?, credit?, balance)
        # Usually two means (withdrawal, balance) or (lodgement, balance)
        # We'll heuristically treat amounts[-2] as DEBIT if remarks contain 'fee','charge' -> debit, else treat as CREDIT
        cand0, cand1 = amounts[-2], amounts[-1]
        # naive heuristic: if words like 'fee', 'charge', 'tax', 'commission' in text -> debit
        if re.search(
            r"\b(fee|charge|vat|commission|tax|levy)\b", joined, re.IGNORECASE
        ):
            out["DEBIT"] = normalize_money(cand0)
            out["CREDIT"] = "0.00"
            out["BALANCE"] = normalize_money(cand1)
        else:
            # often deposit rows show lodgement then balance
            out["DEBIT"] = "0.00"
            out["CREDIT"] = normalize_money(cand0)
            out["BALANCE"] = normalize_money(cand1)
    elif len(amounts) == 1:
        # last token is likely balance OR a single amount line (treat as balance)
        out["BALANCE"] = normalize_money(amounts[-1])

    # 4) REFERENCE: pick best candidate from the joined text but avoid picking the val_date or amounts
    ref = _pick_reference(joined)
    if ref:
        out["REFERENCE"] = ref

    # 5) REMARKS: remove tx dates, val dates, amounts and reference from joined text to get narration
    cleaned = joined
    if m_tx:
        cleaned = cleaned.replace(m_tx.group(0), " ")
    if m_val:
        cleaned = cleaned.replace(m_val.group(0), " ")
    if ref:
        cleaned = cleaned.replace(ref, " ", 1)
    # remove amounts
    cleaned = RX_AMOUNT.sub(" ", cleaned)
    # collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Remove leading serial numbers or index numbers like "1 " or "01 " at start
    cleaned = re.sub(r"^\d{1,3}\s+", "", cleaned)

    out["REMARKS"] = cleaned

    # Final clean-up: format TXN_DATE & VAL_DATE empty->"" and ensure DEBIT/CREDIT have 2dp
    for k in ("DEBIT", "CREDIT", "BALANCE"):
        out[k] = normalize_money(out.get(k, "0.00"))

    # If TXN_DATE missing but first token is date-like in row_cells[0], try that
    if not out["TXN_DATE"] and row_cells:
        first = (row_cells[0] or "").strip()
        if RX_TXN_DATE.match(first):
            out["TXN_DATE"] = normalize_date(first)

    return out


def _row_looks_misaligned(row_cells: List[Optional[str]]) -> bool:
    """
    Heuristic to detect misaligned rows:
    - if a cell expected to be VAL_DATE contains long digit ref
    - or last cell (balance) is empty while amounts appear earlier
    - or the 4th cell (REF) is much longer (contains many digits) and the 5th cell looks like non-date
    """
    # make a copy of textual cells
    cells = [str(c or "").strip() for c in row_cells]
    # if less than expected columns, treat as misaligned
    if len(cells) < 6:
        return True

    # sample indices for normalized layout (after possibly dropping S/NO)
    # expected: [DATE, TRANSACTION DETAILS, REF, VAL_DATE, WITHDRAWAL, LODGEMENT, BALANCE]
    # check if any of the following holds:
    # - cell[2] (REF) empty but cell[3] contains long digits -> misaligned
    if len(cells) > 3:
        c2 = cells[2]
        c3 = cells[3]
        if c3 and RX_REF_DIGITS.search(c3) and (not c2 or len(c2) < 4):
            return True
    # - last cell empty but there are 1-3 amount-like tokens earlier
    last = cells[-1] if cells else ""
    amounts = _extract_amounts_from_text(" ".join(cells))
    if not last.strip() and len(amounts) >= 2:
        return True

    # - 4th cell does not look like a value date yet looks like alnum ref
    if (
        len(cells) > 3
        and not RX_VAL_DATE.search(cells[3])
        and RX_REF_ALNUM.search(cells[3])
    ):
        return True

    return False


def parse(path: str) -> List[Dict[str, str]]:
    transactions: List[Dict[str, str]] = []

    # normalized headers for parse_text_row (drop S/NO)
    normalized_headers = [normalize_column_name(h) for h in KNOWN_HEADERS]
    normalized_headers_no_serial = normalized_headers[1:]

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                print(f"(access:003): Processing page {page_num}", file=sys.stderr)
                table_settings = MAIN_TABLE_SETTINGS.copy()
                tables = page.extract_tables(table_settings)

                if not tables:
                    print(
                        f"(access:003): No tables found on page {page_num}",
                        file=sys.stderr,
                    )
                    continue

                for table in tables:
                    if not table or len(table) < 2:
                        continue

                    # skip summary-like small tables
                    if len(table[0]) <= 3:
                        continue

                    for raw_row in table:
                        if not raw_row:
                            continue

                        # Drop S/NO if present (common case)
                        row = raw_row[1:] if len(raw_row) >= 8 else raw_row[:]

                        # skip header-like rows
                        joined_header_check = " ".join(
                            str(c or "").strip().lower() for c in row if c
                        )
                        if any(
                            k in joined_header_check
                            for k in (
                                "date",
                                "transaction details",
                                "ref. no",
                            )
                        ):
                            continue

                        # If row looks misaligned (especially page 1), parse freestyle
                        if page_num == 1 or _row_looks_misaligned(row):
                            parsed = _parse_freestyle_row(row)
                            # merge into standardized row shape expected by calculate_checks
                            standardized = {
                                "TXN_DATE": parsed.get("TXN_DATE", "") or "",
                                "VAL_DATE": parsed.get("VAL_DATE", "") or "",
                                "REFERENCE": parsed.get("REFERENCE", "") or "",
                                "REMARKS": parsed.get("REMARKS", "") or "",
                                "DEBIT": parsed.get("DEBIT", "0.00") or "0.00",
                                "CREDIT": parsed.get("CREDIT", "0.00") or "0.00",
                                "BALANCE": parsed.get("BALANCE", "") or "",
                            }
                            transactions.append(standardized)
                            continue

                        # Otherwise use column-based parser (works for pages 2+ and well-formed rows)
                        # Ensure we have same number of columns as normalized_headers_no_serial
                        row_cells = list(row)
                        if len(row_cells) < len(normalized_headers_no_serial):
                            row_cells += [""] * (
                                len(normalized_headers_no_serial) - len(row_cells)
                            )
                        elif len(row_cells) > len(normalized_headers_no_serial):
                            row_cells = row_cells[: len(normalized_headers_no_serial)]

                        standardized = parse_text_row(
                            row_cells, normalized_headers_no_serial
                        )
                        transactions.append(standardized)

        # final filtering and checks
        clean = [t for t in transactions if t.get("TXN_DATE") or t.get("VAL_DATE")]
        print(
            f"(access:003): Parsed {len(clean)} candidate transactions", file=sys.stderr
        )
        return calculate_checks(clean)

    except Exception as e:
        print(f"(access:003): ERROR parsing statement: {e}", file=sys.stderr)
        return []
