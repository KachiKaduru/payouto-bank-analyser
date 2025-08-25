import re
import sys
from typing import List, Dict
from datetime import datetime
from PyPDF2 import PdfReader

TOLERANCE = 0.01

# Field name mappings for normalization (unchanged)
FIELD_MAPPINGS = {
    "TXN_DATE": [
        "txn date",
        "trans date",
        "transaction date",
        "date",
        "post date",
        "posted date",
        "trans. date",
        "posted\ndate",
        "trans\ndate",
        "transaction\ndate",
        "create date",
    ],
    "VAL_DATE": [
        "val date",
        "value date",
        "effective date",
        "value. date",
        "valuedate",
        "date",
        "value\ndate",
        "VAL_DATE",
    ],
    "REFERENCE": [
        "reference",
        "ref",
        "transaction id",
        "txn id",
        "ref. number",
        "reference number",
        "reference\nnumber",
        "check no",
        "channel",
    ],
    "REMARKS": [
        "remarks",
        "description",
        "narration",
        "comment",
        "transaction details",
        "details",
        "descr",
        "REMARKS",
        "description/payee/memo",
    ],
    "DEBIT": [
        "debit",
        "withdrawal",
        "dr",
        "withdrawal(DR)",
        "debits",
        "money out",
        "debit (NGN)",
        "DEBIT",
        "debit amount",
        "pay out",
    ],
    "CREDIT": [
        "credit",
        "deposit",
        "cr",
        "deposit(CR)",
        "credits",
        "money in",
        "credit(₦)",
        "credit (NGN)",
        "CREDIT",
        "credit amount",
        "pay in",
    ],
    "BALANCE": [
        "balance",
        "bal",
        "account balance",
        " balance(₦)",
        "balance (NGN)",
        "BALANCE",
    ],
    "AMOUNT": ["amount", "txn amount", "transaction amount", "balance(₦)"],
}

MAIN_TABLE_SETTINGS = {
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


def to_float(value: str) -> float:
    if not value or value.strip() == "":
        return 0.0
    try:
        # Remove currency symbols, commas, and handle negative numbers
        cleaned = re.sub(r"[^\d.-]", "", value.strip())
        return float(cleaned)
    except ValueError:
        print(f"Warning: Could not parse number '{value}'", file=sys.stderr)
        return 0.0


def normalize_date(date_str: str) -> str:
    if not date_str:
        return ""
    for fmt in [
        "%d-%b-%Y",
        "%d-%b-%y",
        "%d/%m/%Y",
        "%d/%m/%y",
        "%d-%m-%Y",
        "%d-%m-%y",
        "%Y-%m-%d",
        "%d %b %Y",
        "%d.%m.%Y",
        "%d.%m.%y",
        "%d %B %Y",
        "%d-%B-%Y",
    ]:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.strftime("%d-%b-%Y")  # Abbreviated month
        except ValueError:
            continue
    print(f"Warning: Could not parse date '{date_str}'", file=sys.stderr)
    return date_str


def normalize_column_name(col: str) -> str:
    if not col:
        return ""
    col_lower = col.lower().strip()
    for standard, aliases in FIELD_MAPPINGS.items():
        if col_lower in [alias.lower() for alias in aliases]:
            return standard
    return col_lower


def calculate_checks(transactions: List[Dict[str, str]]) -> List[Dict[str, str]]:
    updated = []
    prev_balance = None

    for txn in transactions:
        debit = to_float(txn["DEBIT"])
        credit = to_float(txn["CREDIT"])
        current_balance = to_float(txn["BALANCE"])

        if prev_balance is not None:
            expected = round(prev_balance - debit + credit, 2)
            actual = round(current_balance, 2)
            check = abs(expected - actual) <= TOLERANCE
            txn["Check"] = "TRUE" if check else "FALSE"
            txn["Check 2"] = f"{abs(expected - actual):.2f}" if not check else "0.00"
        else:
            txn["Check"] = "TRUE"
            txn["Check 2"] = "0.00"

        updated.append(txn)
        prev_balance = current_balance

    return updated


def decrypt_pdf(pdf_path: str, password: str) -> PdfReader:
    """Decrypt a PDF and return the PdfReader object."""
    try:
        reader = PdfReader(pdf_path)
        if reader.is_encrypted:
            reader.decrypt(password)
            print("PDF decrypted successfully.")
        else:
            print("PDF is not encrypted.")
        return reader
    except Exception as e:
        print(f"Error decrypting PDF: {e}")
        raise
