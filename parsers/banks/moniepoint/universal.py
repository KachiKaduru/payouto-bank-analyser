# banks/moniepoint/universal.py
import sys
import re
from typing import List, Dict
import pdfplumber

from utils import (
    STANDARDIZED_ROW,
    normalize_date,
    clean_money,
    merge_and_drop_year_artifacts,
    calculate_checks,
)

# --- Patterns ---------------------------------------------------------------

# Find ANY triple of amounts; we will use ALL matches to segment glued rows.
MONEY3_ANY = re.compile(
    r"(\d{1,3}(?:,\d{3})*\.\d{2})\s+(\d{1,3}(?:,\d{3})*\.\d{2})\s+(\d{1,3}(?:,\d{3})*\.\d{2})"
)

# Timestamp markers
RX_PREFIX_LINE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:)$")
RX_FULL_LINE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})$")

RX_PREFIX_ANY = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:)")
RX_FULL_ANY = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})")
RX_MMSS_LINE = re.compile(r"^\d{2}:\d{2}$")
RX_MMSS_ANY = re.compile(r"(\d{2}:\d{2})(?!\d)")


# NEW: timestamp at start of line, may have trailing narration
RX_PREFIX_LEAD = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:)\s*(.*)$")
RX_FULL_LEAD = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\s*(.*)$")

# Reference tokens that often indicate row starts (expanded with PUR|)
RX_REF_TOKEN = re.compile(
    r"\b(?:AP_TRSF\|[^ \t\n]+|TRF\|[^ \t\n]+|MIT\|(?:HYD|TMP|HBP)\|[^ \t\n]+|PUR\|[^ \t\n]+)\b"
)

# --- Helpers ----------------------------------------------------------------


def _flat(buf: List[str]) -> str:
    return " ".join(s.strip() for s in buf if s and s.strip())


def _mmss_from_buf(buf: List[str]) -> tuple[str | None, List[str]]:
    """Find a MM:SS token (standalone or inline) and remove it from the buffer."""
    for i, l in enumerate(buf[:8]):
        if RX_MMSS_LINE.fullmatch(l):
            mmss = l
            return mmss, (buf[:i] + buf[i + 1 :])
        m_inline = RX_MMSS_ANY.search(l)
        if m_inline:
            mmss = m_inline.group(1)
            nl = (l[: m_inline.start()] + l[m_inline.end() :]).strip()
            nbuf = buf[:i] + ([nl] if nl else []) + buf[i + 1 :]
            return mmss, nbuf
    return None, buf


def _make_row(date_prefix: str, buf: List[str]) -> Dict[str, str] | None:
    """Create one row from the LEFTMOST triple in this buffer."""
    if not buf:
        return None
    mmss, buf2 = _mmss_from_buf(buf)
    txn_iso = date_prefix + (mmss or "00:00")
    flat = _flat(buf2)

    # Use the LEFTMOST triple to carve out one row when multiple exist.
    first = next(MONEY3_ANY.finditer(flat), None)
    if not first:
        return None

    debit_s, credit_s, balance_s = first.groups()
    narration = flat[: first.start()].strip()

    # Heuristic: last token with '|' or '_' becomes REFERENCE
    reference = ""
    for tok in narration.split():
        if "|" in tok or "_" in tok:
            reference = tok

    row = STANDARDIZED_ROW.copy()
    d = txn_iso.split("T")[0]
    row["TXN_DATE"] = normalize_date(d)
    row["VAL_DATE"] = normalize_date(d)
    row["REFERENCE"] = reference
    row["REMARKS"] = narration
    row["DEBIT"] = clean_money(debit_s)
    row["CREDIT"] = clean_money(credit_s)
    row["BALANCE"] = clean_money(balance_s)
    row["Check"] = ""
    row["Check 2"] = ""
    return row


def _drain_if_multi_triples(
    date_prefix: str, buf: List[str], out: List[Dict[str, str]]
):
    """
    If buffer has 2+ amount triples, peel rows from the LEFT, repeatedly,
    until at most one triple remains. This handles glued gray-bands.
    """
    while True:
        flat = _flat(buf)
        triples = list(MONEY3_ANY.finditer(flat))
        if len(triples) <= 1:
            return buf
        # Build a temporary buffer that contains only the segment up to the first triple,
        # plus the first triple itself – that’s one row.
        cut_end = triples[0].end()
        left_segment = flat[:cut_end]
        right_segment = flat[cut_end:].strip()

        # Re-tokenize the left into buf-l for _make_row
        left_buf = [left_segment]
        row = _make_row(date_prefix, left_buf)
        if row:
            out.append(row)

        # Continue with the remainder
        buf = [right_segment] if right_segment else []


def _split_inline_boundaries(line: str) -> List[str]:
    sent = "§§§CUT§§§"
    line = RX_FULL_ANY.sub(lambda m: sent + m.group(1), line)
    line = RX_PREFIX_ANY.sub(lambda m: sent + m.group(1), line)
    line = RX_MMSS_ANY.sub(lambda m: sent + m.group(1), line)
    return [p.strip() for p in line.split(sent) if p.strip()]


