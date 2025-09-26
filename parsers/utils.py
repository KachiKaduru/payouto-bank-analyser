import sys
import re
from typing import List, Dict
from datetime import datetime
from PyPDF2 import PdfReader, PdfWriter
import tempfile

TOLERANCE = 0.01

## CONSTANTS
FIELD_MAPPINGS = {
    "TXN_DATE": [
        "txn date",
        "trans",
        "trans date",
        "transdate",
        "transaction date",
        "date",
        "post date",
        "posted date",
        "trans. date",
        "posted\ndate",
        "trans\ndate",
        "transaction\ndate",
        "create date",
        "actual transaction date",  # ← new
        "actual\ntransaction\ndate",  # ← new
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
        "transaction reference",
        "txn id",
        "ref. number",
        "reference number",
        "reference\nnumber",
        "check no",
        "chq\nno",
        "chq no",
        "channel",
    ],
    "REMARKS": [
        "remarks",
        "description",
        "descrip�on",
        "descrip\x00on",
        "descrip\ufffdon",
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
        "withdrawals",
        "dr",
        "withdrawal(DR)",
        "debits",
        "money out",
        "debit(₦)",
        "debit(\u20a6)",
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
        "credit(\u20a6)",
        "credit (NGN)",
        "CREDIT",
        "credit amount",
        "pay in",
        # "lodgements",
    ],
    "BALANCE": [
        "balance",
        "bal",
        "account balance",
        "balance(₦)",
        "balance (NGN)",
        "BALANCE",
        "current balance",
        "current\nbalance",
        "",
    ],
    "AMOUNT": [
        "amount",
        "txn amount",
        "transaction amount",
        "balance(₦)",
        "balance(\u20a6)",
    ],
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
    value = value.strip() if value else ""
    if not value or value == "-" or value == "":
        return 0.0
    try:
        # Remove currency symbols, commas, and handle negative numbers
        cleaned = re.sub(r"[^\d.-]", "", value)
        return float(cleaned)
    except ValueError:
        print(f"Warning: Could not parse number '{value}'", file=sys.stderr)
        return 0.0


def normalize_date(date_str: str) -> str:
    if not date_str:
        return ""

    # Skip non-date rows like totals/closing balance
    if re.match(r"(?i)^(total|closing|opening|balance|subtotal)", date_str.strip()):
        return ""

    # Clean up spaces and dash issues
    cleaned = re.sub(r"\s+", " ", date_str.strip())  # collapse multiple spaces
    cleaned = re.sub(r"-\s+", "-", cleaned)  # remove space after dash
    cleaned = re.sub(r":\s+", ":", cleaned)  # remove space after colon in time

    # Handle cases like '2025-03-13\n2025-03-13'
    if "\n" in date_str or "\r" in date_str:
        parts = [p.strip() for p in re.split(r"[\r\n]+", date_str) if p.strip()]
        if len(set(parts)) == 1:  # same date duplicated
            cleaned = parts[0]
        elif parts:  # multiple different dates → prefer first (TXN over VAL)
            cleaned = parts[0]

    # Fix truncated 4-digit year like '024-12-09'
    if re.match(r"^\d{3}-\d{2}-\d{2}$", cleaned):
        cleaned = "2" + cleaned

    # Supported date formats (added US-style month/day/year)
    date_formats = [
        "%d-%b-%Y",
        "%d-%b-%y",
        "%d/%m/%Y",
        "%d/%m/%y",
        "%d-%m-%Y",
        "%d-%m-%y",
        "%m/%d/%Y",  # ✅ e.g. 1/30/2025
        "%m/%d/%y",  # ✅ e.g. 1/30/25
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%d %b %Y",
        "%d.%m.%Y",
        "%d.%m.%y",
        "%d %B %Y",
        "%d-%B-%Y",
    ]

    for fmt in date_formats:
        try:
            dt = datetime.strptime(cleaned, fmt)
            # Return in Excel-friendly ISO format
            return dt.strftime("%Y-%m-%d")  # ✅ Excel recognizes & sorts
        except ValueError:
            continue

    # If nothing matches, log and return original
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
    # standardized_row = STANDARDIZED_ROW
    standardized_row = STANDARDIZED_ROW.copy()

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

    standardized_row["DEBIT"] = row_dict.get("DEBIT", "0.00") or "0.00"
    standardized_row["CREDIT"] = row_dict.get("CREDIT", "0.00") or "0.00"
    standardized_row["BALANCE"] = row_dict.get("BALANCE", "0.00")

    return standardized_row


def decrypt_pdf(
    pdf_path: str,
    password: str = "",
    effective_path: str = None,
    temp_file_path: str = None,
) -> str:
    reader = PdfReader(pdf_path)
    if reader.is_encrypted:
        if not password:
            raise ValueError("Encrypted PDF detected. Please provide a password.")
        reader.decrypt(password)
        print("PDF decrypted successfully.")
        # Create a temporary file for the decrypted PDF
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            writer = PdfWriter()
            for page in reader.pages:
                writer.add_page(page)
            writer.write(temp_file)
            temp_file_path = temp_file.name
            effective_path = temp_file_path
        return temp_file_path, effective_path
