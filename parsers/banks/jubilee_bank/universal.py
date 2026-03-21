import sys
import re
import pdfplumber
from typing import List, Dict

from utils import (
    normalize_column_name,
    FIELD_MAPPINGS,
    MAIN_TABLE_SETTINGS,
    parse_text_row,
    calculate_checks,
    normalize_date,  # <-- add
    clean_money,  # <-- optional but recommended
    RX_FOUR_DIGIT_YEAR,  # <-- use your regex
    RX_ENDS_MONTH_DASH,
    RX_MULTI_WS,
)


def stitch_split_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Fix cases where a transaction is split across pages:
    - previous row has "10-Jan-" and next row has "2026"
    - amounts/balance appear on the next row
    - narration continues on the next row
    """
    stitched: List[Dict[str, str]] = []
    i = 0

    def is_year_only(x: str) -> bool:
        return bool(x) and RX_FOUR_DIGIT_YEAR.match(x.strip())

    def is_month_dash(x: str) -> bool:
        return bool(x) and RX_ENDS_MONTH_DASH.match(x.strip().upper())

    def is_blank_or_zero_money(x: str) -> bool:
        # treat "", None, "0.00" as empty for stitching purposes
        return clean_money(x) == "0.00"

    while i < len(rows):
        cur = rows[i]
        nxt = rows[i + 1] if i + 1 < len(rows) else None

        cur_txn = (cur.get("TXN_DATE") or "").strip()
        cur_val = (cur.get("VAL_DATE") or "").strip()

        # Case A: date split like "10-Jan-" + "2026"
        if nxt:
            nxt_txn = (nxt.get("TXN_DATE") or "").strip()
            nxt_val = (nxt.get("VAL_DATE") or "").strip()

            if (
                is_month_dash(cur_txn)
                and is_year_only(nxt_txn)
                and is_year_only(nxt_val)
            ):
                # merge the date pieces
                merged_txn_raw = (
                    f"{cur_txn}{nxt_txn}"  # "10-Jan-" + "2026" -> "10-Jan-2026"
                )
                merged_val_raw = f"{cur_val}{nxt_val}"

                cur["TXN_DATE"] = normalize_date(merged_txn_raw) or merged_txn_raw
                cur["VAL_DATE"] = normalize_date(merged_val_raw) or merged_val_raw

                # merge remarks (carry over the continuation line)
                cur_rem = (cur.get("REMARKS") or "").rstrip()
                nxt_rem = (nxt.get("REMARKS") or "").lstrip()
                merged_rem = f"{cur_rem}\n{nxt_rem}".strip()
                cur["REMARKS"] = RX_MULTI_WS.sub(
                    " ", merged_rem
                )  # optional: collapse whitespace

                # if amounts/balance are missing on cur but present on nxt, pull them in
                if is_blank_or_zero_money(
                    cur.get("DEBIT", "")
                ) and not is_blank_or_zero_money(nxt.get("DEBIT", "")):
                    cur["DEBIT"] = nxt.get("DEBIT", cur.get("DEBIT", "0.00"))
                if is_blank_or_zero_money(
                    cur.get("CREDIT", "")
                ) and not is_blank_or_zero_money(nxt.get("CREDIT", "")):
                    cur["CREDIT"] = nxt.get("CREDIT", cur.get("CREDIT", "0.00"))
                if (
                    not (cur.get("BALANCE") or "").strip()
                    and (nxt.get("BALANCE") or "").strip()
                ):
                    cur["BALANCE"] = nxt["BALANCE"]

                stitched.append(cur)
                i += 2
                continue

        # Case B: continuation row with no valid date (or year-only) but has only narration
        # Attach it to the previous stitched row if it looks like a spillover line.
        if stitched:
            looks_like_bad_date = (
                is_year_only(cur_txn)
                or is_month_dash(cur_txn)
                or cur_txn == ""
                or cur_txn == "—"
            )
            has_no_money = is_blank_or_zero_money(
                cur.get("DEBIT", "")
            ) and is_blank_or_zero_money(cur.get("CREDIT", ""))
            has_no_balance = not (cur.get("BALANCE") or "").strip()

            if looks_like_bad_date and has_no_money and has_no_balance:
                prev = stitched[-1]
                prev["REMARKS"] = RX_MULTI_WS.sub(
                    " ",
                    (
                        prev.get("REMARKS", "").rstrip()
                        + " "
                        + (cur.get("REMARKS", "").strip())
                    ).strip(),
                )
                i += 1
                continue

        stitched.append(cur)
        i += 1

    return stitched


def parse(path: str) -> List[Dict[str, str]]:
    transactions = []
    global_headers = None

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                print(f"(jubilee_bank): Processing page {page_num}", file=sys.stderr)
                tables = page.extract_tables(MAIN_TABLE_SETTINGS)

                if tables:
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

                        if not is_header_row and len(first_row) <= 2:
                            continue

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
                            continue

                        for row in data_rows:
                            standardized_row = parse_text_row(row, global_headers)
                            transactions.append(standardized_row)

        # ✅ stitch split rows BEFORE filtering / reversing / checks
        transactions = stitch_split_rows(transactions)

        # keep rows that now have a real date (normalize_date typically returns YYYY-MM-DD)
        rows = [
            t
            for t in transactions
            if (t.get("TXN_DATE") or "").strip() and "-" in (t.get("TXN_DATE") or "")
        ]
        rows.reverse()
        return calculate_checks(rows)

    except Exception as e:
        print(f"Error processing jubilee_bank statement: {e}", file=sys.stderr)
        return []
