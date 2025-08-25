# zenith-parser-001.py
import pdfplumber, re, json, sys
from datetime import datetime

TOLERANCE = 0.01

HEADER_SIGNATURE = [
    "DATE POSTED",
    "VALUE DATE",
    "DESCRIPTION",
    "DEBIT",
    "CREDIT",
    "BALANCE",
]

FIELD_MAPPINGS = {
    "DATE POSTED": "TXN_DATE",
    "VALUE DATE": "VAL_DATE",
    "DESCRIPTION": "REMARKS",
    "REFERENCE": "REFERENCE",
    "DEBIT": "DEBIT",
    "CREDIT": "CREDIT",
    "BALANCE": "BALANCE",
}


def to_float(value):
    if not value or value.strip() == "":
        return 0.0
    try:
        cleaned = re.sub(r"[^\d.-]", "", value.strip())
        return float(cleaned)
    except:
        return 0.0


def normalize_date(date_str):
    if not date_str:
        return ""
    for fmt in ["%d-%b-%Y", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d %b %Y", "%d %B %Y"]:
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%d-%b-%Y")
        except:
            continue
    return date_str


def calculate_checks(transactions):
    prev_balance = None
    for txn in transactions:
        debit, credit, current_balance = (
            to_float(txn["DEBIT"]),
            to_float(txn["CREDIT"]),
            to_float(txn["BALANCE"]),
        )
        if prev_balance is not None:
            expected = round(prev_balance - debit + credit, 2)
            actual = round(current_balance, 2)
            if abs(expected - actual) <= TOLERANCE:
                txn["Check"], txn["Check 2"] = "TRUE", "0.00"
            else:
                txn["Check"], txn["Check 2"] = "FALSE", f"{abs(expected - actual):.2f}"
        else:
            txn["Check"], txn["Check 2"] = "TRUE", "0.00"
        prev_balance = current_balance
    return transactions


def parse_pdf(path):
    transactions, headers = [], None
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                if not table:
                    continue

                # Skip Zenith summary tables
                first_row_text = " ".join([str(x) for x in table[0] if x])
                if (
                    "Account Number" in first_row_text
                    or "Opening Balance" in first_row_text
                ):
                    continue

                # Detect headers safely
                if not headers:
                    cleaned_header = [col.strip() if col else "" for col in table[0]]
                    if all(
                        any(h in (col or "") for col in cleaned_header)
                        for h in HEADER_SIGNATURE
                    ):
                        headers = [
                            FIELD_MAPPINGS.get(col.strip(), col.strip()) if col else ""
                            for col in table[0]
                        ]
                        continue

                if not headers:
                    continue

                # Process rows
                for row in table:
                    if len(row) < len(headers):
                        row.extend([""] * (len(headers) - len(row)))
                    row_dict = {
                        headers[i]: row[i].strip() if row[i] else ""
                        for i in range(len(headers))
                    }

                    # Handle multiline remarks
                    if (
                        not row_dict["TXN_DATE"]
                        and not row_dict["VAL_DATE"]
                        and row_dict["REMARKS"]
                    ):
                        if transactions:
                            transactions[-1]["REMARKS"] += " " + row_dict["REMARKS"]
                        continue

                    txn = {
                        "TXN_DATE": normalize_date(row_dict.get("TXN_DATE", "")),
                        "VAL_DATE": normalize_date(row_dict.get("VAL_DATE", "")),
                        "REFERENCE": row_dict.get("REFERENCE", ""),
                        "REMARKS": row_dict.get("REMARKS", ""),
                        "DEBIT": row_dict.get("DEBIT", "0.00"),
                        "CREDIT": row_dict.get("CREDIT", "0.00"),
                        "BALANCE": row_dict.get("BALANCE", "0.00"),
                        "Check": "",
                        "Check 2": "",
                    }
                    transactions.append(txn)

    if not transactions:
        return {"error": "No valid transactions found."}
    return calculate_checks(transactions)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(
            "Usage: python zenith-parser-001.py path/to/statement.pdf", file=sys.stderr
        )
        sys.exit(1)
    file_path = sys.argv[1]
    print(json.dumps(parse_pdf(file_path), indent=2))
