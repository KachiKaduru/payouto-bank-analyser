from typing import Dict, List
import pdfplumber
from utils import MAIN_TABLE_SETTINGS


def parse(path: str) -> List[Dict[str, str]]:
    transactions = []
    global_headers = None

    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            print("\n=== PAGE", i, "===")
            tables = page.extract_tables(MAIN_TABLE_SETTINGS)
            if not tables:
                print("NO TABLES")
            else:
                for t_index, table in enumerate(tables):
                    print(f"--- TABLE {t_index} ---")
                    for row in table:
                        print(row)
    return transactions
