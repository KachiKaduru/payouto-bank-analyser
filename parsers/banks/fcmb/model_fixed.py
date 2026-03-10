import re
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pdfplumber

from utils import (
    MAIN_TABLE_SETTINGS,
    to_float,
    normalize_money,
    normalize_date,
    normalize_column_name,
    calculate_checks,
    parse_text_row,
)


RX_TXN_LINE = re.compile(
    r"^(?P<txn_date>\d{2}-[A-Za-z]{3}-\d{4})\s+"
    r"(?P<body>.*?)\s+"
    r"(?P<val_date>\d{2}-[A-Za-z]{3}-\d{4})\s+"
    r"(?P<amount>[\d,]+\.\d{2})\s+"
    r"(?P<balance>[\d,]+\.\d{2})\s+"
    r"(?P<side>Cr|Dr)$",
    re.IGNORECASE,
)
RX_PAGE_STAMP = re.compile(r"^\d{1,2}/\d{1,2}/\d{2},")
RX_HEADERISH = re.compile(
    r"^(ACCOUNT STATEMENT|SUMMARY DETAILS|PRIVATE AND CONFIDENTIAL|Date\s+Reference|Opening Balance:)",
    re.IGNORECASE,
)
RX_SUMMARYISH = re.compile(
    r"^(Account No:|Account Type:|For the Period of:|Account Name:|Address:|Currency:|Total Credit:|Total Debit:|Cleared Balance:|Uncleared Balance:|Available Balance:)",
    re.IGNORECASE,
)
RX_FOOTERISH = re.compile(
    r"^(Group Head|Operations|Signature|Page\s+\d+|For enquiries)",
    re.IGNORECASE,
)
RX_REFERENCE_LINE = re.compile(
    r"^(?:NIP/\d+|FTN\d+|\d{6,}\*+|\*+\d+|\d{2,3}/\d{6,}|\d{10,}|S\d{5,}|\d{1,3})$",
    re.IGNORECASE,
)
RX_BODY_REF_TOKEN = re.compile(
    r"^(?:NIP/\d+|FTN\d+|\d{6,}\*+|\d{8,}|\*+\d+)$",
    re.IGNORECASE,
)

GLOBAL_HEADERS_FCMB = [
    "TXN_DATE",
    "REFERENCE",
    "REMARKS",
    "VAL_DATE",
    "CREDIT",
    "DEBIT",
    "BALANCE",
]


def _looks_like_blank_row(row: List[str]) -> bool:
    return not any((cell or "").strip() for cell in row)


def _looks_like_opening_balance_row(row: List[str]) -> bool:
    first = (row[0] or "").strip() if row else ""
    return first.lower().startswith("opening balance:")


def _standardize_table_row(
    row: List[str], headers: List[str]
) -> Optional[Dict[str, str]]:
    if not row or _looks_like_blank_row(row) or _looks_like_opening_balance_row(row):
        return None
    standardized = parse_text_row(row, headers)
    if not standardized.get("TXN_DATE") and not standardized.get("VAL_DATE"):
        return None
    return standardized


def _extract_table_rows(
    page, global_headers: Optional[List[str]]
) -> Tuple[List[Dict[str, str]], Optional[List[str]]]:
    rows: List[Dict[str, str]] = []
    tables = page.extract_tables(MAIN_TABLE_SETTINGS) or []

    for table in tables:
        if not table:
            continue

        first_row = table[0]
        normalized_first_row = [
            normalize_column_name(h) if h else "" for h in first_row
        ]
        is_header_row = any(
            h
            in {
                "TXN_DATE",
                "REFERENCE",
                "REMARKS",
                "VAL_DATE",
                "DEBIT",
                "CREDIT",
                "BALANCE",
            }
            for h in normalized_first_row
            if h
        )

        if is_header_row and not global_headers:
            global_headers = normalized_first_row
            data_rows = table[1:]
        elif is_header_row and global_headers:
            data_rows = table[1:] if normalized_first_row == global_headers else table
        else:
            data_rows = table

        if not global_headers:
            continue

        for row in data_rows:
            standardized = _standardize_table_row(row, global_headers)
            if standardized:
                rows.append(standardized)

    return rows, global_headers


def _clean_text_lines(text: str) -> List[str]:
    lines: List[str] = []
    for raw in (text or "").splitlines():
        line = raw.replace("\x00", "").strip()
        if not line or line == ".":
            continue
        if (
            RX_PAGE_STAMP.match(line)
            or RX_HEADERISH.match(line)
            or RX_SUMMARYISH.match(line)
            or RX_FOOTERISH.match(line)
        ):
            continue
        lines.append(line)
    return lines


def _split_reference_and_remarks(prefix_lines: List[str], body: str) -> Tuple[str, str]:
    ref_parts = [p.strip() for p in prefix_lines if p and p.strip()]
    body = (body or "").strip()
    tokens = body.split()

    if ref_parts:
        first_ref = ref_parts[0]
        if (
            first_ref.startswith("NIP/")
            and tokens
            and RX_BODY_REF_TOKEN.match(tokens[0])
        ):
            ref_parts.append(tokens[0])
            body = " ".join(tokens[1:]).strip()
        elif (
            first_ref.startswith("FTN")
            and tokens
            and RX_BODY_REF_TOKEN.match(tokens[0])
            and "/" in tokens[0]
        ):
            ref_parts.append(tokens[0])
            body = " ".join(tokens[1:]).strip()
        elif "*" in first_ref and tokens and tokens[0].startswith("**"):
            ref_parts.append(tokens[0])
            body = " ".join(tokens[1:]).strip()
    else:
        if (
            tokens
            and RX_BODY_REF_TOKEN.match(tokens[0])
            and not tokens[0].startswith(("QR/", "Q", "Rsvl:"))
        ):
            ref_parts.append(tokens[0])
            body = " ".join(tokens[1:]).strip()

    return "\n".join(ref_parts).strip(), body


