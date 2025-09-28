import re
import sys
from typing import List, Dict, Tuple

import pdfplumber

from utils import (
    normalize_column_name,
    parse_text_row,
    calculate_checks,
)

# Toggle debug prints to stderr
DEBUG = False

# Flexible date detection for common formats in Access statements
DATE_RE = re.compile(
    r"^\s*(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}|\d{4}-\d{2}-\d{2})"
)


def _dbg(*args, **kwargs):
    if DEBUG:
        print(*args, **kwargs, file=sys.stderr)


def _group_words_into_lines(words: List[Dict], v_tol: float = 3.0) -> List[Dict]:
    """
    Group page.extract_words() output into visual lines by 'top' coordinate.
    Returns list of dicts: { 'words': [word_dicts], 'text': '...', 'top': float, 'bottom': float }
    """
    if not words:
        return []

    # sort by vertical position then horizontal
    words = sorted(words, key=lambda w: (round(w["top"], 2), w["x0"]))
    lines: List[List[Dict]] = []
    current = [words[0]]
    current_top = words[0]["top"]

    for w in words[1:]:
        if abs(w["top"] - current_top) <= v_tol:
            current.append(w)
            # keep current_top as running average to handle slight drift
            current_top = (current_top * (len(current) - 1) + w["top"]) / len(current)
        else:
            lines.append(current)
            current = [w]
            current_top = w["top"]
    lines.append(current)

    out = []
    for row_words in lines:
        row_words = sorted(row_words, key=lambda x: x["x0"])
        text = " ".join(w["text"] for w in row_words)
        top = sum(w["top"] for w in row_words) / len(row_words)
        bottom = sum(w["bottom"] for w in row_words) / len(row_words)
        out.append({"words": row_words, "text": text, "top": top, "bottom": bottom})
    return out


def _build_columns_from_header(
    header_words: List[Dict], page_width: float, gap_threshold: float = None
) -> List[Tuple[float, float, str]]:
    """
    From header line words, cluster them into columns using horizontal gaps.
    Returns list of (x0, x1, header_text) for each column.
    """
    if not header_words:
        return []

    if gap_threshold is None:
        # adaptive threshold: small fraction of page width
        gap_threshold = max(18, page_width * 0.02)

    cols: List[List[Dict]] = []
    current = [header_words[0]]

    for w in header_words[1:]:
        prev = current[-1]
        gap = w["x0"] - prev["x1"]
        if gap > gap_threshold:
            cols.append(current)
            current = [w]
        else:
            current.append(w)
    cols.append(current)

    columns = []
    for c in cols:
        x0 = min(w["x0"] for w in c) - 1.0
        x1 = max(w["x1"] for w in c) + 1.0
        header_text = " ".join(w["text"] for w in c).strip()
        columns.append((x0, x1, header_text))
    return columns


def _line_to_parts(
    line_words: List[Dict], columns: List[Tuple[float, float, str]]
) -> List[str]:
    """
    Given words in a visual line and list of (x0,x1,header_text),
    return list of column texts aligned to the columns.
    """
    parts = ["" for _ in columns]

    for w in line_words:
        cx = (w["x0"] + w["x1"]) / 2.0
        # find column for the word
        for idx, (x0, x1, _) in enumerate(columns):
            if cx >= x0 and cx <= x1:
                if parts[idx]:
                    parts[idx] += " " + w["text"]
                else:
                    parts[idx] = w["text"]
                break
        else:
            # if no column matched, append to the last column (sensible fallback)
            if parts:
                if parts[-1]:
                    parts[-1] += " " + w["text"]
                else:
                    parts[-1] = w["text"]
    # strip whitespace
    parts = [p.strip() for p in parts]
    return parts


def _looks_like_summary_line(joined_text: str) -> bool:
    """
    Heuristics to ignore summary / meta lines that are not transactions.
    """
    tch = joined_text.lower().strip()
    if not tch:
        return True
    # common non-transaction lines
    for token in (
        "opening balance",
        "closing balance",
        "total withdrawals",
        "total lodgements",
        "account statement",
        "account name",
        "summary statement",
        "closing balance",
        "debit count",
        "credit count",
        "account number",
        "address",
        "currency",
        "end date",
        "start date",
        "date printed",
    ):
        if token in tch:
            return True
    return False


