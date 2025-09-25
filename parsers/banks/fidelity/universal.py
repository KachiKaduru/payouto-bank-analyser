# banks/fidelity/universal.py
import re
import sys
from typing import List, Dict, Optional

import pdfplumber

from utils import (
    normalize_column_name,
    to_float,
    normalize_date,
    calculate_checks,
    STANDARDIZED_ROW,
)

# Regex helpers
DATE_CELL_RE = re.compile(
    r"\d{1,2}-[A-Za-z]{3}-\d{2,4}"
)  # matches "3-Feb-25", "03-Feb-2025", etc.
DATE_LINE_START_RE = re.compile(r"^\s*\d{1,2}-[A-Za-z]{3}-\d{2,4}\b")
NUM_RE = re.compile(r"[()\-]?\s*\d{1,3}(?:[,.\d]{0,})\d*(?:\.\d+)?\s*[)]?$")
MULTI_SPACE_SPLIT = re.compile(r"\s{2,}")

EXPECTED_KEYS = {
    "TXN_DATE",
    "VAL_DATE",
    "REFERENCE",
    "REMARKS",
    "DEBIT",
    "CREDIT",
    "BALANCE",
    "AMOUNT",
}


def _looks_like_date(s: Optional[str]) -> bool:
    if not s:
        return False
    return bool(DATE_CELL_RE.search(s))


def _right_numeric_cells(row_cells: List[str]) -> List[str]:
    """
    Scan row cells from the right and return a list of numeric-like strings (right-to-left order reversed to left-to-right).
    """
    found = []
    for cell in reversed(row_cells):
        if not cell:
            continue
        if NUM_RE.search(cell):
            # clean lightly (keep parentheses if present; to_float will remove currency chars)
            found.append(cell.strip())
        # Stop early if we've got 3 numeric tokens (debit, credit, balance)
        if len(found) >= 3:
            break
    return list(reversed(found))


def _standardize_row_map(row_map: Dict[str, str]) -> Dict[str, str]:
    out = STANDARDIZED_ROW.copy()
    # Only call normalize_date if value looks like a date -> avoids warnings
    txn = row_map.get("TXN_DATE", "") or ""
    val = row_map.get("VAL_DATE", "") or ""
    out["TXN_DATE"] = (
        normalize_date(txn)
        if _looks_like_date(txn)
        else (normalize_date(val) if _looks_like_date(val) else "")
    )
    out["VAL_DATE"] = (
        normalize_date(val)
        if _looks_like_date(val)
        else (normalize_date(txn) if _looks_like_date(txn) else "")
    )
    out["REFERENCE"] = (row_map.get("REFERENCE") or "").strip()
    out["REMARKS"] = " ".join((row_map.get("REMARKS") or "").split())
    out["DEBIT"] = row_map.get("DEBIT") or "0.00"
    out["CREDIT"] = row_map.get("CREDIT") or "0.00"
    out["BALANCE"] = row_map.get("BALANCE") or "0.00"
    out["Check"] = ""
    out["Check 2"] = ""
    return out