# --- Main -------------------------------------------------------------------
def parse(path: str) -> List[Dict[str, str]]:
    transactions: List[Dict[str, str]] = []

    # IMPORTANT: keep state across pages
    current_prefix = None
    buf: List[str] = []

    try:
        with pdfplumber.open(path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                print(f"(moniepoint): Processing page {page_num}", file=sys.stderr)

                raw_lines = [
                    ln
                    for ln in (page.extract_text() or "").split("\n")
                    if ln and ln.strip()
                ]
                if not raw_lines:
                    continue

                # Pre-split inline boundaries to avoid glued rows
                lines: List[str] = []
                for ln in raw_lines:
                    lines.extend(_split_inline_boundaries(ln))

                i = 0
                while i < len(lines):
                    l = lines[i].strip()

                    # --- NEW: lead timestamp handling (timestamp + trailing narration on same line)
                    m_full_lead = RX_FULL_LEAD.match(l)
                    m_pref_lead = RX_PREFIX_LEAD.match(l)

                    if m_full_lead or m_pref_lead:
                        # finalize previous row if it is complete enough
                        if (
                            current_prefix is not None
                            and buf
                            and MONEY3_ANY.search(_flat(buf))
                        ):
                            buf = (
                                _drain_if_multi_triples(
                                    current_prefix, buf, transactions
                                )
                                or buf
                            )
                            row = _make_row(current_prefix, buf)
                            if row:
                                transactions.append(row)
                            buf = []

                        if m_full_lead:
                            full = m_full_lead.group(1)
                            rest = (m_full_lead.group(2) or "").strip()
                            current_prefix = full[:-5]
                            # seed mm:ss so _make_row can reconstruct HH:MM:SS
                            buf.append(full[-5:])
                            if rest:
                                buf.append(rest)
                        else:
                            pref = m_pref_lead.group(1)
                            rest = (m_pref_lead.group(2) or "").strip()
                            current_prefix = pref
                            if rest:
                                buf.append(rest)

                        i += 1
                        continue

                    # --- existing timestamp-only lines
                    m_full_line = RX_FULL_LINE.match(l)
                    m_pref_line = RX_PREFIX_LINE.match(l)

                    is_mmss_line = RX_MMSS_LINE.match(l) is not None
                    is_mmss_any = RX_MMSS_ANY.fullmatch(l) is not None

                    # New timestamp (full or prefix) → finalize previous row (only if it looks complete)
                    if m_full_line or m_pref_line:
                        if (
                            current_prefix is not None
                            and buf
                            and MONEY3_ANY.search(_flat(buf))
                        ):
                            buf = (
                                _drain_if_multi_triples(
                                    current_prefix, buf, transactions
                                )
                                or buf
                            )
                            row = _make_row(current_prefix, buf)
                            if row:
                                transactions.append(row)
                            buf = []

                        if m_full_line:
                            full = m_full_line.group(1)
                            current_prefix = full[:-5]
                            buf.append(full[-5:])
                        else:
                            current_prefix = m_pref_line.group(1)

                        i += 1
                        continue

                    # Fresh MM:SS + existing complete row → split
                    if (is_mmss_line or is_mmss_any) and current_prefix is not None:
                        buf = (
                            _drain_if_multi_triples(current_prefix, buf, transactions)
                            or buf
                        )

                        if MONEY3_ANY.search(_flat(buf)):
                            row = _make_row(current_prefix, buf)
                            if row:
                                transactions.append(row)
                            buf = []

                        buf.append(l[-5:] if len(l) >= 5 else l)
                        i += 1
                        continue

                    # New reference token after a complete triple → split (covers PUR|…)
                    if (
                        current_prefix is not None
                        and buf
                        and MONEY3_ANY.search(_flat(buf))
                        and RX_REF_TOKEN.search(l)
                    ):
                        buf = (
                            _drain_if_multi_triples(current_prefix, buf, transactions)
                            or buf
                        )
                        row = _make_row(current_prefix, buf)
                        if row:
                            transactions.append(row)
                        buf = [l]
                        i += 1
                        continue

                    # Otherwise, keep collecting
                    if current_prefix is not None:
                        buf.append(l)
                        buf = (
                            _drain_if_multi_triples(current_prefix, buf, transactions)
                            or buf
                        )

                    i += 1

                # DO NOT force-flush page tail unless it already has a triple.
                # Otherwise this tail is probably a row that continues on next page.
                if current_prefix is not None and buf and MONEY3_ANY.search(_flat(buf)):
                    buf = (
                        _drain_if_multi_triples(current_prefix, buf, transactions)
                        or buf
                    )
                    row = _make_row(current_prefix, buf)
                    if row:
                        transactions.append(row)
                    buf = []

        # Final flush after last page (if any)
        if current_prefix is not None and buf and MONEY3_ANY.search(_flat(buf)):
            buf = _drain_if_multi_triples(current_prefix, buf, transactions) or buf
            row = _make_row(current_prefix, buf)
            if row:
                transactions.append(row)
            buf = []

        transactions = merge_and_drop_year_artifacts(transactions)
        transactions = calculate_checks(
            [t for t in transactions if t["TXN_DATE"] or t["VAL_DATE"]]
        )
        return transactions

    except Exception as e:
        print(f"Error processing Moniepoint MFB statement: {e}", file=sys.stderr)
        return []
