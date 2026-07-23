import re
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pdfplumber

from utils import (
    STANDARDIZED_ROW,
    calculate_checks,
    normalize_money,
    normalize_whitespace,
)

# Keystone compact date format: 05Jun26
RX_DATE = re.compile(r"^\s*(\d{1,2}[A-Za-z]{3}\d{2})\s*$")
RX_FOOTER = re.compile(
    r"^\s*-?\s*Page\s+\d+\s+of\s+\d+\s*-?\s*$",
    re.IGNORECASE,
)

TABLE_SETTINGS = {
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


def _clean_cell(value: Optional[str]) -> str:
    return (value or "").strip()


def _normalize_header(value: Optional[str]) -> str:
    value = _clean_cell(value)
    value = re.sub(r"\s+", " ", value)
    return value.lower()


def _normalize_keystone_date(value: str) -> str:
    """Convert 05Jun26 to 2026-06-05."""
    match = RX_DATE.fullmatch(value or "")
    if not match:
        return ""

    try:
        return datetime.strptime(
            match.group(1),
            "%d%b%y",
        ).strftime("%Y-%m-%d")
    except ValueError:
        return ""


def _find_table_header(
    table: List[List[Optional[str]]],
) -> Tuple[Optional[int], Optional[Dict[str, int]]]:
    """
    Locate Keystone's transaction header.

    Expected logical fields:
    Date | V. Date | Narration | Ref | Debit | Credit | Balance

    The physical PDF may contain extra blank columns.
    """
    for row_index, row in enumerate(table):
        headers = [_normalize_header(cell) for cell in row]

        has_value_date = "v. date" in headers or "v date" in headers

        required = {
            "date",
            "narration",
            "debit",
            "credit",
            "balance",
        }

        if has_value_date and required.issubset(set(headers)):
            header_map: Dict[str, int] = {}

            for index, header in enumerate(headers):
                if header and header not in header_map:
                    header_map[header] = index

            if "v. date" not in header_map and "v date" in header_map:
                header_map["v. date"] = header_map["v date"]

            return row_index, header_map

    return None, None


def _find_header_top(page) -> Optional[float]:
    """
    Locate the visual table header.

    This lets us crop page 1 below its account-summary tables.
    """
    words = page.extract_words(
        x_tolerance=1,
        y_tolerance=2,
        keep_blank_chars=False,
        use_text_flow=False,
    )

    for word in words:
        if word["text"].lower() != "date" or word["x0"] > 70:
            continue

        top = word["top"]

        has_narration = any(
            other["text"].lower() == "narration" and abs(other["top"] - top) <= 2
            for other in words
        )

        has_balance = any(
            other["text"].lower() == "balance" and abs(other["top"] - top) <= 2
            for other in words
        )

        if has_narration and has_balance:
            return top

    return None


def _get(
    cells: List[str],
    index: Optional[int],
) -> str:
    if index is None or index < 0 or index >= len(cells):
        return ""

    return cells[index]


def _append_narration(
    transaction: Dict[str, str],
    narration: str,
) -> None:
    narration = normalize_whitespace(narration)

    if not narration:
        return

    transaction["REMARKS"] = normalize_whitespace(
        f'{transaction.get("REMARKS", "")} {narration}'
    )


def _build_transaction(
    cells: List[str],
    header_map: Dict[str, int],
) -> Optional[Dict[str, str]]:
    txn_date = _normalize_keystone_date(_get(cells, header_map.get("date")))

    val_date = _normalize_keystone_date(_get(cells, header_map.get("v. date")))

    if not txn_date:
        return None

    if not val_date:
        val_date = txn_date

    balance_index = header_map["balance"]

    # Keystone's right boundary sometimes produces an extra column:
    #
    #     833.78 -> ["83", "3.78"]
    #
    # Joining everything from Balance to the end repairs this.
    raw_balance = "".join(cells[balance_index:])

    row = STANDARDIZED_ROW.copy()

    row.update(
        {
            "TXN_DATE": txn_date,
            "VAL_DATE": val_date,
            "REFERENCE": normalize_whitespace(_get(cells, header_map.get("ref"))),
            "REMARKS": normalize_whitespace(_get(cells, header_map.get("narration"))),
            "DEBIT": normalize_money(_get(cells, header_map.get("debit"))),
            "CREDIT": normalize_money(_get(cells, header_map.get("credit"))),
            "BALANCE": normalize_money(raw_balance),
        }
    )

    return row


def parse(path: str) -> List[Dict[str, str]]:
    transactions: List[Dict[str, str]] = []
    current_transaction: Optional[Dict[str, str]] = None

    try:
        with pdfplumber.open(path) as pdf:
            for page_number, page in enumerate(
                pdf.pages,
                1,
            ):
                print(
                    ("(keystone_universal): " f"Processing page {page_number}"),
                    file=sys.stderr,
                )

                header_top = _find_header_top(page)

                if header_top is None:
                    print(
                        (
                            "(keystone_universal): "
                            "Header not found on page "
                            f"{page_number}; skipping page"
                        ),
                        file=sys.stderr,
                    )
                    continue

                # Remove the account-summary area above the
                # transaction table.
                table_area = page.crop(
                    (
                        0,
                        max(0, header_top - 5),
                        page.width,
                        page.height,
                    )
                )

                tables = table_area.extract_tables(TABLE_SETTINGS) or []

                page_table_found = False

                for table in tables:
                    if not table:
                        continue

                    header_index, header_map = _find_table_header(table)

                    if header_index is None or header_map is None:
                        continue

                    page_table_found = True

                    for raw_row in table[header_index + 1 :]:
                        cells = [_clean_cell(cell) for cell in raw_row]

                        non_empty = " ".join(cell for cell in cells if cell).strip()

                        if not non_empty or RX_FOOTER.fullmatch(non_empty):
                            continue

                        new_transaction = _build_transaction(
                            cells,
                            header_map,
                        )

                        if new_transaction is not None:
                            if current_transaction is not None:
                                transactions.append(current_transaction)

                            current_transaction = new_transaction
                            continue

                        # No dates means this physical table row is
                        # a continuation of the current narration.
                        #
                        # This intentionally works across page breaks.
                        narration = _get(
                            cells,
                            header_map.get("narration"),
                        )

                        if (
                            current_transaction is not None
                            and narration
                            and "open balance" not in narration.lower()
                        ):
                            _append_narration(
                                current_transaction,
                                narration,
                            )

                if not page_table_found:
                    print(
                        (
                            "(keystone_universal): "
                            "No matching transaction table "
                            f"found on page {page_number}"
                        ),
                        file=sys.stderr,
                    )

        if current_transaction is not None:
            transactions.append(current_transaction)

        transactions = [
            row for row in transactions if row.get("TXN_DATE") and row.get("BALANCE")
        ]

        print(
            ("(keystone_universal): Parsed " f"{len(transactions)} transactions"),
            file=sys.stderr,
        )

        return calculate_checks(transactions)

    except Exception as exc:
        print(
            ("(keystone_universal): " f"Error processing PDF: {exc}"),
            file=sys.stderr,
        )
        return []
