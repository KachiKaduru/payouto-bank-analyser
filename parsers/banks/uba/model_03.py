import sys
import re
from collections import defaultdict
from typing import Dict, List, Optional

import pdfplumber

from utils import (
    STANDARDIZED_ROW,
    normalize_date,
    clean_money,
    calculate_checks,
)

MONTH_RX = (
    r"(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)"
)


ROW_START_RE = re.compile(
    rf"^{MONTH_RX}\s+\d{{1,2}}(?:st|nd|rd|th)(?:\s+\d{{4}})?$",
    re.IGNORECASE,
)

HEADER_RE = re.compile(
    r"TRANS\s+DATE.*VALUE\s+DATE.*NARRATION.*CHQ.*DEBIT.*CREDIT.*BALANCE",
    re.IGNORECASE,
)


def _normalize_uba_date(raw: str) -> str:
    if not raw:
        return ""
    raw = " ".join(raw.split())
    return normalize_date(raw)


def _clean_narration(text: str) -> str:
    if not text:
        return ""

    s = " ".join(text.split())

    # tighten punctuation/slashes after multiline joins
    s = re.sub(r"\s+([/.,])", r"\1", s)
    s = re.sub(r"([/@+-])\s+", r"\1", s)

    # preserve natural spacing elsewhere
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s


def _line_to_columns(words: List[dict]) -> Dict[str, str]:
    """
    Map words into fixed columns by x-position.

    Observed layout for this UBA variant:
      TXN DATE : x < 160
      VAL DATE : 160 <= x < 265
      NARRATION: 265 <= x < 371
      CHQ NO   : 371 <= x < 470
      DEBIT    : 470 <= x < 570
      CREDIT   : 570 <= x < 670
      BALANCE  : x >= 670
    """
    cols = {
        "txn": [],
        "val": [],
        "nar": [],
        "chq": [],
        "debit": [],
        "credit": [],
        "bal": [],
    }

    for w in sorted(words, key=lambda x: x["x0"]):
        x = w["x0"]
        t = w["text"]

        if x < 160:
            cols["txn"].append(t)
        elif x < 265:
            cols["val"].append(t)
        elif x < 371:
            cols["nar"].append(t)
        elif x < 470:
            cols["chq"].append(t)
        elif x < 570:
            cols["debit"].append(t)
        elif x < 670:
            cols["credit"].append(t)
        else:
            cols["bal"].append(t)

    return {k: " ".join(v).strip() for k, v in cols.items()}


def _extract_lines(page) -> List[Dict[str, str]]:
    words = page.extract_words(use_text_flow=False, x_tolerance=2, y_tolerance=3)
    if not words:
        return []

    buckets = defaultdict(list)
    for w in words:
        buckets[round(w["top"], 1)].append(w)

    lines = []
    for top in sorted(buckets):
        lines.append(_line_to_columns(buckets[top]))

    return lines


def _is_page_number_line(line: Dict[str, str]) -> bool:
    """
    Page number artifact appears as a lone number, typically in CHQ-ish area.
    Example: '2', '3'
    """
    joined = " ".join(v for v in line.values() if v).strip()
    if not re.fullmatch(r"\d{1,3}", joined or ""):
        return False

    # real page number lines in this PDF are not in txn/val/narration columns
    return bool(line.get("chq")) and not any(
        [
            line.get("txn"),
            line.get("val"),
            line.get("nar"),
            line.get("debit"),
            line.get("credit"),
            line.get("bal"),
        ]
    )


def _is_new_txn_start(line: Dict[str, str]) -> bool:
    return bool(ROW_START_RE.match((line.get("txn") or "").strip()))


def _looks_complete(row_buf: Dict[str, List[str] | str]) -> bool:
    txn_date = _normalize_uba_date(" ".join(row_buf.get("txn_parts", [])))
    return bool(txn_date and row_buf.get("bal"))


