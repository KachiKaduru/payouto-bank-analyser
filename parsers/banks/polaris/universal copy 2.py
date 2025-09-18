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
    pending_row = None  # store last row for continuation merges

    # --- helpers ---
    def is_footer_line(line: str) -> bool:
        """Detect Polaris/Nomba footer links or generic web links we must ignore."""
        if not line:
            return False
        lower = line.lower().strip()
        # specific Polaris footer + generic URL checks
        if "polarisplus.polarisbanklimited.com" in lower:
            return True
        if lower.startswith("http") or lower.startswith("www"):
            return True
        if ".php" in lower and "genscript" in lower:
            return True
        # guard against any '.com' footers
        if ".com" in lower and len(lower.split()) <= 3:
            return True
        return False

    def extract_leading_date_str(line: str) -> str:
        """Return the leading date substring from a line, if present (else '').
        Covers patterns like 04-FEB-25, 04-Feb-2025, 04/02/2025, 2025-02-04, 'March 1st 2025'.
        """
        if not line:
            return ""
        patterns = [
            r"^\s*(\d{1,2}[-/\.][A-Za-z]{3,9}[-/\.]\d{2,4})",  # 05-JUN-25 or 05-Jun-2025
            r"^\s*([A-Za-z]{3,9}\s+\d{1,2}(?:st|nd|rd|th)?[,]?\s+\d{4})",  # March 1st 2025
            r"^\s*(\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4})",  # 04/02/2023
            r"^\s*(\d{4}-\d{2}-\d{2})",  # 2025-06-01
        ]
        for p in patterns:
            m = re.match(p, line, flags=re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return ""

    def candidate_normalized_date(line: str) -> str:
        """Normalize the leading date substring (if any) using normalize_date."""
        s = extract_leading_date_str(line)
        if not s:
            return ""
        # remove ordinals like '1st'
        s_clean = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", s, flags=re.IGNORECASE)
        return normalize_date(s_clean)

    def starts_with_date(line: str) -> bool:
        """Quick boolean check whether line starts with a date-like token."""
        return bool(extract_leading_date_str(line))

    # --- main parsing ---
    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                print(f"(polaris): Processing page {page_num}", file=sys.stderr)

                # keep per-page transactions for duplicate checks
                page_transactions: List[Dict[str, str]] = []

                # Table extraction settings (same as original)
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

                # --- original table parsing logic (unchanged behavior) ---
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
                            global_header_map = {
                                i: h
                                for i, h in enumerate(global_headers)
                                if h in FIELD_MAPPINGS
                            }
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
                                f"(polaris): No headers found by page {page_num}, skipping table",
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

                        for row_idx, row in enumerate(data_rows):
                            if len(row) < len(global_headers):
                                row.extend([""] * (len(global_headers) - len(row)))

                            row_dict = {
                                global_headers[i]: (
                                    row[i] if i < len(global_headers) else ""
                                )
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
                            page_transactions.append(standardized_row)
                            pending_row = standardized_row

                else:
                    # fallback text extraction when page has no tables (keeps old behavior)
                    print(
                        f"(polaris): No tables found on page {page_num}, attempting text extraction",
                        file=sys.stderr,
                    )
                    text = page.extract_text() or ""
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

                # --- NEW: End-of-page leftover text check (date-start block, skip footers) ---
                try:
                    if global_headers:
                        page_text = page.extract_text() or ""
                        # normalize lines and remove blank lines
                        lines = [
                            ln.strip() for ln in page_text.split("\n") if ln.strip()
                        ]

                        # remove any lines that are pure footer links from the end first
                        # (so a trailing footer won't be considered part of a block)
                        while lines and is_footer_line(lines[-1]):
                            # pop footer lines off the end
                            print(
                                f"(polaris): stripping footer from page {page_num}: {lines[-1]}",
                                file=sys.stderr,
                            )
                            lines.pop()

                        if lines:
                            # find the last line that looks like it starts with a date
                            last_date_idx = None
                            for idx in range(len(lines) - 1, -1, -1):
                                if starts_with_date(lines[idx]) and not is_footer_line(
                                    lines[idx]
                                ):
                                    last_date_idx = idx
                                    break

                            if last_date_idx is not None:
                                # form a block: date line + any following lines (these are the continuation lines)
                                block_lines = lines[last_date_idx:]

                                # ensure we didn't accidentally include footers in the middle; strip footers inside block too
                                block_lines = [
                                    ln for ln in block_lines if not is_footer_line(ln)
                                ]
                                if not block_lines:
                                    # nothing left after removing footers
                                    pass
                                else:
                                    first_line = block_lines[0]
                                    normalized_date = candidate_normalized_date(
                                        first_line
                                    )

                                    # check duplicates:
                                    duplicate = False
                                    if normalized_date:
                                        for t in page_transactions:
                                            if (
                                                t.get("TXN_DATE") == normalized_date
                                                or t.get("VAL_DATE") == normalized_date
                                            ):
                                                duplicate = True
                                                break
                                    else:
                                        # fallback simple substring preview match
                                        preview = " ".join(block_lines)[:80].strip()
                                        for t in page_transactions:
                                            combined = (
                                                t.get("REMARKS", "")
                                                + " "
                                                + t.get("REFERENCE", "")
                                            ).strip()
                                            if preview and preview in combined:
                                                duplicate = True
                                                break

                                    if not duplicate:
                                        print(
                                            f"(polaris): Found trailing transaction block on page {page_num} (lines {last_date_idx}-{len(lines)-1}), adding.",
                                            file=sys.stderr,
                                        )
                                        parsed = parse_text_row(
                                            block_lines, global_headers
                                        )
                                        # safety: ensure parsed TXN_DATE isn't a URL (double check)
                                        if parsed.get(
                                            "TXN_DATE"
                                        ) and not is_footer_line(
                                            parsed.get("TXN_DATE")
                                        ):
                                            transactions.append(parsed)
                                            page_transactions.append(parsed)
                                            pending_row = parsed
                                        else:
                                            print(
                                                f"(polaris): Block parsed but TXN_DATE looks like footer; skipping.",
                                                file=sys.stderr,
                                            )
                                    else:
                                        print(
                                            f"(polaris): Trailing block on page {page_num} appears duplicate; skipping.",
                                            file=sys.stderr,
                                        )

                except Exception as e:
                    print(
                        f"(polaris): Error during end-of-page leftover check on page {page_num}: {e}",
                        file=sys.stderr,
                    )

            # finalize and run checks on rows that include dates
            return calculate_checks(
                [t for t in transactions if t["TXN_DATE"] or t["VAL_DATE"]]
            )

    except Exception as e:
        print(f"Error processing Polaris Bank statement: {e}", file=sys.stderr)
        return []
