import sys
import re
from typing import List, Dict, Tuple, Optional
from datetime import datetime
from PyPDF2 import PdfReader, PdfWriter
import tempfile

TOLERANCE = 0.01

# ------------------------
# CONSTANTS / MAPPINGS
# ------------------------

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
        "actual transaction date",
        "actual\ntransaction\ndate",
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
        "date/time",
    ],
    "REFERENCE": [
        "reference",
        "ref",
        "transaction id",
        "transaction reference",
        "txn id",
        "tran id",
        "ref. number",
        "ref. no",
        "reference number",
        "reference\nnumber",
        "check no",
        "chq\nno",
        "chq no",
        "channel",
        "DOC NO.",
    ],
    "REMARKS": [
        "remarks",
        "description",
        "descrip�on",
        "descrip\x00on",
        "descrip\ufffdon",
        "narration",
        "comment",
        "transaction detail",
        "transaction details",
        "transaction description",
        "details",
        "descr",
        "REMARKS",
        "description/payee/memo",
        "TRANSACCTNAMION DESC",
    ],
    "DEBIT": [
        "dr",
        "debit",
        "debits",
        "DEBIT",
        "debit (NGN)",
        "debit(₦)",
        "debit(\u20a6)",
        "debit amount",
        "money out",
        "money out (NGN)",
        "pay out",
        "withdrawal",
        "withdrawals",
        "withdrawal(DR)",
    ],
    "CREDIT": [
        "cr",
        "credit",
        "CREDIT",
        "credits",
        "credit (NGN)",
        "credit(₦)",
        "credit(\u20a6)",
        "credit amount",
        "deposit",
        "deposits",
        "deposit(CR)",
        "money in",
        "money in (NGN)",
        "pay in",
        "lodgement",
        "lodgements",
    ],
    "BALANCE": [
        "bal",
        "balance",
        "BALANCE",
        "account balance",
        "current balance",
        "current\nbalance",
        "balance (NGN)",
        "balance(₦)",
        "balance(\u20a6)",
        "",
    ],
    "AMOUNT": [
        "amount",
        "txn amount",
        "transaction amount",
        "debit/credit(₦)",
        "debit/credit(\u20a6)",
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

# ------------------------
# COMPILED REGEX (shared)
# ------------------------

RX_AMOUNT_LIKE = re.compile(r"^\s*[-\d,]+(?:\.\d{2})?\s*$")
RX_TWO_DIGIT_YEAR = re.compile(r"^\s*\d{2}\s*$")  # "25"
RX_FOUR_DIGIT_YEAR = re.compile(r"^\s*\d{4}\s*$")  # "2025"
RX_ENDS_MONTH_DASH = re.compile(
    r"^\s*\d{2}-[A-Z]{3}-\s*$"
)  # "30-JAN-" (optional spaces around)
RX_MULTI_WS = re.compile(r"\s+")


# ------------------------
# NUMERIC / MONEY HELPERS
# ------------------------
def to_float(value: str) -> float:
    value = value.strip() if value else ""
    if not value or value in {"-", ""}:
        return 0.0
    try:
        cleaned = re.sub(r"[^\d.-]", "", value)
        return float(cleaned)
    except ValueError:
        print(f"Warning: Could not parse number '{value}'", file=sys.stderr)
        return 0.0


def clean_money(s: Optional[str]) -> str:
    """
    Normalizes placeholders like '----', '—', '' to '0.00',
    strips non-numeric clutter, handles parentheses as negatives,
    returns a clean numeric string with 2 decimal places.
    """
    if not s:
        return "0.00"

    t = s.strip()
    if t in {"", "-", "—", "----"}:
        return "0.00"

    # Detect parentheses-based negatives: (25.00) → -25.00
    is_negative = False
    if t.startswith("(") and t.endswith(")"):
        is_negative = True
        t = t[1:-1].strip()

    # Remove any non-numeric clutter except decimal and minus
    if not RX_AMOUNT_LIKE.match(t):
        t = re.sub(r"[^\d.,-]", "", t)

    try:
        value = to_float(t)
        if is_negative:
            value = -value
        return f"{value:.2f}"
    except Exception:
        return "0.00"


def normalize_money(s: Optional[str]) -> str:
    """Alias for clean_money for readability in parsers."""
    return clean_money(s)


# ------------------------
# DATE HELPERS
# ------------------------
def join_date_fragments(s: str) -> str:
    """
    Turns '03-FEB-\\n25' or '03- FEB- 25' into '03-FEB-25' (prior to normalize_date()).
    """
    if not s:
        return ""
    return RX_MULTI_WS.sub("", s)


def is_two_digit_year(s: str) -> bool:
    return bool(RX_TWO_DIGIT_YEAR.fullmatch((s or "").strip()))


def is_year_only(s: str) -> bool:
    ss = (s or "").strip()
    return bool(RX_TWO_DIGIT_YEAR.fullmatch(ss) or RX_FOUR_DIGIT_YEAR.fullmatch(ss))


def ends_with_month_dash(s: str) -> bool:
    return bool(RX_ENDS_MONTH_DASH.fullmatch((s or "").strip()))


def normalize_date(date_str: str) -> str:
    if not date_str:
        return ""

    # Skip non-date rows like totals/closing balance
    if re.match(r"(?i)^(total|closing|opening|balance|subtotal)", date_str.strip()):
        return ""

    s = date_str.strip()

    # Remove trailing 'Page', 'Page 2', 'Page-4', etc.
    s = re.sub(r"[Pp]age[\s\-]?\d*$", "", s).strip()

    # Normalize spacing around common separators
    s = re.sub(r"\s*-\s*", "-", s)
    s = re.sub(r"\s*/\s*", "/", s)
    s = re.sub(r"\s*:\s*", ":", s)
    s = re.sub(r"\s+", " ", s)

    # Collapse spaces occurring *between digits* (e.g. '2 0 2 5' -> '2025')
    s = re.sub(r"(?<=\d)\s+(?=\d)", "", s)

    # If there are line breaks, first try a "hard collapse" (good for '06/24/202\n5')
    if "\n" in date_str or "\r" in date_str:
        collapsed = re.sub(r"[\r\n]+", "", s)
        # Also fix digit-separated-by-spaces again after collapse
        collapsed = re.sub(r"(?<=\d)\s+(?=\d)", "", collapsed)
        try:
            # Fast path: if collapsed parses, take it
            for fmt in (
                "%d-%b-%Y",
                "%d-%b-%y",
                "%d/%m/%Y",
                "%d/%m/%y",
                "%d-%m-%Y",
                "%d-%m-%y",
                "%m/%d/%Y",
                "%m/%d/%y",
                "%Y-%m-%d",
                "%Y-%m-%dT%H:%M:%S",
                "%d %b %Y",
                "%d.%m.%Y",
                "%d.%m.%y",
                "%d %B %Y",
                "%d-%B-%Y",
                "%d/%b/%y",
            ):
                try:
                    dt = datetime.strptime(collapsed, fmt)
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    pass
        except Exception:
            pass

        # Fallback for things like '11-Dec-\n2024' -> '11-Dec-2024'
        parts = [p.strip("- /:.") for p in re.split(r"[\r\n]+", s) if p.strip()]
        if parts:
            # If first chunk already ends with a date separator, keep it; else join with '-'
            # e.g. '11-Dec-' + '2024' => '11-Dec-2024'; '11 Dec' + '2024' => '11 Dec-2024'
            if re.search(r"[-/]", parts[0] + "-"):
                s = "".join(parts) if parts[0].endswith(("/", "-")) else "-".join(parts)
            else:
                s = "-".join(parts)

    # Fix truncated 4-digit year like '024-12-09' -> '2024-12-09'
    if re.match(r"^\d{3}-\d{2}-\d{2}$", s):
        s = "2" + s

    date_formats = [
        "%d-%b-%Y",
        "%d-%b-%y",
        "%d/%m/%Y",
        "%d/%m/%y",
        "%d-%m-%Y",
        "%d-%m-%y",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%d %b %Y",
        "%d.%m.%Y",
        "%d.%m.%y",
        "%d %B %Y",
        "%d-%B-%Y",
        "%d/%b/%y",
    ]

    for fmt in date_formats:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # If nothing matches, keep original so upstream can decide what to do.
    print(
        f"Warning: Could not parse date '{date_str}' (cleaned='{s}')", file=sys.stderr
    )
    return date_str


def normalize_whitespace(text: str) -> str:
    """
    Merge multi-line narration into 1 line, collapse repeated spaces,
    and insert a space after slashes where needed.
    """
    if not text:
        return ""

    # Replace newline with space
    text = text.replace("\n", " ")

    # Collapse multiple spaces
    text = re.sub(r"\s+", " ", text)

    # Fix slashes: "ABC/DEF" → "ABC / DEF"
    text = re.sub(r"/(?=\w)", " / ", text)

    return text.strip()


# ------------------------
# COLUMN / ROW HELPERS
# ------------------------
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
        debit = to_float(txn.get("DEBIT", "0.00"))
        credit = to_float(txn.get("CREDIT", "0.00"))
        current_balance = to_float(txn.get("BALANCE", "0.00"))

        if prev_balance is not None:
            expected = round(prev_balance - debit + credit, 2)
            actual = round(current_balance, 2)
            diff = abs(expected - actual)

            # Guard clause for small differences
            if diff < 0.1:
                txn["Check"] = "TRUE"
            else:
                txn["Check"] = "FALSE"

            txn["Check 2"] = f"{diff:.2f}"
        else:
            txn["Check"] = "TRUE"
            txn["Check 2"] = "0.00"

        updated.append(txn)
        prev_balance = current_balance

    return updated


def parse_text_row(row: List[str], headers: List[str]) -> Dict[str, str]:
    standardized_row = STANDARDIZED_ROW.copy()

    if len(row) < len(headers):
        row.extend([""] * (len(headers) - len(row)))

    row_dict = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}

    # Join fragments before normalize_date
    standardized_row["TXN_DATE"] = normalize_date(
        join_date_fragments(row_dict.get("TXN_DATE", row_dict.get("VAL_DATE", "")))
    )
    standardized_row["VAL_DATE"] = normalize_date(
        join_date_fragments(row_dict.get("VAL_DATE", row_dict.get("TXN_DATE", "")))
    )

    standardized_row["REFERENCE"] = row_dict.get("REFERENCE", "")
    standardized_row["REMARKS"] = row_dict.get("REMARKS", "")

    standardized_row["DEBIT"] = normalize_money(row_dict.get("DEBIT", "0.00"))
    standardized_row["CREDIT"] = normalize_money(row_dict.get("CREDIT", "0.00"))
    bal_raw = (row_dict.get("BALANCE", "") or "").strip()
    standardized_row["BALANCE"] = f"{to_float(bal_raw):.2f}" if bal_raw else ""

    return standardized_row


