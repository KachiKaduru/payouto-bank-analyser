import sys
import pdfplumber
from typing import List, Dict
from utils import (
    normalize_column_name,
    FIELD_MAPPINGS,
    MAIN_TABLE_SETTINGS,
    parse_text_row,
    calculate_checks,
)


def parse(path: str) -> List[Dict[str, str]]:
    transactions = []
    global_headers = None

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                print(f"(gtb): Processing page {page_num}", file=sys.stderr)

                # Table extraction settings
                table_settings = MAIN_TABLE_SETTINGS.copy()
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
                            global_headers = normalized_first_row

                            print(
                                f"Stored global headers: {global_headers}",
                                file=sys.stderr,
                            )
                            data_rows = table[1:]
                        elif is_header_row and global_headers:
                            if normalized_first_row == global_headers:
                                print(
                                    f"Skipping repeated header row on page {page_num}",
                                    file=sys.stderr,
                                )
                                data_rows = table[1:]
                            else:
                                print(
                                    f"Different headers on page {page_num}, treating as data",
                                    file=sys.stderr,
                                )
                                data_rows = table
                        else:
                            data_rows = table

                        if not global_headers:
                            print(
                                f"(gtb): No headers found by page {page_num}, skipping table",
                                file=sys.stderr,
                            )
                            continue

                        for row in data_rows:
                            standardized_row = parse_text_row(row, global_headers)
                            transactions.append(standardized_row)
                else:
                    print(
                        f"(gtb): No tables found on page {page_num}, attempting text extraction",
                        file=sys.stderr,
                    )

        return calculate_checks(
            [t for t in transactions if t["TXN_DATE"] or t["VAL_DATE"]]
        )

    except Exception as e:
        print(f"Error processing GTBank statement: {e}", file=sys.stderr)
        return []
