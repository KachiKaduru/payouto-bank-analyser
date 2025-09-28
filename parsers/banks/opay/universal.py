import pdfplumber
import sys
import json
from typing import List, Dict
from utils import *


def parse(path: str) -> List[Dict[str, str]]:
    transactions = []
    global_headers = None

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                print(f"(opay parser_001): Processing page {page_num}", file=sys.stderr)
                tables = page.extract_tables(MAIN_TABLE_SETTINGS)

                if tables:
                    for table in tables:
                        if (
                            not table or len(table) < 2
                        ):  # Need at least header + one row
                            continue

                        # OPay headers are consistent: ['Trans. Time', 'Value Date', 'Description', 'Debit/Credit(₦)', 'Balance(₦)', 'Channel', 'Transaction Reference', 'Counterparty']
                        first_row = [
                            normalize_column_name(h) if h else "" for h in table[0]
                        ]
                        if (
                            "TXN_DATE" in first_row or "VAL_DATE" in first_row
                        ):  # Detect header row
                            global_headers = first_row
                            data_rows = table[1:]
                        else:
                            data_rows = table  # Continuation without headers

                        if not global_headers:
                            continue

                        for row in data_rows:
                            if len(row) < len(global_headers):
                                row.extend([""] * (len(global_headers) - len(row)))

                            row_dict = {
                                global_headers[i]: row[i] if i < len(row) else ""
                                for i in range(len(global_headers))
                            }

                            # Standardize for OPay: Split combined Debit/Credit
                            amount_str = (
                                row_dict.get("DEBIT/CREDIT(₦)", "")
                                .replace("₦", "")
                                .strip()
                            )
                            debit = "0.00"
                            credit = "0.00"
                            if amount_str.startswith("+"):
                                credit = amount_str[1:].replace(",", "")
                            elif amount_str.startswith("-"):
                                debit = amount_str[1:].replace(",", "")
                            else:
                                # Fallback: Assume positive is credit
                                try:
                                    amt = to_float(amount_str)
                                    credit = f"{abs(amt):.2f}" if amt >= 0 else "0.00"
                                    debit = f"{abs(amt):.2f}" if amt < 0 else "0.00"
                                except:
                                    pass

                            standardized_row = {
                                "TXN_DATE": normalize_date(
                                    row_dict.get("TRANS. TIME", "")
                                ),
                                "VAL_DATE": normalize_date(
                                    row_dict.get("VALUE DATE", "")
                                ),
                                "REFERENCE": row_dict.get("TRANSACTION REFERENCE", ""),
                                "REMARKS": row_dict.get("DESCRIPTION", "")
                                + " | "
                                + row_dict.get("COUNTERPARTY", ""),
                                "DEBIT": debit,
                                "CREDIT": credit,
                                "BALANCE": row_dict.get("BALANCE(₦)", "")
                                .replace("₦", "")
                                .replace(",", ""),
                                "Check": "",
                                "Check 2": "",
                            }

                            transactions.append(standardized_row)

        return calculate_checks(
            [t for t in transactions if t["TXN_DATE"] or t["VAL_DATE"]]
        )

    except Exception as e:
        print(f"Error in OPay parser_001: {e}", file=sys.stderr)
        return []