def _flush_row(
    row_buf: Optional[Dict[str, List[str] | str]],
) -> Optional[Dict[str, str]]:
    if not row_buf:
        return None

    txn_date = _normalize_uba_date(" ".join(row_buf.get("txn_parts", [])))
    val_date = _normalize_uba_date(" ".join(row_buf.get("val_parts", [])))

    if not txn_date or not row_buf.get("bal"):
        return None

    row = STANDARDIZED_ROW.copy()
    row["TXN_DATE"] = txn_date
    row["VAL_DATE"] = val_date
    row["REFERENCE"] = ""
    row["REMARKS"] = _clean_narration(" ".join(row_buf.get("nar_parts", [])))
    row["DEBIT"] = clean_money(row_buf.get("debit") or "0.00")
    row["CREDIT"] = clean_money(row_buf.get("credit") or "0.00")
    row["BALANCE"] = clean_money(row_buf.get("bal") or "0.00")
    row["Check"] = ""
    row["Check 2"] = ""

    return row


def parse(path: str) -> List[Dict[str, str]]:
    transactions: List[Dict[str, str]] = []
    current_row: Optional[Dict[str, List[str] | str]] = None
    in_txn_area = False

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                print(f"(uba model_03): Processing page {page_num}", file=sys.stderr)

                lines = _extract_lines(page)
                if not lines:
                    continue

                for line in lines:
                    joined = " ".join(v for v in line.values() if v).strip()
                    if not joined:
                        continue

                    if HEADER_RE.search(joined):
                        in_txn_area = True
                        continue

                    if not in_txn_area:
                        continue

                    if _is_page_number_line(line):
                        continue

                    # New row begins
                    if _is_new_txn_start(line):
                        flushed = _flush_row(current_row)
                        if flushed:
                            transactions.append(flushed)

                        current_row = {
                            "txn_parts": [line["txn"]] if line.get("txn") else [],
                            "val_parts": [line["val"]] if line.get("val") else [],
                            "nar_parts": [line["nar"]] if line.get("nar") else [],
                            "chq": line.get("chq", ""),
                            "debit": line.get("debit", ""),
                            "credit": line.get("credit", ""),
                            "bal": line.get("bal", ""),
                        }
                        continue

                    # Continuation line before first row on a page:
                    # this is how page-break split rows continue.
                    if current_row is None:
                        continue

                    # Pure txn-year continuation like lone "2025" at page top
                    if re.fullmatch(r"\d{4}", joined):
                        if line.get("txn") and not any(
                            [
                                line.get("val"),
                                line.get("nar"),
                                line.get("chq"),
                                line.get("debit"),
                                line.get("credit"),
                                line.get("bal"),
                            ]
                        ):
                            current_row["txn_parts"].append(line["txn"])
                            continue
                        if line.get("val") and not any(
                            [
                                line.get("txn"),
                                line.get("nar"),
                                line.get("chq"),
                                line.get("debit"),
                                line.get("credit"),
                                line.get("bal"),
                            ]
                        ):
                            current_row["val_parts"].append(line["val"])
                            continue

                    # Generic continuation
                    if line.get("txn"):
                        current_row["txn_parts"].append(line["txn"])
                    if line.get("val"):
                        current_row["val_parts"].append(line["val"])
                    if line.get("nar"):
                        current_row["nar_parts"].append(line["nar"])

                    if not current_row.get("chq") and line.get("chq"):
                        current_row["chq"] = line["chq"]
                    if not current_row.get("debit") and line.get("debit"):
                        current_row["debit"] = line["debit"]
                    if not current_row.get("credit") and line.get("credit"):
                        current_row["credit"] = line["credit"]
                    if not current_row.get("bal") and line.get("bal"):
                        current_row["bal"] = line["bal"]

        flushed = _flush_row(current_row)
        if flushed:
            transactions.append(flushed)

        transactions = [t for t in transactions if t["TXN_DATE"] or t["VAL_DATE"]]
        transactions = calculate_checks(transactions)
        return transactions

    except Exception as e:
        print(f"Error processing UBA model_03 statement: {e}", file=sys.stderr)
        return []
