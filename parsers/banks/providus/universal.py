import sys
import re
import pdfplumber
from typing import List, Dict
from utils import (
    normalize_column_name,
    FIELD_MAPPINGS,
    normalize_date,
    to_float,
    parse_text_row,
    calculate_checks,
)


def detect_and_fix_debit_credit_swap(transactions, sample_size=50, tolerance=0.01):
    """
    Heuristic: for each consecutive row with a parseable BALANCE, compare:
      expected_delta = credit - debit
      actual_delta   = current_balance - prev_balance
    If expected_delta matches actual_delta -> orientation OK
    If -expected_delta matches actual_delta -> swapped
    Use majority vote over up to sample_size rows to decide.
    """
    vote_ok = 0
    vote_swap = 0
    checked = 0
    prev_balance = None

    for t in transactions:
        bal = to_float(t.get("BALANCE", ""))
        debit = to_float(t.get("DEBIT", ""))
        credit = to_float(t.get("CREDIT", ""))

        if prev_balance is None:
            prev_balance = bal
            continue

        if abs(debit) < 1e-9 and abs(credit) < 1e-9:
            prev_balance = bal
            continue

        expected_delta = round(credit - debit, 2)
        actual_delta = round(bal - prev_balance, 2)

        if abs(expected_delta - actual_delta) <= tolerance:
            vote_ok += 1
        elif abs((-expected_delta) - actual_delta) <= tolerance:
            vote_swap += 1

        checked += 1
        prev_balance = bal

        if checked >= sample_size:
            break

    print(
        f"(providus) swap-detect: checked={checked}, ok={vote_ok}, swap={vote_swap}",
        file=sys.stderr,
    )

    if checked > 0 and vote_swap > vote_ok and vote_swap >= max(2, checked // 3):
        print(
            "(providus) DETECTED DEBIT<->CREDIT SWAP — swapping all rows.",
            file=sys.stderr,
        )
        for t in transactions:
            t["DEBIT"], t["CREDIT"] = t.get("CREDIT", "0.00"), t.get("DEBIT", "0.00")
        return transactions, True

    print("(providus) No debit/credit swap detected.", file=sys.stderr)
    return transactions, False


def parse(path: str) -> List[Dict[str, str]]:
    transactions = []
    global_headers = None
    global_header_map = None

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                print(f"(providus): Processing page {page_num}", file=sys.stderr)
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

                        if is_header_row and not global_headers:
                            global_headers = normalized_first_row
                            global_header_map = {
                                i: h
                                for i, h in enumerate(global_headers)
                                if h in FIELD_MAPPINGS
                            }
                            print(
                                f"Stored global headers: {global_headers}",
                                file=sys.stderr,
                            )
                            data_rows = table[1:]
                        elif is_header_row and global_headers:
                            if normalized_first_row == global_headers:
                                print(
                                    f"Skipping repeated header row on page {page_num}",
                                    file=sys.stderr,
                                )
                                data_rows = table[1:]
                            else:
                                print(
                                    f"Different headers on page {page_num}, treating as data",
                                    file=sys.stderr,
                                )
                                data_rows = table
                        else:
                            data_rows = table

                        if not global_headers:
                            print(
                                f"(providus): No headers found by page {page_num}, skipping table",
                                file=sys.stderr,
                            )
                            continue

                        has_amount = "AMOUNT" in global_headers
                        balance_idx = (
                            global_headers.index("BALANCE")
                            if "BALANCE" in global_headers
                            else -1
                        )
                        prev_balance = None

                        for row in data_rows:
                            if len(row) < len(global_headers):
                                row.extend([""] * (len(global_headers) - len(row)))

                            row_dict = {
                                global_headers[i]: (
                                    row[i] if i < len(global_headers) else ""
                                )
                                for i in range(len(global_headers))
                            }

                            # Skip summary/total rows
                            if (
                                row_dict.get("TXN_DATE", "")
                                .strip()
                                .lower()
                                .startswith(("total", "closing", "opening", "subtotal"))
                            ):
                                continue

                            standardized_row = {
                                "TXN_DATE": normalize_date(
                                    row_dict.get(
                                        "TXN_DATE", row_dict.get("VAL_DATE", "")
                                    )
                                ),
                                "VAL_DATE": normalize_date(
                                    row_dict.get(
                                        "VAL_DATE", row_dict.get("TXN_DATE", "")
                                    )
                                ),
                                "REFERENCE": row_dict.get("REFERENCE", ""),
                                "REMARKS": row_dict.get("REMARKS", ""),
                                "DEBIT": "",
                                "CREDIT": "",
                                "BALANCE": row_dict.get("BALANCE", ""),
                                "Check": "",
                                "Check 2": "",
                            }

                            if has_amount and balance_idx != -1:
                                amount = to_float(row_dict.get("AMOUNT", ""))
                                current_balance = to_float(row_dict.get("BALANCE", ""))

                                if prev_balance is not None:
                                    if current_balance < prev_balance:
                                        standardized_row["DEBIT"] = f"{abs(amount):.2f}"
                                        standardized_row["CREDIT"] = "0.00"
                                    else:
                                        standardized_row["DEBIT"] = "0.00"
                                        standardized_row["CREDIT"] = (
                                            f"{abs(amount):.2f}"
                                        )
                                else:
                                    standardized_row["DEBIT"] = "0.00"
                                    standardized_row["CREDIT"] = "0.00"
                                prev_balance = current_balance
                            else:
                                standardized_row["DEBIT"] = row_dict.get(
                                    "DEBIT", "0.00"
                                )
                                standardized_row["CREDIT"] = row_dict.get(
                                    "CREDIT", "0.00"
                                )
                                prev_balance = (
                                    to_float(standardized_row["BALANCE"])
                                    if standardized_row["BALANCE"]
                                    else prev_balance
                                )

                            transactions.append(standardized_row)
                else:
                    print(
                        f"(providus): No tables found on page {page_num}, attempting text extraction",
                        file=sys.stderr,
                    )

        # 🔑 run swap detector before calculate_checks
        transactions, _ = detect_and_fix_debit_credit_swap(transactions)

        return calculate_checks(
            [t for t in transactions if t["TXN_DATE"] or t["VAL_DATE"]]
        )

    except Exception as e:
        print(f"Error processing Providus Bank statement: {e}", file=sys.stderr)
        return []
