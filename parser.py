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
        "trans. date",
    ],
    "VAL_DATE": [
        "val date",
        "value date",
        "effective date",
        "value. date",
        "date",
        "valuedate",
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
    ],
    "DEBIT": ["debit", "withdrawal", "dr", "withdrawal(dr)", "debits", "money out"],
    "CREDIT": [
        "credit",
        "deposit",
        "cr",
        "deposit(cr)",
        "credits",
        "money in",
        "credit(₦)",
    ],
    "BALANCE": ["balance", "bal", "account balance", " debit(₦)"],
    "AMOUNT": ["amount", "txn amount", "transaction amount", " balance(₦)"],
}


def to_float(value: str) -> float:
    if not value or value.strip() == "":
        return 0.0
    try:
        # Remove commas, currency symbols, and extra whitespace
        cleaned = re.sub(r"[^\d.-]", "", value.strip())
        return float(cleaned)
    except ValueError:
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
    ]:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.strftime("%d-%B-%Y")
        except ValueError:
            continue
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

    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    if not table or len(table) < 2:
                        continue

                    headers = [normalize_column_name(h) if h else "" for h in table[0]]
                    has_amount = "AMOUNT" in headers
                    balance_idx = (
                        headers.index("BALANCE") if "BALANCE" in headers else -1
                    )
                    prev_balance = None

                    for row in table[1:]:
                        if len(row) < len(headers):
                            row.extend([""] * (len(headers) - len(row)))

                        row_dict = {
                            headers[i]: row[i] if i < len(row) else ""
                            for i in range(len(headers))
                        }

                        standardized_row = {
                            "TXN_DATE": normalize_date(
                                row_dict.get("TXN_DATE", row_dict.get("VAL_DATE", ""))
                            ),
                            "VAL_DATE": normalize_date(
                                row_dict.get("VAL_DATE", row_dict.get("TXN_DATE", ""))
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
                                    standardized_row["CREDIT"] = f"{abs(amount):.2f}"
                            else:
                                standardized_row["DEBIT"] = "0.00"
                                standardized_row["CREDIT"] = "0.00"
                            prev_balance = current_balance
                        else:
                            standardized_row["DEBIT"] = row_dict.get("DEBIT", "0.00")
                            standardized_row["CREDIT"] = row_dict.get("CREDIT", "0.00")
                            prev_balance = (
                                to_float(standardized_row["BALANCE"])
                                if standardized_row["BALANCE"]
                                else prev_balance
                            )

                        transactions.append(standardized_row)

        return calculate_checks(transactions)

    except Exception as e:
        print(f"Error processing PDF: {e}", file=sys.stderr)
        return []


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
