import pdfplumber
import re
import sys
import json
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOLERANCE = 0.01

# Enhanced field name mappings for normalization
FIELD_MAPPINGS = {
    "TXN_DATE": [
        "txn date",
        "trans date",
        "transaction date",
        "date",
        "post date",
        "posted date",
        "trans. date",
    ],
    "VAL_DATE": [
        "val date",
        "value date",
        "effective date",
        "value. date",
        "valuedate",
        "date",
    ],
    "REFERENCE": [
        "reference",
        "ref",
        "transaction id",
        "txn id",
        "ref. number",
        "reference number",
    ],
    "REMARKS": [
        "remarks",
        "description",
        "narration",
        "comment",
        "transaction details",
        "details",
    ],
    "DEBIT": [
        "debit",
        "withdrawal",
        "dr",
        "withdrawal(DR)",
        "debits",
        "money out",
        "debit (NGN)",
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
    ],
    "BALANCE": ["balance", "bal", "account balance", " balance(₦)", "balance (NGN)"],
    "AMOUNT": ["amount", "txn amount", "transaction amount", "balance(₦)"],
}

# Additional patterns for better detection
CURRENCY_PATTERNS = [
    r"₦[\d,]+\.?\d*",  # Nigerian Naira
    r"\$[\d,]+\.?\d*",  # US Dollar
    r"£[\d,]+\.?\d*",  # British Pound
    r"€[\d,]+\.?\d*",  # Euro
    r"[\d,]+\.?\d*",  # Generic number
]

DATE_PATTERNS = [
    r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}",
    r"\d{1,2}[-/][A-Za-z]{3}[-/]\d{2,4}",
    r"\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4}",
    r"[A-Za-z]{3}\s+\d{1,2},?\s+\d{2,4}",
    r"\d{2,4}[-/]\d{1,2}[-/]\d{1,2}",
]


def to_float(value: str) -> float:
    """Enhanced number parsing with better error handling"""
    if not value or value.strip() == "" or value.strip() == "-":
        return 0.0

    try:
        # Handle various formats
        value = str(value).strip()

        # Remove currency symbols and spaces
        cleaned = re.sub(r"[₦$£€,\s]", "", value)

        # Handle parentheses as negative
        if cleaned.startswith("(") and cleaned.endswith(")"):
            cleaned = "-" + cleaned[1:-1]

        # Handle CR/DR suffixes
        if cleaned.upper().endswith("CR"):
            cleaned = cleaned[:-2].strip()
        elif cleaned.upper().endswith("DR") or cleaned.upper().endswith("DB"):
            cleaned = "-" + cleaned[:-2].strip()

        # Remove any remaining non-numeric characters except decimal point and minus
        cleaned = re.sub(r"[^\d.-]", "", cleaned)

        if not cleaned or cleaned == "-":
            return 0.0

        return float(cleaned)

    except (ValueError, AttributeError) as e:
        logger.warning(f"Could not parse number '{value}': {e}")
        return 0.0


def normalize_date(date_str: str) -> str:
    """Enhanced date parsing with more formats"""
    if not date_str or date_str.strip() == "":
        return ""

    # Clean the date string
    date_str = re.sub(r"[^\w\s/-]", "", str(date_str)).strip()

    date_formats = [
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
        "%b %d, %Y",
        "%B %d, %Y",
        "%d/%b/%Y",
        "%d/%B/%Y",
        "%Y/%m/%d",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%m-%d-%Y",
        "%m-%d-%y",
        "%d %b, %Y",
        "%d-%b",
        "%d/%m",
        "%m/%d",  # Formats without year
    ]

    for fmt in date_formats:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            # If no year specified, assume current year
            if dt.year == 1900:
                dt = dt.replace(year=datetime.now().year)
            return dt.strftime("%d-%b-%Y")
        except ValueError:
            continue

    logger.warning(f"Could not parse date '{date_str}'")
    return date_str


def normalize_column_name(col: str) -> str:
    """Enhanced column name normalization"""
    if not col:
        return ""

    # Clean the column name
    col_clean = re.sub(r"[^\w\s()]", "", str(col)).strip().lower()

    # Remove common prefixes/suffixes
    col_clean = re.sub(r"^(column|col|field)\s*", "", col_clean)
    col_clean = re.sub(r"\s*(column|col|field)$", "", col_clean)

    for standard, aliases in FIELD_MAPPINGS.items():
        if col_clean in [alias.lower() for alias in aliases]:
            return standard

    return col_clean


