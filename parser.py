import pdfplumber
import re
import sys
import json
from typing import List, Dict
from datetime import datetime

TOLERANCE = 0.01

# Field name mappings for normalization
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
            return dt.strftime("%d-%B-%Y")
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


def parse_pdf(path: str) -> List[Dict[str, str]]:
    transactions = []
    global_headers = None
    global_header_map = None

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                print(f"Processing page {page_num}", file=sys.stderr)
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
                            # Store headers from the first page with headers
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
                            # Process data rows (skip header row)
                            data_rows = table[1:]
                        elif is_header_row and global_headers:
                            # Check if first row matches global_headers
                            if normalized_first_row == global_headers:
                                print(
                                    f"Skipping repeated header row on page {page_num}",
                                    file=sys.stderr,
                                )
                                data_rows = table[1:]  # Skip header row
                            else:
                                # Treat as data if different headers
                                print(
                                    f"Different headers on page {page_num}, treating as data",
                                    file=sys.stderr,
                                )
                                data_rows = table
                        else:
                            # No header row, use global_headers
                            data_rows = table

                        if not global_headers:
                            print(
                                f"No headers found by page {page_num}, skipping table",
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
                                global_headers[i]: row[i] if i < len(row) else ""
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
                    # Fallback: Extract text if no tables found
                    print(
                        f"No tables found on page {page_num}, attempting text extraction",
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
        print(f"Error processing PDF: {e}", file=sys.stderr)
        return []


def parse_text_row(row: List[str], headers: List[str]) -> Dict[str, str]:
    standardized_row = {
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


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python parser.py path/to/statement.pdf", file=sys.stderr)
        sys.exit(1)

    try:
        file_path = sys.argv[1]
        result = parse_pdf(file_path)
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
