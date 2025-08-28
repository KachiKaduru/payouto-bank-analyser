import sys
import re
from typing import List, Dict
from datetime import datetime
from PyPDF2 import PdfReader, PdfWriter
import tempfile
import pikepdf

TOLERANCE = 0.01

## CONSTANTS
FIELD_MAPPINGS = {
    "TXN_DATE": [
        "txn date",
        "trans",
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
        "value",
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
        'chq\nno',
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
        "balance(₦)",
        "balance (NGN)",
        "BALANCE",
        "",
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

STANDARDIZED_ROW = {
    "TXN_DATE": "",
    "VAL_DATE": "",
    "REFERENCE": "",
    "REMARKS": "",
    "DEBIT": "0.00",
    "CREDIT": "0.00",
    "BALANCE": "0.00",
    "Check": "",
    "Check 2": "",
}


# FUNCTIONS
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

    # Clean up multiple spaces and fix dash+space issue
    cleaned = re.sub(r"\s+", " ", date_str.strip())        # collapse spaces
    cleaned = re.sub(r"-\s+", "-", cleaned)                # remove space after dash

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
            dt = datetime.strptime(cleaned, fmt)
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


def parse_text_row(row: List[str], headers: List[str]) -> Dict[str, str]:
    standardized_row = STANDARDIZED_ROW

    if len(row) < len(headers):
        row.extend([""] * (len(headers) - len(row)))

    row_dict = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}

    standardized_row["TXN_DATE"] = normalize_date(
        row_dict.get("TXN_DATE", row_dict.get("VAL_DATE", ""))
    )
    standardized_row["VAL_DATE"] = normalize_date(
        row_dict.get("VAL_DATE", row_dict.get("TXN_DATE", ""))
    )
    standardized_row["REFERENCE"] = row_dict.get("REFERENCE", "")
    standardized_row["REMARKS"] = row_dict.get("REMARKS", "")
    standardized_row["DEBIT"] = row_dict.get("DEBIT", "0.00")
    standardized_row["CREDIT"] = row_dict.get("CREDIT", "0.00")
    standardized_row["BALANCE"] = row_dict.get("BALANCE", "0.00")

    return standardized_row


def decrypt_pdf(input_path: str, password: str = '') -> str:
    """
    Decrypt a password-protected PDF.
    1. Try PyPDF2 first (fast, works for simple encryption).
    2. If PyPDF2 fails, fallback to pikepdf (handles stronger encryption).

    Returns the path to the decrypted PDF (temp file) if successful,
    or the original path if unencrypted. Returns None on failure.
    """
    # ---- Try PyPDF2 ----
    try:
        reader = PdfReader(input_path)
        if reader.is_encrypted:
            if not password:
                raise ValueError("Encrypted PDF detected. Please provide a password.")
            result = reader.decrypt(password)
            if result:  # Success (1 or True)
                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=".pdf"
                ) as temp_file:
                    writer = PdfWriter()
                    for page in reader.pages:
                        writer.add_page(page)
                    writer.write(temp_file)
                print("✅ Decrypted successfully with PyPDF2")
                return temp_file.name
            else:
                print("⚠️ PyPDF2 failed, trying pikepdf...")
        else:
            print("ℹ️ PDF is not encrypted")
            return input_path
    except Exception as e:
        print(f"⚠️ PyPDF2 error: {e} → trying pikepdf...")

    # ---- Fallback: pikepdf ----
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            with pikepdf.open(input_path, password=password) as pdf:
                pdf.save(temp_file.name)
        print("✅ Decrypted successfully with pikepdf")
        return temp_file.name
    except Exception as e:
        print(f"❌ Both PyPDF2 and pikepdf failed: {e}")
        return ''
