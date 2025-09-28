# banks/access/universal.py
import pdfplumber
import re
import sys
from typing import List, Dict
from utils import (
    FIELD_MAPPINGS,
    is_two_digit_year,
    ends_with_month_dash,
    normalize_date,
    join_date_fragments,
    clean_money,
    to_float,
    parse_text_row,
    normalize_column_name,
    calculate_checks,
)

# ---------- helpers ----------
RX_YEAR2 = re.compile(r"^\s*\d{2}\s*$")  # "25"
RX_YEAR4 = re.compile(r"^\s*\d{4}\s*$")  # "2025"
RX_ENDS_MON_DASH = re.compile(
    r"^\s*\d{2}-[A-Z]{3}-\s*$"
)  # "30-JAN-" (maybe trailing space)
RX_AMOUNT_LIKE = re.compile(r"^\s*[-\d,]+(?:\.\d{2})?\s*$")


def _looks_like_artifact(row: Dict[str, str]) -> bool:
    """Exactly the condition you described."""
    no_remarks = not (row.get("REMARKS") or "").strip()
    debit = (row.get("DEBIT") or "").strip()
    credit = (row.get("CREDIT") or "").strip()
    balance = (row.get("BALANCE") or "").strip()
    money_empty = debit in {"", "0.00"} and credit in {"", "0.00"} and balance == ""
    year_only_dates = is_two_digit_year(row.get("TXN_DATE")) and is_two_digit_year(
        row.get("VAL_DATE")
    )
    return no_remarks and money_empty and year_only_dates


