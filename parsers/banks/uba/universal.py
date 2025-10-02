import sys
import re
import pdfplumber
from typing import List, Dict

from utils import (
    normalize_column_name,
    FIELD_MAPPINGS,
    normalize_date,
    to_float,
    normalize_money,
    parse_text_row,
    calculate_checks,
)


def clean_transaction(row: Dict[str, str]) -> Dict[str, str]:
    """
    Fix misaligned UBA rows where narration fragments spill into DEBIT, CREDIT, or REFERENCE.
    Rules:
    - Keep only valid monetary values (must contain decimals).
    - If DEBIT or CREDIT contains a plain integer and the other side has a valid decimal,
      treat the integer as junk and move it to REMARKS.
    - Ensure empty DEBIT/CREDIT are formatted as "0.00".
    """
    remarks_extra = []

    # --- Clean REFERENCE ---
    ref = row.get("REFERENCE", "")
    if ref and not re.match(r"^\d+$", ref.strip()):  # not purely numeric
        remarks_extra.append(ref)
        row["REFERENCE"] = ""

    # Helper to check if a string looks like a money value with decimals
    def is_decimal_number(value: str) -> bool:
        return bool(re.match(r"^\d[\d,]*\.\d{2}$", value.strip()))

    # --- Clean DEBIT ---
    debit = row.get("DEBIT", "").strip()
    credit = row.get("CREDIT", "").strip()

    if debit:
        if is_decimal_number(debit):
            row["DEBIT"] = debit
        else:
            # if it's a plain integer and credit has a valid decimal → junk
            if re.match(r"^\d+$", debit) and is_decimal_number(credit):
                remarks_extra.append(debit)
                row["DEBIT"] = "0.00"
            else:
                # fallback: try to extract last valid decimal
                numbers = re.findall(r"\d[\d,]*\.?\d*", debit)
                if numbers and is_decimal_number(numbers[-1]):
                    row["DEBIT"] = numbers[-1]
                    junk = debit.replace(numbers[-1], "").strip()
                    if junk:
                        remarks_extra.append(junk)
                else:
                    remarks_extra.append(debit)
                    row["DEBIT"] = "0.00"
    else:
        row["DEBIT"] = "0.00"

    # --- Clean CREDIT ---
    if credit:
        if is_decimal_number(credit):
            row["CREDIT"] = credit
        else:
            # if it's a plain integer and debit has a valid decimal → junk
            if re.match(r"^\d+$", credit) and is_decimal_number(debit):
                remarks_extra.append(credit)
                row["CREDIT"] = "0.00"
            else:
                numbers = re.findall(r"\d[\d,]*\.?\d*", credit)
                if numbers and is_decimal_number(numbers[-1]):
                    row["CREDIT"] = numbers[-1]
                    junk = credit.replace(numbers[-1], "").strip()
                    if junk:
                        remarks_extra.append(junk)
                else:
                    remarks_extra.append(credit)
                    row["CREDIT"] = "0.00"
    else:
        row["CREDIT"] = "0.00"

    # Merge any extras back into remarks
    if remarks_extra:
        row["REMARKS"] = (
            row.get("REMARKS", "") + " " + " ".join(remarks_extra)
        ).strip()

    return row


def parse(path: str) -> List[Dict[str, str]]:
    transactions = []
    global_headers = None
    global_header_map = None

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                print(f"(uba): Processing page {page_num}", file=sys.stderr)
                # Table extraction settings
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
                                f"(uba): No headers found by page {page_num}, skipping table",
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
                                "BALANCE": normalize_money(row_dict.get("BALANCE", "")),
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

                            # 🔑 Clean misaligned rows
                            standardized_row = clean_transaction(standardized_row)

                            transactions.append(standardized_row)
                else:
                    print(
                        f"(uba): No tables found on page {page_num}, attempting text extraction",
                        file=sys.stderr,
                    )
                    text = page.extract_text()
                    if text and global_headers:
                        lines = text.split("\n")
                        current_row = []
                        for line in lines:
                            if re.match(r"^\d{2}[-/.]\d{2}[-/.]\d{4}", line):
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

        return calculate_checks(
            [t for t in transactions if t["TXN_DATE"] or t["VAL_DATE"]]
        )

    except Exception as e:
        print(f"Error processing UBA statement: {e}", file=sys.stderr)
        return []
