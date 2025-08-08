import re
import sys
import json
from typing import List, Dict, Optional, Union
from datetime import datetime
import pdfplumber
from PyPDF2 import PdfReader

TOLERANCE = 0.01  # Tolerance for balance checks
MAX_LINES_FOR_TRANSACTION = 5  # Maximum lines to consider for a single transaction

# Common patterns for bank statements
DATE_PATTERNS = [
    r"\d{2}-[A-Za-z]{3}-\d{2,4}",  # 01-Jan-2023
    r"\d{2}/\d{2}/\d{2,4}",  # 01/01/2023
    r"\d{4}-\d{2}-\d{2}",  # 2023-01-01
    r"\d{2}\.\d{2}\.\d{4}",  # 01.01.2023
]

AMOUNT_PATTERNS = [
    r"[+-]?[\d,]+\.\d{2}",  # Standard currency format
    r"[+-]?\d+\.\d{2}",  # Currency without commas
]

REFERENCE_PATTERNS = [
    r"\b(S|NIP|POS|TRF|USSD|WEB|ATM|CHQ|FT|IB|BP|DD)[\w\d/]+\b",
    r"\b\d{8,16}\b",  # Long numeric references
    r"\b[A-Z]{2,}\d{5,}\b",  # Mixed alphanumeric references
]


def to_float(value: str) -> float:
    """Convert string to float, handling commas and empty strings."""
    if not value:
        return 0.0
    try:
        return float(value.replace(",", "").strip())
    except ValueError:
        return 0.0


def find_first_match(patterns: List[str], text: str) -> Optional[str]:
    """Find the first matching pattern in text."""
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return None


def extract_dates(text: str) -> Dict[str, Optional[str]]:
    """Extract transaction and value dates from text."""
    dates = {"txn_date": None, "val_date": None}

    # Find all date matches
    all_dates = []
    for pattern in DATE_PATTERNS:
        all_dates.extend(re.findall(pattern, text))

    if not all_dates:
        return dates

    # Use the first date as transaction date
    dates["txn_date"] = all_dates[0]

    # If multiple dates, use the second as value date
    if len(all_dates) > 1:
        dates["val_date"] = all_dates[1]
    else:
        dates["val_date"] = all_dates[0]

    return dates


def extract_amounts(text: str) -> Dict[str, Optional[str]]:
    """Extract debit, credit, and balance amounts from text."""
    amounts = {"debit": None, "credit": None, "balance": None}

    # Find all amount matches
    all_amounts = []
    for pattern in AMOUNT_PATTERNS:
        all_amounts.extend(re.findall(pattern, text))

    if not all_amounts:
        return amounts

    # The last amount is typically the balance
    amounts["balance"] = all_amounts[-1]

    # If multiple amounts, the one before balance is the transaction amount
    if len(all_amounts) > 1:
        transaction_amount = all_amounts[-2]

        # Determine if it's debit or credit
        if "-" in transaction_amount or "DR" in text.upper():
            amounts["debit"] = transaction_amount.replace("-", "").strip()
        else:
            amounts["credit"] = transaction_amount

    return amounts


def extract_reference(text: str) -> str:
    """Extract transaction reference from text."""
    reference = find_first_match(REFERENCE_PATTERNS, text)
    return reference if reference else ""


def extract_remarks(text: str, txn_date: str) -> str:
    """Extract transaction remarks, excluding dates and amounts."""
    # Remove dates
    for pattern in DATE_PATTERNS:
        text = re.sub(pattern, "", text)

    # Remove amounts
    for pattern in AMOUNT_PATTERNS:
        text = re.sub(pattern, "", text)

    # Remove common noise
    text = re.sub(r"[*#]", "", text)
    text = re.sub(r"\b(DR|CR|CHG)\b", "", text, flags=re.IGNORECASE)

    return text.strip()


def calculate_checks(transactions: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Calculate balance checks for transactions."""
    updated = []
    prev_balance = None

    for txn in transactions:
        debit = to_float(txn["DEBIT"])
        credit = to_float(txn["CREDIT"])
        current_balance = to_float(txn["BALANCE"])

        if prev_balance is not None:
            expected = round(prev_balance - debit + credit, 2)
            actual = round(current_balance, 2)
            difference = abs(expected - actual)
            check = difference < TOLERANCE
            txn["Check"] = str(check)
            txn["Check 2"] = f"{difference:.2f}" if not check else "0.00"
        else:
            txn["Check"] = ""
            txn["Check 2"] = ""

        updated.append(txn)
        prev_balance = current_balance

    return updated


def parse_transaction_block(block: str) -> Optional[Dict[str, str]]:
    """Parse a single transaction block."""
    dates = extract_dates(block)
    if not dates["txn_date"]:
        return None

    amounts = extract_amounts(block)
    if not amounts["balance"]:
        return None

    reference = extract_reference(block)
    remarks = extract_remarks(block, dates["txn_date"])

    return {
        "TXN DATE": dates["txn_date"],
        "VAL DATE": dates["val_date"] or dates["txn_date"],
        "REFERENCE": reference,
        "REMARKS": remarks,
        "DEBIT": amounts["debit"] or "",
        "CREDIT": amounts["credit"] or "",
        "BALANCE": amounts["balance"],
        "Check": "",
        "Check 2": "",
    }


def group_transaction_lines(lines: List[str]) -> List[str]:
    """Group lines that belong to the same transaction."""
    transactions = []
    current_txn = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check if this line starts a new transaction
        if any(re.search(pattern, line) for pattern in DATE_PATTERNS):
            if current_txn:
                transactions.append(" ".join(current_txn))
                current_txn = []

        current_txn.append(line)

        # Prevent transaction blocks from getting too large
        if len(current_txn) >= MAX_LINES_FOR_TRANSACTION:
            transactions.append(" ".join(current_txn))
            current_txn = []

    if current_txn:
        transactions.append(" ".join(current_txn))

    return transactions


def parse_universal(text: str) -> List[Dict[str, str]]:
    """Parse text from bank statement into structured transactions."""
    lines = text.splitlines()
    transaction_blocks = group_transaction_lines(lines)
    transactions = []

    for block in transaction_blocks:
        txn = parse_transaction_block(block)
        if txn:
            transactions.append(txn)

    return calculate_checks(transactions)


def extract_text_with_pdfplumber(pdf_path: str) -> str:
    """Extract text using pdfplumber (more accurate for some PDFs)."""
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() + "\n"
    return text


def extract_text_with_pypdf2(pdf_path: str) -> str:
    """Extract text using PyPDF2."""
    reader = PdfReader(pdf_path)
    text = "\n".join(
        [page.extract_text() for page in reader.pages if page.extract_text()]
    )
    return text


def parse_pdf(pdf_path: str) -> List[Dict[str, str]]:
    """Parse PDF using the best available method."""
    try:
        # Try pdfplumber first as it's generally more accurate
        text = extract_text_with_pdfplumber(pdf_path)
        if len(text.strip()) > 100:  # Ensure we got reasonable text
            return parse_universal(text)
    except Exception as e:
        print(f"Note: pdfplumber failed, falling back to PyPDF2: {e}")

    # Fall back to PyPDF2 if pdfplumber fails
    text = extract_text_with_pypdf2(pdf_path)
    return parse_universal(text)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python parser.py path/to/statement.pdf")
        sys.exit(1)

    try:
        file_path = sys.argv[1]
        result = parse_pdf(file_path)
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"Error processing file: {e}")
        sys.exit(1)