def detect_table_structure(tables: List[List[List]], page_text: str = "") -> Dict:
    """Analyze table structure to identify the best parsing strategy"""
    structure_info = {
        "has_headers": False,
        "header_row_idx": -1,
        "column_count": 0,
        "data_rows": 0,
        "table_type": "unknown",
    }

    if not tables:
        return structure_info

    # Analyze first table
    table = tables[0]
    if not table:
        return structure_info

    structure_info["column_count"] = len(table[0]) if table[0] else 0
    structure_info["data_rows"] = len(table)

    # Look for header indicators
    for i, row in enumerate(table[:3]):  # Check first 3 rows
        if not row:
            continue

        row_text = " ".join([str(cell) if cell else "" for cell in row]).lower()

        # Count header-like words
        header_indicators = [
            "date",
            "description",
            "amount",
            "balance",
            "debit",
            "credit",
            "reference",
        ]
        header_count = sum(
            1 for indicator in header_indicators if indicator in row_text
        )

        if header_count >= 2:  # At least 2 header indicators
            structure_info["has_headers"] = True
            structure_info["header_row_idx"] = i
            break

    # Determine table type
    if "amount" in page_text.lower() and (
        "debit" not in page_text.lower() and "credit" not in page_text.lower()
    ):
        structure_info["table_type"] = "single_amount"
    elif "debit" in page_text.lower() and "credit" in page_text.lower():
        structure_info["table_type"] = "debit_credit"
    else:
        structure_info["table_type"] = "generic"

    return structure_info


def extract_text_fallback(page) -> List[Dict[str, str]]:
    """Fallback text extraction when table extraction fails"""
    transactions = []
    text = page.extract_text()

    if not text:
        return transactions

    lines = text.split("\n")
    current_transaction = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check if line starts with a date
        date_match = None
        for pattern in DATE_PATTERNS:
            match = re.search(pattern, line)
            if match:
                date_match = match.group()
                break

        if date_match:
            # Process previous transaction if exists
            if current_transaction:
                txn = parse_text_transaction(current_transaction)
                if txn:
                    transactions.append(txn)

            # Start new transaction
            current_transaction = [line]
        else:
            # Continue current transaction
            if current_transaction:
                current_transaction.append(line)

    # Process last transaction
    if current_transaction:
        txn = parse_text_transaction(current_transaction)
        if txn:
            transactions.append(txn)

    return transactions


def parse_text_transaction(lines: List[str]) -> Optional[Dict[str, str]]:
    """Parse a transaction from text lines"""
    if not lines:
        return None

    full_text = " ".join(lines)

    # Extract date
    date_str = ""
    for pattern in DATE_PATTERNS:
        match = re.search(pattern, full_text)
        if match:
            date_str = match.group()
            break

    # Extract amounts
    amounts = []
    for pattern in CURRENCY_PATTERNS:
        matches = re.findall(pattern, full_text)
        for match in matches:
            amount = to_float(match)
            if amount != 0:
                amounts.append(amount)

    # Extract description (remove date and amounts)
    description = full_text
    if date_str:
        description = description.replace(date_str, "")
    for pattern in CURRENCY_PATTERNS:
        description = re.sub(pattern, "", description)
    description = " ".join(description.split())  # Normalize whitespace

    # Determine debit/credit/balance
    debit = "0.00"
    credit = "0.00"
    balance = "0.00"
    if amounts:
        # Assume last amount is balance
        balance = f"{amounts[-1]:.2f}"
        # Previous amounts could be debit/credit
        if len(amounts) > 1:
            amount = amounts[-2]
            if amount < 0:
                debit = f"{abs(amount):.2f}"
            else:
                credit = f"{amount:.2f}"

    return {
        "TXN_DATE": normalize_date(date_str),
        "VAL_DATE": normalize_date(date_str),
        "REFERENCE": "",
        "REMARKS": description,
        "DEBIT": debit,
        "CREDIT": credit,
        "BALANCE": balance,
        "Check": "",
        "Check 2": "",
    }


def smart_amount_detection(
    row_dict: Dict[str, str], table_type: str, prev_balance: Optional[float] = None
) -> Tuple[str, str]:
    """Smart detection of debit/credit amounts based on context"""
    debit, credit = "0.00", "0.00"

    if table_type == "single_amount":
        amount = to_float(row_dict.get("AMOUNT", ""))
        current_balance = to_float(row_dict.get("BALANCE", ""))

        if prev_balance is not None and amount != 0:
            if current_balance < prev_balance:
                debit = f"{abs(amount):.2f}"
            else:
                credit = f"{abs(amount):.2f}"
        elif amount < 0:
            debit = f"{abs(amount):.2f}"
        elif amount > 0:
            credit = f"{amount:.2f}"

    elif table_type == "debit_credit":
        debit = f"{to_float(row_dict.get('DEBIT', '0')):.2f}"
        credit = f"{to_float(row_dict.get('CREDIT', '0')):.2f}"

    else:
        # Generic detection - look for any amount fields
        for key, value in row_dict.items():
            if key.upper() in ["AMOUNT", "DEBIT", "WITHDRAWAL", "DR"]:
                debit = f"{to_float(value):.2f}"
            elif key.upper() in ["CREDIT", "DEPOSIT", "CR"]:
                credit = f"{to_float(value):.2f}"

    return debit, credit


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