def _parse_text_txn_line(
    prefix_lines: List[str], line: str
) -> Optional[Dict[str, str]]:
    m = RX_TXN_LINE.match(line)
    if not m:
        return None
    reference, remarks = _split_reference_and_remarks(prefix_lines, m.group("body"))
    return {
        "TXN_DATE": normalize_date(m.group("txn_date")),
        "VAL_DATE": normalize_date(m.group("val_date")),
        "REFERENCE": reference,
        "REMARKS": remarks,
        "DEBIT": "",
        "CREDIT": "",
        "BALANCE": normalize_money(m.group("balance")),
        "Check": "",
        "Check 2": "",
        "_AMOUNT": normalize_money(m.group("amount")),
    }


def _txn_key(txn: Dict[str, str]) -> Tuple[str, str, str]:
    return (
        txn.get("TXN_DATE", ""),
        txn.get("VAL_DATE", ""),
        normalize_money(txn.get("BALANCE", "")),
    )


def _extract_text_rows(
    page, carry_ref_lines: Optional[List[str]]
) -> Tuple[List[Dict[str, str]], List[str]]:
    lines = _clean_text_lines(page.extract_text() or "")
    rows: List[Dict[str, str]] = []
    prefix_lines: List[str] = list(carry_ref_lines or [])

    for line in lines:
        parsed = _parse_text_txn_line(prefix_lines, line)
        if parsed:
            rows.append(parsed)
            prefix_lines = []
            continue
        if RX_REFERENCE_LINE.match(line):
            prefix_lines.append(line)
            continue
        prefix_lines = []

    return rows, prefix_lines


def _merge_page_rows(
    table_rows: List[Dict[str, str]], text_rows: List[Dict[str, str]]
) -> List[Dict[str, str]]:
    if not text_rows:
        return table_rows

    table_buckets: Dict[Tuple[str, str, str], List[Dict[str, str]]] = {}
    for row in table_rows:
        table_buckets.setdefault(_txn_key(row), []).append(row)

    merged: List[Dict[str, str]] = []
    used_ids = set()

    for text_row in text_rows:
        bucket = table_buckets.get(_txn_key(text_row)) or []
        if bucket:
            row = bucket.pop(0)
            merged.append(row)
            used_ids.add(id(row))
        else:
            merged.append(text_row)

    for row in table_rows:
        if id(row) not in used_ids:
            merged.append(row)

    return merged


def _fill_missing_amount_sides(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    for idx, row in enumerate(rows):
        if "_AMOUNT" not in row:
            row["DEBIT"] = normalize_money(row.get("DEBIT", "0.00"))
            row["CREDIT"] = normalize_money(row.get("CREDIT", "0.00"))
            row["BALANCE"] = (
                normalize_money(row.get("BALANCE", "0.00"))
                if row.get("BALANCE")
                else ""
            )
            continue

        amount = to_float(row.get("_AMOUNT", "0.00"))
        current_balance = to_float(row.get("BALANCE", "0.00"))
        prev_balance = (
            to_float(rows[idx - 1].get("BALANCE", "0.00"))
            if idx > 0 and rows[idx - 1].get("BALANCE")
            else None
        )
        next_balance = (
            to_float(rows[idx + 1].get("BALANCE", "0.00"))
            if idx + 1 < len(rows) and rows[idx + 1].get("BALANCE")
            else None
        )

        debit = 0.0
        credit = 0.0
        if prev_balance is not None:
            if current_balance < prev_balance:
                debit = amount
            elif current_balance > prev_balance:
                credit = amount
            elif next_balance is not None:
                if next_balance < current_balance:
                    credit = amount
                elif next_balance > current_balance:
                    debit = amount
        elif next_balance is not None:
            if next_balance < current_balance:
                credit = amount
            elif next_balance > current_balance:
                debit = amount

        row["DEBIT"] = f"{debit:.2f}"
        row["CREDIT"] = f"{credit:.2f}"
        row["BALANCE"] = f"{current_balance:.2f}"
        row.pop("_AMOUNT", None)

    return rows


def parse(path: str) -> List[Dict[str, str]]:
    transactions: List[Dict[str, str]] = []
    global_headers: Optional[List[str]] = None
    carry_ref_lines: List[str] = []

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                print(f"(fcmb-fixed): Processing page {page_num}", file=sys.stderr)
                table_rows, global_headers = _extract_table_rows(page, global_headers)
                if not global_headers:
                    global_headers = GLOBAL_HEADERS_FCMB
                text_rows, carry_ref_lines = _extract_text_rows(page, carry_ref_lines)
                transactions.extend(_merge_page_rows(table_rows, text_rows))

        transactions = [
            t for t in transactions if t.get("TXN_DATE") or t.get("VAL_DATE")
        ]
        transactions = _fill_missing_amount_sides(transactions)
        return calculate_checks(transactions)
    except Exception as exc:
        print(f"Error processing FCMB statement: {exc}", file=sys.stderr)
        return []
