from typing import List, Dict, Optional
import pdfplumber
from utils import (
    MAIN_TABLE_SETTINGS,
    calculate_checks,
    normalize_money,
    normalize_whitespace,
    normalize_date,
)

UBA_HEADER_ROW_1 = [
    "TRANS\nDATE",
    "VALUE\nDATE",
    "NARRATION",
    "CHQ.\nNO",
    "DEBIT",
    "CREDIT",
    "BALANCE",
]


def is_header_row(row: List[Optional[str]]) -> bool:
    """
    Detect the 2nd row of the UBA header.
    """
    cleaned = [(x or "").strip() for x in row]
    return cleaned == UBA_HEADER_ROW_1


def parse(path: str) -> List[Dict[str, str]]:
    transactions: List[Dict[str, str]] = []
    header_found = False

    with pdfplumber.open(path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):

            # Skip page 1 (UBA metadata page)
            if page_num == 1:
                print(f"(uba_002_parser): Skipping metadata page {page_num}")
                continue

            print(f"(uba_002_parser): Processing page {page_num}")

            tables = page.extract_tables(MAIN_TABLE_SETTINGS)
            if not tables:
                print("(uba_002_parser): No tables on this page.")
                continue

            for table in tables:
                for row in table:

                    # Clean row values
                    row = [(x or "").strip() for x in row]

                    # Detect header row
                    if is_header_row(row):
                        print(f"(uba_002_parser): Header detected on page {page_num}")
                        header_found = True
                        continue

                    # If no header yet, skip
                    if not header_found:
                        print("(uba_002_parser): Skipping row, no header yet.")
                        continue

                    # Must be a transaction row (7 columns)
                    if len(row) != 7:
                        continue

                    (
                        txn_date,
                        val_date,
                        narr,
                        chq,
                        debit_raw,
                        credit_raw,
                        balance_raw,
                    ) = row

                    # Skip empty rows
                    if not txn_date or not val_date:
                        continue

                    transactions.append(
                        {
                            "TXN_DATE": normalize_date(txn_date),
                            "VAL_DATE": normalize_date(val_date),
                            "REMARKS": normalize_whitespace(narr),
                            "REFERENCE": normalize_whitespace(chq) or "",
                            "DEBIT": normalize_money(debit_raw) or "0.00",
                            "CREDIT": normalize_money(credit_raw) or "0.00",
                            "BALANCE": normalize_money(balance_raw) or "0.00",
                        }
                    )
    return calculate_checks([t for t in transactions if t["TXN_DATE"] or t["VAL_DATE"]])