def parse(path: str) -> List[Dict[str, str]]:
    transactions: List[Dict[str, str]] = []
    prev_balance: Optional[float] = None

    try:
        with pdfplumber.open(path) as pdf:
            for pno, page in enumerate(pdf.pages, start=1):
                print(f"(fidelity-universal): processing page {pno}", file=sys.stderr)

                # Table extraction settings (tuned for fidelity-like statements)
                table_settings = {
                    "vertical_strategy": "text",
                    "horizontal_strategy": "lines",
                    "snap_tolerance": 3,
                    "join_tolerance": 3,
                    "min_words_vertical": 1,
                    "min_words_horizontal": 1,
                    "text_tolerance": 2,
                }

                tables = page.extract_tables(table_settings) or []

                used_table = None
                # choose the largest table (most rows) if multiple
                if tables:
                    tables = sorted(
                        tables, key=lambda t: len(t) if t else 0, reverse=True
                    )
                    for t in tables:
                        if not t or len(t) < 2:
                            continue
                        # heuristics: must have at least one numeric-looking cell somewhere (balance)
                        if any(
                            NUM_RE.search(str(cell or "")) for row in t for cell in row
                        ):
                            used_table = t
                            break
                    if used_table is None:
                        used_table = tables[0]

                if used_table:
                    header_row_idx = None
                    # try to detect header in first 3 rows
                    for ridx in range(min(3, len(used_table))):
                        row = used_table[ridx]
                        mapped_count = 0
                        for cell in row:
                            try:
                                mapped = normalize_column_name(cell or "")
                                if mapped and mapped in EXPECTED_KEYS:
                                    mapped_count += 1
                            except Exception:
                                continue
                        if mapped_count >= 3:
                            header_row_idx = ridx
                            break

                    if header_row_idx is None:
                        # fallback: assume first row is header
                        header_row_idx = 0

                    header_row = used_table[header_row_idx]
                    # build index map using normalize_column_name
                    idx_map: Dict[str, int] = {}
                    for idx, raw in enumerate(header_row):
                        try:
                            norm = normalize_column_name(raw or "")
                        except Exception:
                            norm = ""
                        if norm and norm in EXPECTED_KEYS:
                            idx_map[norm] = idx
                        else:
                            # extra heuristics on the header text if not normalized
                            rc = (raw or "").lower()
                            if "value" in rc and "val" not in idx_map:
                                idx_map.setdefault("VAL_DATE", idx)
                            if "transaction" in rc or (
                                "transaction" in rc or "txn" in rc
                            ):
                                idx_map.setdefault("TXN_DATE", idx)
                            if (
                                "detail" in rc
                                or "narrat" in rc
                                or "remark" in rc
                                or "description" in rc
                            ):
                                idx_map.setdefault("REMARKS", idx)
                            if "pay in" in rc or "credit" in rc:
                                idx_map.setdefault("CREDIT", idx)
                            if "pay out" in rc or "debit" in rc:
                                idx_map.setdefault("DEBIT", idx)
                            if "bal" in rc:
                                idx_map.setdefault("BALANCE", idx)

                    # ensure BALANCE index exists (fallback to last column)
                    if "BALANCE" not in idx_map:
                        idx_map["BALANCE"] = len(header_row) - 1

                    # process data rows after header_row_idx
                    data_rows = used_table[header_row_idx + 1 :]
                    i = 0
                    while i < len(data_rows):
                        raw_row = data_rows[i]
                        # normalize length
                        if len(raw_row) < len(header_row):
                            raw_row = [c if c is not None else "" for c in raw_row] + [
                                ""
                            ] * (len(header_row) - len(raw_row))

                        # Merge continuation rows where the next row does NOT start with a date
                        remarks_parts = []
                        if "REMARKS" in idx_map:
                            remarks_parts.append(
                                (raw_row[idx_map["REMARKS"]] or "").strip()
                            )
                        else:
                            # fallback: join middle cells
                            remarks_parts.append(
                                " ".join(
                                    [str(c or "").strip() for c in raw_row[:-3] if c]
                                )
                            )

                        # attempt to find true date cell among mapped date columns, else search whole row
                        txn_candidate = (
                            raw_row[idx_map["TXN_DATE"]]
                            if "TXN_DATE" in idx_map
                            else ""
                        )
                        val_candidate = (
                            raw_row[idx_map["VAL_DATE"]]
                            if "VAL_DATE" in idx_map
                            else ""
                        )
                        true_date_cell = ""
                        if _looks_like_date(txn_candidate):
                            true_date_cell = txn_candidate
                        elif _looks_like_date(val_candidate):
                            true_date_cell = val_candidate
                        else:
                            # search entire row for any date-like cell
                            for cell in raw_row:
                                if _looks_like_date(str(cell or "")):
                                    true_date_cell = str(cell or "")
                                    break

                        # Merge continuation lines into remarks
                        j = i
                        while j + 1 < len(data_rows):
                            nxt = data_rows[j + 1]
                            nxt_first = (nxt[0] or "").strip() if len(nxt) > 0 else ""
                            # if next row starts with a date-like cell, it's not a continuation
                            if _looks_like_date(nxt_first):
                                break
                            # otherwise treat it as continuation: append its remarks or whole row content
                            cont_piece = ""
                            if "REMARKS" in idx_map and idx_map["REMARKS"] < len(nxt):
                                cont_piece = (nxt[idx_map["REMARKS"]] or "").strip()
                            else:
                                cont_piece = " ".join(
                                    [str(c or "").strip() for c in nxt if c]
                                )
                            if cont_piece:
                                remarks_parts.append(cont_piece)
                            j += 1

                        # Advance i to skip merged rows
                        i = j + 1

                        # Build the row_map
                        row_map: Dict[str, str] = {}
                        # set dates (but do not normalize here unless they look like dates)
                        if true_date_cell:
                            # Assign found date cell to TXN_DATE (prefer existing mapping if both mapped)
                            row_map["TXN_DATE"] = true_date_cell
                        else:
                            # Use mapped columns if available (but only if they look like dates)
                            td = (
                                raw_row[idx_map["TXN_DATE"]]
                                if "TXN_DATE" in idx_map
                                and idx_map["TXN_DATE"] < len(raw_row)
                                else ""
                            )
                            if _looks_like_date(td):
                                row_map["TXN_DATE"] = td
                            else:
                                row_map["TXN_DATE"] = ""

                        if "VAL_DATE" in idx_map and idx_map["VAL_DATE"] < len(raw_row):
                            row_map["VAL_DATE"] = raw_row[idx_map["VAL_DATE"]] or ""
                        else:
                            row_map["VAL_DATE"] = ""

                        # Reference
                        if "REFERENCE" in idx_map and idx_map["REFERENCE"] < len(
                            raw_row
                        ):
                            row_map["REFERENCE"] = raw_row[idx_map["REFERENCE"]] or ""
                        else:
                            row_map["REFERENCE"] = ""

                        # Remarks consolidated
                        row_map["REMARKS"] = " ".join(
                            [p for p in remarks_parts if p]
                        ).strip()

                        # Balance (must exist)
                        bal_idx = idx_map.get("BALANCE", len(raw_row) - 1)
                        row_map["BALANCE"] = (
                            raw_row[bal_idx] if bal_idx < len(raw_row) else ""
                        )

                        # Debit / Credit if present in mapped indices
                        if "DEBIT" in idx_map and idx_map["DEBIT"] < len(raw_row):
                            row_map["DEBIT"] = raw_row[idx_map["DEBIT"]] or ""
                        else:
                            row_map["DEBIT"] = ""

                        if "CREDIT" in idx_map and idx_map["CREDIT"] < len(raw_row):
                            row_map["CREDIT"] = raw_row[idx_map["CREDIT"]] or ""
                        else:
                            row_map["CREDIT"] = ""

                        # If debit/credit missing, try to extract numeric tokens from the right
                        if (not row_map["DEBIT"] or not row_map["CREDIT"]) and any(
                            raw_row
                        ):
                            right_nums = _right_numeric_cells(raw_row)
                            # right_nums are left-to-right order among found numeric tokens on right side
                            # heuristics: last token -> balance, second-last -> credit, third-last -> debit
                            if right_nums:
                                if not row_map["BALANCE"] or NUM_RE.search(
                                    str(row_map["BALANCE"] or "")
                                ):
                                    # replace balance if numeric token fits
                                    row_map["BALANCE"] = right_nums[-1]
                                if len(right_nums) >= 2:
                                    if not row_map["CREDIT"]:
                                        row_map["CREDIT"] = right_nums[-2]
                                if len(right_nums) >= 3:
                                    if not row_map["DEBIT"]:
                                        row_map["DEBIT"] = right_nums[-3]

                        # Standardize and format numeric fields
                        std = _standardize_row_map(row_map)
                        try:
                            std["DEBIT"] = f"{to_float(std['DEBIT']):.2f}"
                        except Exception:
                            std["DEBIT"] = "0.00"
                        try:
                            std["CREDIT"] = f"{to_float(std['CREDIT']):.2f}"
                        except Exception:
                            std["CREDIT"] = "0.00"
                        try:
                            std["BALANCE"] = f"{to_float(std['BALANCE']):.2f}"
                        except Exception:
                            std["BALANCE"] = "0.00"

                        # Infer debit/credit from balance change if both zero
                        curr_bal_val = to_float(std["BALANCE"])
                        dval = to_float(std["DEBIT"])
                        cval = to_float(std["CREDIT"])
                        if prev_balance is not None and dval == 0 and cval == 0:
                            if curr_bal_val < prev_balance:
                                inferred = round(abs(curr_bal_val - prev_balance), 2)
                                std["DEBIT"] = f"{inferred:.2f}"
                                std["CREDIT"] = "0.00"
                            else:
                                inferred = round(abs(curr_bal_val - prev_balance), 2)
                                std["CREDIT"] = f"{inferred:.2f}"
                                std["DEBIT"] = "0.00"

                        prev_balance = to_float(std["BALANCE"])
                        transactions.append(std)
                else:
                    # No usable table -> text fallback (line-based)
                    text = page.extract_text() or ""
                    if not text:
                        continue
                    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
                    current_map: Optional[Dict[str, str]] = None
                    for line in lines:
                        if DATE_LINE_START_RE.match(line):
                            # push previous
                            if current_map:
                                std = _standardize_row_map(current_map)
                                std["DEBIT"] = f"{to_float(std['DEBIT']):.2f}"
                                std["CREDIT"] = f"{to_float(std['CREDIT']):.2f}"
                                std["BALANCE"] = f"{to_float(std['BALANCE']):.2f}"
                                # infer if needed
                                if (
                                    prev_balance is not None
                                    and to_float(std["DEBIT"]) == 0
                                    and to_float(std["CREDIT"]) == 0
                                ):
                                    currb = to_float(std["BALANCE"])
                                    if currb < prev_balance:
                                        inf = round(abs(currb - prev_balance), 2)
                                        std["DEBIT"] = f"{inf:.2f}"
                                    else:
                                        inf = round(abs(currb - prev_balance), 2)
                                        std["CREDIT"] = f"{inf:.2f}"
                                prev_balance = to_float(std["BALANCE"])
                                transactions.append(std)

                            # new row start
                            parts = MULTI_SPACE_SPLIT.split(line)
                            # extract right numeric tokens
                            rnums = _extract_right_numeric_from_parts(parts := parts)
                            # default mapping strategy (best-effort)
                            txn_guess = parts[0] if parts else ""
                            val_guess = (
                                parts[1]
                                if len(parts) > 1 and _looks_like_date(parts[1])
                                else ""
                            )
                            # remarks: everything between dates and numeric region
                            # find index where numeric region starts
                            num_start_idx = None
                            for idx in range(len(parts) - 1, -1, -1):
                                if NUM_RE.search(parts[idx]):
                                    num_start_idx = idx
                                else:
                                    if num_start_idx is not None:
                                        break
                            if num_start_idx is None:
                                remarks = " ".join(parts[1:])
                            else:
                                remarks = " ".join(parts[1:num_start_idx])

                            current_map = {
                                "TXN_DATE": txn_guess,
                                "VAL_DATE": val_guess,
                                "REFERENCE": "",
                                "REMARKS": remarks.strip(),
                                "DEBIT": rnums[-3] if len(rnums) >= 3 else "",
                                "CREDIT": rnums[-2] if len(rnums) >= 2 else "",
                                "BALANCE": rnums[-1] if len(rnums) >= 1 else "",
                            }
                        else:
                            # continuation line
                            if current_map:
                                current_map["REMARKS"] = (
                                    current_map.get("REMARKS", "") + " " + line
                                ).strip()

                    # push last in text fallback
                    if current_map:
                        std = _standardize_row_map(current_map)
                        std["DEBIT"] = f"{to_float(std['DEBIT']):.2f}"
                        std["CREDIT"] = f"{to_float(std['CREDIT']):.2f}"
                        std["BALANCE"] = f"{to_float(std['BALANCE']):.2f}"
                        if (
                            prev_balance is not None
                            and to_float(std["DEBIT"]) == 0
                            and to_float(std["CREDIT"]) == 0
                        ):
                            currb = to_float(std["BALANCE"])
                            if currb < prev_balance:
                                inf = round(abs(currb - prev_balance), 2)
                                std["DEBIT"] = f"{inf:.2f}"
                            else:
                                inf = round(abs(currb - prev_balance), 2)
                                std["CREDIT"] = f"{inf:.2f}"
                        transactions.append(std)
        # filter and run checks
        cleaned = []
        for t in transactions:
            if (t.get("TXN_DATE") or t.get("VAL_DATE")) or (
                to_float(t.get("DEBIT", "0")) or to_float(t.get("CREDIT", "0"))
            ):
                # ensure format
                t["DEBIT"] = f"{to_float(t.get('DEBIT', '0')):.2f}"
                t["CREDIT"] = f"{to_float(t.get('CREDIT', '0')):.2f}"
                t["BALANCE"] = f"{to_float(t.get('BALANCE', '0')):.2f}"
                cleaned.append(t)

        return calculate_checks(cleaned)
    except Exception as e:
        print(f"fidelity-universal error: {e}", file=sys.stderr)
        return []


# helper used by text fallback for extracting right numeric tokens from parts
def _extract_right_numeric_from_parts(parts: List[str]) -> List[str]:
    found = []
    for token in reversed(parts):
        if NUM_RE.search(token):
            # clean token (remove currency signs, stray letters)
            t = re.sub(r"[^\d\.\,\-\(\)]", "", token)
            if t:
                found.append(t)
        if len(found) >= 3:
            break
    return list(reversed(found))
