import sys
import re
import pdfplumber
from typing import List, Dict

from utils import (
    normalize_column_name,
    FIELD_MAPPINGS,
    normalize_date,
    to_float,
    parse_text_row,
    calculate_checks,
)


def parse(path: str) -> List[Dict[str, str]]:
    transactions = []
    global_headers = None
    global_header_map = None

    date_patterns = [
        r"^\d{1,2}[-/ ]?[A-Za-z]{3}[-/ ]?\d{2,4}",  # 14 Jul 24 / 14-Jul-2024
        r"^\d{1,2}[-/ ]?[A-Za-z]{4,9}[-/ ]?\d{2,4}",  # 14 July 2024
        r"^\d{2}[-/.]\d{2}[-/.]\d{2,4}",  # 01/08/24 or 01/08/2024
    ]

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                print(f"(wema): Processing page {page_num}", file=sys.stderr)
                text = page.extract_text()

                if not text:
                    print(f"(wema): No text found on page {page_num}", file=sys.stderr)
                    continue

                lines = text.split("\n")

                # Look for header row
                for i, line in enumerate(lines):
                    print(f"(wema): Line {i}: {line}", file=sys.stderr)
                    if all(
                        h.lower() in line.lower()
                        for h in ["date", "reference", "balance"]
                    ):
                        headers = [normalize_column_name(h) for h in line.split()]
                        global_headers = headers
                        global_header_map = {
                            idx: h
                            for idx, h in enumerate(global_headers)
                            if h in FIELD_MAPPINGS
                        }
                        print(f"(wema): Extracted header line: {line}", file=sys.stderr)
                        print(
                            f"(wema): Normalized headers: {global_headers}",
                            file=sys.stderr,
                        )

                        # Start parsing from next line
                        data_lines = lines[i + 1 :]
                        current_row = []

                        for dl in data_lines:
                            if any(re.match(p, dl) for p in date_patterns):
                                if current_row:
                                    transactions.append(
                                        parse_text_row(current_row, global_headers)
                                    )
                                current_row = [dl]
                            else:
                                current_row.append(dl)

                        if current_row:
                            transactions.append(
                                parse_text_row(current_row, global_headers)
                            )
                        break  # stop after first header on the page

        if transactions:
            print(f"(wema): Parsed {len(transactions)} transactions", file=sys.stderr)
            print(f"(wema): First sample row: {transactions[0]}", file=sys.stderr)
        else:
            print("(wema): No transactions parsed at all", file=sys.stderr)

        return calculate_checks(
            [t for t in transactions if t["TXN_DATE"] or t["VAL_DATE"]]
        )

    except Exception as e:
        print(f"Error processing Wema Bank statement: {e}", file=sys.stderr)
        return []