def parse_pdf(path: str) -> List[Dict[str, str]]:
    """Enhanced PDF parsing with multiple strategies"""
    transactions = []
    global_headers = None
    global_header_map = None

    try:
        with pdfplumber.open(path) as pdf:
            logger.info(f"Processing PDF with {len(pdf.pages)} pages")

            for page_num, page in enumerate(pdf.pages, 1):
                logger.info(f"Processing page {page_num}")

                # Multiple table extraction strategies
                table_settings_list = [
                    # Strategy 1: Lines-based detection
                    {
                        "vertical_strategy": "lines",
                        "horizontal_strategy": "lines",
                        "snap_tolerance": 3,
                        "join_tolerance": 3,
                        "min_words_vertical": 3,
                        "min_words_horizontal": 1,
                        "text_tolerance": 1,
                    },
                    # Strategy 2: Text-based detection
                    {
                        "vertical_strategy": "text",
                        "horizontal_strategy": "text",
                        "text_tolerance": 3,
                        "text_word_threshold": 0.1,
                    },
                    # Strategy 3: Explicit boundaries
                    {
                        "vertical_strategy": "explicit",
                        "horizontal_strategy": "explicit",
                        "explicit_vertical_lines": page.chars,
                        "explicit_horizontal_lines": [],
                    },
                ]

                tables = []
                page_text = page.extract_text() or ""

                # Try different table extraction strategies
                for settings in table_settings_list:
                    try:
                        extracted_tables = page.extract_tables(settings)
                        if extracted_tables and any(
                            len(table) > 1 for table in extracted_tables
                        ):
                            tables = extracted_tables
                            break
                    except Exception as e:
                        logger.debug(f"Table extraction strategy failed: {e}")
                        continue

                if tables:
                    # Analyze table structure
                    structure = detect_table_structure(tables, page_text)
                    logger.info(f"Page {page_num}: Table structure - {structure}")

                    for table in tables:
                        if not table or len(table) < 1:
                            continue

                        # Determine header row
                        header_row_idx = (
                            structure["header_row_idx"]
                            if structure["has_headers"]
                            else 0
                        )

                        if structure["has_headers"] and header_row_idx >= 0:
                            first_row = table[header_row_idx]
                            normalized_first_row = [
                                normalize_column_name(h) if h else "" for h in first_row
                            ]

                            # Store or verify headers
                            if not global_headers:
                                global_headers = normalized_first_row
                                global_header_map = {
                                    i: h
                                    for i, h in enumerate(global_headers)
                                    if h in FIELD_MAPPINGS
                                }
                                logger.info(
                                    f"Global headers established: {global_headers}"
                                )

                            data_rows = table[header_row_idx + 1 :]
                        else:
                            data_rows = table

                        if not global_headers:
                            logger.warning(
                                f"No headers found, attempting text fallback for page {page_num}"
                            )
                            text_transactions = extract_text_fallback(page)
                            transactions.extend(text_transactions)
                            continue

                        prev_balance = None

                        for row_idx, row in enumerate(data_rows):
                            if not row or all(
                                not cell or str(cell).strip() == "" for cell in row
                            ):
                                continue

                            # Pad row to match header length
                            if len(row) < len(global_headers):
                                row.extend([""] * (len(global_headers) - len(row)))

                            row_dict = {
                                global_headers[i]: (
                                    str(row[i]).strip()
                                    if i < len(row) and row[i]
                                    else ""
                                )
                                for i in range(len(global_headers))
                            }

                            # Skip empty rows
                            if not any(row_dict.values()):
                                continue

                            # Smart amount detection
                            debit, credit = smart_amount_detection(
                                row_dict, structure["table_type"], prev_balance
                            )

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
                                "DEBIT": debit,
                                "CREDIT": credit,
                                "BALANCE": f"{to_float(row_dict.get('BALANCE', '')):.2f}",
                                "Check": "",
                                "Check 2": "",
                            }

                            # Only add if we have essential data
                            if (
                                standardized_row["TXN_DATE"]
                                or standardized_row["VAL_DATE"]
                                or standardized_row["REMARKS"]
                            ):
                                transactions.append(standardized_row)
                                prev_balance = to_float(standardized_row["BALANCE"])

                else:
                    # Fallback to text extraction
                    logger.info(
                        f"No tables found on page {page_num}, using text fallback"
                    )
                    text_transactions = extract_text_fallback(page)
                    transactions.extend(text_transactions)

        # Filter and calculate checks
        valid_transactions = [
            t for t in transactions if t["TXN_DATE"] or t["VAL_DATE"] or t["REMARKS"]
        ]

        logger.info(f"Found {len(valid_transactions)} valid transactions")
        return calculate_checks(valid_transactions)

    except Exception as e:
        logger.error(f"Error processing PDF: {e}")
        return []


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python parser-grok-v1.py path/to/statement.pdf", file=sys.stderr)
        sys.exit(1)

    try:
        file_path = sys.argv[1]
        result = parse_pdf(file_path)

        if result:
            logger.info(f"Successfully parsed {len(result)} transactions")
            print(json.dumps(result, indent=2))
        else:
            logger.error("No transactions found")
            sys.exit(1)

    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)