# ------------------------
# PAGE-BREAK YEAR ARTIFACT HELPERS
# ------------------------


def looks_like_year_artifact(row: Dict[str, str]) -> bool:
    """
    Detects the 'year-only' page-break artifact you described:
    - TXN_DATE and VAL_DATE are two-digit numbers (e.g., '25')
    - REMARKS empty
    - DEBIT and CREDIT are '' or '0.00'
    - BALANCE empty
    """
    no_remarks = not (row.get("REMARKS") or "").strip()
    debit = (row.get("DEBIT") or "").strip()
    credit = (row.get("CREDIT") or "").strip()
    balance = (row.get("BALANCE") or "").strip()
    money_empty = debit in {"", "0.00"} and credit in {"", "0.00"} and balance == ""
    year_only_dates = is_two_digit_year(
        row.get("TXN_DATE") or ""
    ) and is_two_digit_year(row.get("VAL_DATE") or "")
    return no_remarks and money_empty and year_only_dates


def merge_year_artifact(prev_row: Dict[str, str], artifact_row: Dict[str, str]) -> bool:
    """
    If prev_row has RAW_TXN_DATE/RAW_VAL_DATE (preferred) or TXN_DATE/VAL_DATE
    ending with 'DD-MMM-', append the artifact year ('25' or '2025'),
    re-normalize, update prev_row in-place, and return True.
    Returns False if merge didn't apply.
    """
    y = (artifact_row.get("TXN_DATE") or "").strip()
    if not y:
        return False

    raw_txn = prev_row.get("RAW_TXN_DATE", prev_row.get("TXN_DATE", ""))
    raw_val = prev_row.get("RAW_VAL_DATE", prev_row.get("VAL_DATE", ""))

    if ends_with_month_dash(raw_txn) and ends_with_month_dash(raw_val):
        merged_txn_raw = f"{raw_txn}{y}"
        merged_val_raw = f"{raw_val}{y}"

        prev_row["RAW_TXN_DATE"] = merged_txn_raw
        prev_row["RAW_VAL_DATE"] = merged_val_raw
        prev_row["TXN_DATE"] = normalize_date(join_date_fragments(merged_txn_raw))
        prev_row["VAL_DATE"] = normalize_date(join_date_fragments(merged_val_raw))
        return True

    return False