def _postprocess_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Merge cross-page year fragments into the previous row's dates
    and drop the artifact row. Also normalize money & date formatting.
    """
    cleaned: List[Dict[str, str]] = []
    i = 0
    while i < len(rows):
        r = rows[i]

        # Artifact row (two-digit year, empty everything)
        if _looks_like_artifact(r) and cleaned:
            prev = cleaned[-1]

            prev_raw_txn = prev.get("RAW_TXN_DATE", prev.get("TXN_DATE", ""))
            prev_raw_val = prev.get("RAW_VAL_DATE", prev.get("VAL_DATE", ""))

            if ends_with_month_dash(prev_raw_txn) and ends_with_month_dash(
                prev_raw_val
            ):
                # Merge: append the two digits ("25") to the previous row's raw dates
                y = r.get("TXN_DATE", "").strip()  # "25"
                merged_txn_raw = f"{prev_raw_txn}{y}"
                merged_val_raw = f"{prev_raw_val}{y}"

                # Re-normalize and update prev row
                prev["RAW_TXN_DATE"] = merged_txn_raw
                prev["RAW_VAL_DATE"] = merged_val_raw
                prev["TXN_DATE"] = normalize_date(join_date_fragments(merged_txn_raw))
                prev["VAL_DATE"] = normalize_date(join_date_fragments(merged_val_raw))

                # Skip this artifact row entirely
                i += 1
                continue
            else:
                # Previous row does not end with "DD-MMM-"; drop this artifact anyway.
                i += 1
                continue

        # For normal rows: finalize money; fix inner-cell date breaks.
        r["DEBIT"] = clean_money(r.get("DEBIT", "0.00"))
        r["CREDIT"] = clean_money(r.get("CREDIT", "0.00"))
        r["BALANCE"] = (
            f"{to_float(r['BALANCE']):.2f}" if (r.get("BALANCE") or "").strip() else ""
        )

        # Re-join any inner cell splits like "03-FEB-\n25"
        if r.get("TXN_DATE"):
            r["TXN_DATE"] = normalize_date(join_date_fragments(r["TXN_DATE"]))
        if r.get("VAL_DATE"):
            r["VAL_DATE"] = normalize_date(join_date_fragments(r["VAL_DATE"]))

        cleaned.append(r)
        i += 1

    # Drop helper keys before returning
    for r in cleaned:
        r.pop("RAW_TXN_DATE", None)
        r.pop("RAW_VAL_DATE", None)

    return cleaned


# ---------- parser ----------
def parse(path: str) -> List[Dict[str, str]]:
    transactions: List[Dict[str, str]] = []
    global_headers = None

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                print(f"(access parser): Processing page {page_num}", file=sys.stderr)

                table_settings = {
                    "vertical_strategy": "lines",
                    "horizontal_strategy": "lines",
                    "explicit_vertical_lines": [],
                    "explicit_horizontal_lines": [],
                    "snap_tolerance": 3,
                    "join_tolerance": 3,
                    "min_words_vertical": 3,
                    "min_words_horizontal": 1,
                    "text_tolerance": 1,
                }
                tables = page.extract_tables(table_settings)

                if not tables:
                    # Fallback text mode
                    text = page.extract_text()
                    if text and global_headers:
                        lines = text.split("\n")
                        current_row = []
                        start_rx = re.compile(r"^\s*\d{2}-[A-Z]{3}-\d{2}(?:\d{2})?\b")
                        for line in lines:
                            if start_rx.match(line):
                                if current_row:
                                    transactions.append(
                                        parse_text_row(current_row, global_headers)
                                    )
                                current_row = [line]
                            else:
                                current_row.append(line)
                        if current_row:
                            transactions.append(
                                parse_text_row(current_row, global_headers)
                            )
                    continue

                for table in tables:
                    if not table or len(table) < 1:
                        continue

                    first_row = table[0]
                    normalized_first_row = [
                        normalize_column_name(h) if h else "" for h in first_row
                    ]
                    is_header_row = any(
                        h in FIELD_MAPPINGS for h in normalized_first_row if h
                    )

                    if is_header_row and not global_headers:
                        global_headers = normalized_first_row
                        data_rows = table[1:]
                    elif is_header_row and global_headers:
                        data_rows = (
                            table[1:]
                            if normalized_first_row == global_headers
                            else table
                        )
                    else:
                        data_rows = table

                    if not global_headers:
                        print("No headers yet; skipping table", file=sys.stderr)
                        continue

                    has_amount = "AMOUNT" in global_headers
                    prev_balance = None

                    for row in data_rows:
                        if len(row) < len(global_headers):
                            row.extend([""] * (len(global_headers) - len(row)))

                        row_dict = {
                            global_headers[i]: (row[i] if i < len(row) else "")
                            for i in range(len(global_headers))
                        }

                        # Keep RAW dates exactly as they appeared in the table (for merge step)
                        raw_txn_cell = (
                            row_dict.get("TXN_DATE") or row_dict.get("VAL_DATE") or ""
                        ).strip()
                        raw_val_cell = (
                            row_dict.get("VAL_DATE") or row_dict.get("TXN_DATE") or ""
                        ).strip()

                        # Also compute normalized dates for normal flow (may be empty if split across rows)
                        norm_txn = (
                            normalize_date(join_date_fragments(raw_txn_cell))
                            if raw_txn_cell
                            else ""
                        )
                        norm_val = (
                            normalize_date(join_date_fragments(raw_val_cell))
                            if raw_val_cell
                            else ""
                        )

                        std = {
                            "RAW_TXN_DATE": raw_txn_cell,  # keep for postprocess merge
                            "RAW_VAL_DATE": raw_val_cell,  # keep for postprocess merge
                            "TXN_DATE": norm_txn,
                            "VAL_DATE": norm_val,
                            "REFERENCE": (row_dict.get("REFERENCE") or "").strip(),
                            "REMARKS": (row_dict.get("REMARKS") or "").strip(),
                            "DEBIT": "",
                            "CREDIT": "",
                            "BALANCE": (row_dict.get("BALANCE") or "").strip(),
                            "Check": "",
                            "Check 2": "",
                        }

                        if has_amount:
                            amount = to_float(row_dict.get("AMOUNT", "0"))
                            current_balance = to_float(row_dict.get("BALANCE", "0"))
                            if prev_balance is not None:
                                if current_balance < prev_balance:
                                    std["DEBIT"] = f"{abs(amount):.2f}"
                                    std["CREDIT"] = "0.00"
                                else:
                                    std["DEBIT"] = "0.00"
                                    std["CREDIT"] = f"{abs(amount):.2f}"
                            else:
                                std["DEBIT"] = "0.00"
                                std["CREDIT"] = "0.00"
                            prev_balance = current_balance
                        else:
                            std["DEBIT"] = clean_money(row_dict.get("DEBIT", "0.00"))
                            std["CREDIT"] = clean_money(row_dict.get("CREDIT", "0.00"))
                            prev_balance = (
                                to_float(std["BALANCE"])
                                if std["BALANCE"]
                                else prev_balance
                            )

                        transactions.append(std)

        # Merge artifacts & normalize
        transactions = _postprocess_rows(transactions)

        # Validate / add check columns
        return calculate_checks(
            [t for t in transactions if t.get("TXN_DATE") or t.get("VAL_DATE")]
        )

    except Exception as e:
        print(f"Error processing the Access Bank statement: {e}", file=sys.stderr)
        return []