def parse(path: str) -> List[Dict[str, str]]:
    """
    Parse Access Bank variant statement using a hybrid approach:
    - detect header visually (by word content)
    - derive x-bounds for each column from header word positions
    - for each visual line after the header, extract column text by x-bounds
    - assemble multi-line transactions (continuations) when date missing
    - feed final rows to utils.parse_text_row, then calculate_checks
    """
    transactions: List[Dict[str, str]] = []

    headers_normalized: List[str] = []
    columns_bounds: List[Tuple[float, float, str]] = []
    header_found = False

    with pdfplumber.open(path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            _dbg(f"(access parser_001) page {page_num}", file=sys.stderr)

            # extract positioned words for line-building
            words = page.extract_words(
                x_tolerance=1, y_tolerance=1, keep_blank_chars=False
            )
            if not words:
                _dbg(f"no words on page {page_num}")
                continue

            lines = _group_words_into_lines(words, v_tol=3.0)

            if not lines:
                _dbg(f"no grouped lines on page {page_num}")
                continue

            # If header not found yet, look for a line that contains Withdrawals+Lodgements or other header hints
            if not header_found:
                for li, line in enumerate(lines):
                    text_l = line["text"].lower()
                    # Primary signal: both words appear on the header line
                    if (
                        ("withdrawals" in text_l and "lodgements" in text_l)
                        or ("withdrawals" in text_l and "balance" in text_l)
                        or ("lodgements" in text_l and "balance" in text_l)
                    ):
                        header_found = True
                        header_line_index = li
                        header_words = line["words"]
                        # build columns from header words
                        columns_bounds = _build_columns_from_header(
                            header_words, page.width
                        )
                        # build normalized header names
                        headers_normalized = [
                            normalize_column_name(hdr_text)
                            for (_, _, hdr_text) in columns_bounds
                        ]
                        _dbg(
                            f"Detected header line (page {page_num}, line {li}):",
                            line["text"],
                        )
                        _dbg("Columns (x0,x1,text):")
                        for cb in columns_bounds:
                            _dbg(cb)
                        break

                # If header still not found on this page, carry on to next page
                if not header_found:
                    _dbg(f"No header found on page {page_num}")
                    continue

                # process lines after header on the same page
                work_lines = lines[header_line_index + 1 :]
            else:
                work_lines = lines

            # Now iterate work_lines and assemble transactions
            current_accum: List[str] = []
            # find date column index (TXN_DATE or VAL_DATE) if possible
            date_col_idx = 0
            if headers_normalized:
                for i, h in enumerate(headers_normalized):
                    if h in ("TXN_DATE", "VAL_DATE"):
                        date_col_idx = i
                        break

            # find remarks column index (best-effort: prefer REMARKS)
            remarks_col_idx = None
            if headers_normalized:
                if "REMARKS" in headers_normalized:
                    remarks_col_idx = headers_normalized.index("REMARKS")
                elif "REFERENCE" in headers_normalized:
                    remarks_col_idx = headers_normalized.index("REFERENCE")
                else:
                    # fallback to last column
                    remarks_col_idx = len(headers_normalized) - 1

            for line in work_lines:
                # quick skip of summary-like lines
                if _looks_like_summary_line(line["text"]):
                    _dbg("Skipping summary-like line:", line["text"])
                    continue

                parts = _line_to_parts(line["words"], columns_bounds)

                # some heuristics: if first column is blank but second has date, try second
                date_candidate = (
                    parts[date_col_idx] if date_col_idx < len(parts) else ""
                )
                if not DATE_RE.match(date_candidate):
                    # try any column that looks like a date (some statements put the value date or txn date in a different index)
                    found_idx = None
                    for idx, p in enumerate(parts):
                        if DATE_RE.match(p):
                            found_idx = idx
                            break
                    if found_idx is not None:
                        date_col_idx = found_idx
                        date_candidate = parts[date_col_idx]

                if DATE_RE.match(date_candidate):
                    # start of a new transaction row
                    if current_accum:
                        # flush previous
                        txn = parse_text_row(current_accum, headers_normalized)
                        # remove obvious summary rows after parse
                        joined = " ".join(
                            [
                                current_accum[i]
                                for i in range(len(current_accum))
                                if current_accum[i]
                            ]
                        )
                        if not _looks_like_summary_line(joined):
                            transactions.append(txn)
                        else:
                            _dbg("Filtered summary after parse:", joined)
                    current_accum = parts[:]  # copy parts for new accumulation
                else:
                    # continuation line -> append to remarks column if available, else concatenate to last column
                    if current_accum:
                        append_text = " ".join([p for p in parts if p]).strip()
                        if append_text:
                            if remarks_col_idx is not None and remarks_col_idx < len(
                                current_accum
                            ):
                                if current_accum[remarks_col_idx]:
                                    current_accum[remarks_col_idx] += " " + append_text
                                else:
                                    current_accum[remarks_col_idx] = append_text
                            else:
                                # fallback: append to last column
                                last_idx = len(current_accum) - 1
                                if current_accum[last_idx]:
                                    current_accum[last_idx] += " " + append_text
                                else:
                                    current_accum[last_idx] = append_text
                    else:
                        # stray continuation without a start; ignore
                        _dbg(
                            "Dropping stray continuation line (no current_accum):",
                            line["text"],
                        )
                        continue

            # end of page: flush any remaining accumulated row
            if current_accum:
                txn = parse_text_row(current_accum, headers_normalized)
                joined = " ".join(
                    [
                        current_accum[i]
                        for i in range(len(current_accum))
                        if current_accum[i]
                    ]
                )
                if not _looks_like_summary_line(joined):
                    transactions.append(txn)
                else:
                    _dbg("Filtered summary at page end:", joined)

    # final checks / numeric conversions
    return calculate_checks(
        [t for t in transactions if (t.get("TXN_DATE") or t.get("VAL_DATE"))]
    )