def merge_and_drop_year_artifacts(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Walks the list, merges 'year-only' artifact rows into the previous row when possible,
    and drops the artifact rows. Also normalizes money and dates on the way.
    Safe to call from any parser after initial extraction.
    """
    out: List[Dict[str, str]] = []
    i = 0
    while i < len(rows):
        r = rows[i]
        if looks_like_year_artifact(r) and out:
            merged = merge_year_artifact(out[-1], r)
            # Drop the artifact either way
            i += 1
            continue

        # Normalize money + internal date fragments defensively
        r["DEBIT"] = normalize_money(r.get("DEBIT", "0.00"))
        r["CREDIT"] = normalize_money(r.get("CREDIT", "0.00"))
        bal_raw = (r.get("BALANCE", "") or "").strip()
        r["BALANCE"] = f"{to_float(bal_raw):.2f}" if bal_raw else ""

        if r.get("TXN_DATE"):
            r["TXN_DATE"] = normalize_date(join_date_fragments(r["TXN_DATE"]))
        if r.get("VAL_DATE"):
            r["VAL_DATE"] = normalize_date(join_date_fragments(r["VAL_DATE"]))

        out.append(r)
        i += 1

    # Remove helper keys if present
    for r in out:
        r.pop("RAW_TXN_DATE", None)
        r.pop("RAW_VAL_DATE", None)
    return out


# ------------------------
# PDF DECRYPT
# ------------------------


def decrypt_pdf(
    pdf_path: str,
    password: str = "",
    effective_path: Optional[str] = None,
    temp_file_path: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Returns (readable_path, effective_path).
    - If encrypted and password is correct: writes a temporary decrypted copy and returns its path.
    - If not encrypted: returns (pdf_path, pdf_path).
    """
    reader = PdfReader(pdf_path)
    if reader.is_encrypted:
        if not password:
            raise ValueError("Encrypted PDF detected. Please provide a password.")
        reader.decrypt(password)
        print("PDF decrypted successfully.", file=sys.stderr)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            writer = PdfWriter()
            for page in reader.pages:
                writer.add_page(page)
            # Preserve original metadata (producer, author, etc.)
            if reader.metadata:
                try:
                    metadata = {
                        (k if k.startswith("/") else f"/{k}"): str(v)
                        for k, v in reader.metadata.items()
                        if v is not None
                    }
                    if metadata:
                        writer.add_metadata(metadata)
                except Exception as meta_err:
                    print(
                        f"Warning: Failed to copy PDF metadata: {meta_err}",
                        file=sys.stderr,
                    )
            writer.write(temp_file)
            temp_file_path = temp_file.name
            effective_path = temp_file_path
        return temp_file_path, effective_path or temp_file_path

    # Not encrypted
    return pdf_path, effective_path or pdf_path
