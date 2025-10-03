# /banks/lotus/universal.py
import sys
import re
import pdfplumber
from typing import List, Dict
from utils import (
    normalize_column_name,
    FIELD_MAPPINGS,
    to_float,
    normalize_money,
    calculate_checks,
    normalize_date,
    MAIN_TABLE_SETTINGS,
)


# Helper: normalize a cell to a clean string
def _s(x) -> str:
    if x is None:
        return ""
    return str(x).strip()


# --- top-level helpers unchanged ---


def parse(path: str) -> List[Dict[str, str]]:
    transactions: List[Dict[str, str]] = []

    # NEW: carry state across ALL tables/pages
    running_prev_balance_val = None  # float or None
    last_txn = None  # last real txn for continuation join

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                print(f"(lotus): Processing page {page_num}", file=sys.stderr)

                table_settings = MAIN_TABLE_SETTINGS
                tables = page.extract_tables(table_settings)
                if not tables:
                    print("(lotus): No tables found ...", file=sys.stderr)
                    continue

                for table in tables:
                    if not table or len(table) < 1:
                        continue

                    first_row = [_s(c) for c in table[0]]
                    normalized_first_row = [
                        normalize_column_name(h) if h else "" for h in first_row
                    ]
                    is_header_row = any(
                        h in FIELD_MAPPINGS for h in normalized_first_row if h
                    )
                    if not is_header_row and len(first_row) <= 2:
                        continue

                    if is_header_row:
                        if not "global_headers" in locals() or global_headers is None:
                            global_headers = normalized_first_row
                            print(
                                f"Stored global headers: {global_headers}",
                                file=sys.stderr,
                            )
                            data_rows = table[1:]
                        else:
                            data_rows = (
                                table[1:]
                                if normalized_first_row == global_headers
                                else table
                            )
                    else:
                        data_rows = table

                    if not global_headers:
                        print(
                            "(lotus): No headers found..., skipping table",
                            file=sys.stderr,
                        )
                        continue

                    has_amount = "AMOUNT" in global_headers
                    balance_idx = (
                        global_headers.index("BALANCE")
                        if "BALANCE" in global_headers
                        else -1
                    )

                    # IMPORTANT: Do NOT reset prev balance per-table anymore
                    # prev_balance_val = None  <-- removed

                    for raw_row in data_rows:
                        row = [_s(c) for c in raw_row]
                        if len(row) < len(global_headers):
                            row.extend([""] * (len(global_headers) - len(row)))

                        row_dict = {
                            global_headers[i]: row[i]
                            for i in range(len(global_headers))
                        }

                        # Early drop: pure-empty junk rows
                        if all(
                            _s(row_dict.get(k, "")) == ""
                            for k in (
                                "TXN_DATE",
                                "VAL_DATE",
                                "REMARKS",
                                "DEBIT",
                                "CREDIT",
                                "BALANCE",
                            )
                        ):
                            continue

                        txn_date = normalize_date(
                            row_dict.get("TXN_DATE", "") or row_dict.get("VAL_DATE", "")
                        )
                        val_date = normalize_date(
                            row_dict.get("VAL_DATE", "") or row_dict.get("TXN_DATE", "")
                        )
                        remarks = row_dict.get("REMARKS", "").strip()
                        reference = row_dict.get("REFERENCE", "").strip()
                        debit_raw = row_dict.get("DEBIT", "")
                        credit_raw = row_dict.get("CREDIT", "")
                        bal_raw = row_dict.get("BALANCE", "")
                        amount_raw = row_dict.get("AMOUNT", "") if has_amount else ""

                        debit_val = to_float(debit_raw) if debit_raw else 0.0
                        credit_val = to_float(credit_raw) if credit_raw else 0.0
                        bal_val = to_float(bal_raw) if bal_raw else None
                        amount_val = to_float(amount_raw) if amount_raw else 0.0

                        # Continuation line logic (unchanged)
                        no_money_cells = (
                            debit_raw == ""
                            and credit_raw == ""
                            and (not has_amount or amount_raw == "")
                            and (bal_raw == "")
                        )
                        is_continuation = no_money_cells and (remarks or reference)
                        if is_continuation and last_txn is not None:
                            glue = "\n" if last_txn["REMARKS"] else ""
                            last_txn["REMARKS"] = (
                                f"{last_txn['REMARKS']}{glue}{remarks if remarks else reference}"
                            )
                            if reference and reference not in last_txn["REMARKS"]:
                                last_txn["REMARKS"] += f"\n{reference}"
                            continue

                        txn = {
                            "TXN_DATE": txn_date,
                            "VAL_DATE": val_date,
                            "REFERENCE": reference,
                            "REMARKS": remarks,
                            "DEBIT": "0.00",
                            "CREDIT": "0.00",
                            "BALANCE": "",
                            "Check": "",
                            "Check 2": "",
                        }

                        # Separate columns preferred; AMOUNT heuristics if needed (unchanged)
                        if (
                            has_amount
                            and balance_idx != -1
                            and amount_raw
                            and debit_raw == ""
                            and credit_raw == ""
                        ):
                            narr = txn["REMARKS"].lower()
                            if any(
                                k in narr
                                for k in (
                                    " charge",
                                    "charges",
                                    "sms charge",
                                    "fee",
                                    "vat",
                                    "pos",
                                    "transfer to",
                                )
                            ):
                                debit_val = abs(amount_val)
                                credit_val = 0.0
                            elif any(
                                k in narr
                                for k in (
                                    "transfer in",
                                    "nip trf from",
                                    "credit",
                                    "reversal",
                                    "refund",
                                    "deposit",
                                )
                            ):
                                credit_val = abs(amount_val)
                                debit_val = 0.0

                        txn["DEBIT"] = f"{debit_val:.2f}"
                        txn["CREDIT"] = f"{credit_val:.2f}"

                        # Impute using file-level running_prev_balance_val
                        if bal_val is None and running_prev_balance_val is not None:
                            if debit_val > 0 and credit_val == 0:
                                bal_val = round(running_prev_balance_val - debit_val, 2)
                            elif credit_val > 0 and debit_val == 0:
                                bal_val = round(
                                    running_prev_balance_val + credit_val, 2
                                )

                        if bal_val is not None:
                            txn["BALANCE"] = f"{bal_val:.2f}"
                            running_prev_balance_val = bal_val
                        else:
                            if bal_raw:  # keep tracking if text balance exists
                                running_prev_balance_val = to_float(bal_raw)
                                txn["BALANCE"] = f"{running_prev_balance_val:.2f}"
                            # else: leave BALANCE empty; running_prev_balance_val unchanged

                        transactions.append(txn)
                        last_txn = txn

        print(
            f"(lotus): Total transactions parsed (pre-checks): {len(transactions)}",
            file=sys.stderr,
        )

        # FINAL BACKFILL: second pass to fix any remaining missing BALANCEs
        backfilled: List[Dict[str, str]] = []
        last_bal = None
        for t in transactions:
            d = to_float(t["DEBIT"])
            c = to_float(t["CREDIT"])
            btxt = t["BALANCE"]
            bval = None if btxt == "" else to_float(btxt)

            if bval is None and last_bal is not None:
                if d > 0 and c == 0:
                    bval = round(last_bal - d, 2)
                elif c > 0 and d == 0:
                    bval = round(last_bal + c, 2)

            if bval is not None:
                t["BALANCE"] = f"{bval:.2f}"
                last_bal = bval
            else:
                # if still unknown, do not update last_bal
                pass
            backfilled.append(t)

        # Clean & checks (unchanged idea)
        cleaned = []
        for t in backfilled:
            has_date = bool(t["TXN_DATE"] or t["VAL_DATE"])
            has_money = to_float(t["DEBIT"]) > 0 or to_float(t["CREDIT"]) > 0
            has_balance = t["BALANCE"] != ""
            if has_date or has_money or has_balance:
                cleaned.append(t)

        return calculate_checks(cleaned)

    except Exception as e:
        print(f"Error processing Lotus statement: {e}", file=sys.stderr)
        return []
