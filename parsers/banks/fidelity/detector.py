# banks/fidelity/detector.py
import sys
import re
from typing import Callable, Optional, List, Dict, Any
import pdfplumber

from .universal import parse as parse_universal

# Variant parsers (add as you create them)
from .parser_summary import parse as parse_001  # SUMMARY-first variant

# from .parser_variant002 import parse as parse_002  # Uncomment when ready


# Variant registry:
# - patterns: list of strings and/or compiled regexes
# - min_hits: how many of the patterns must be present to trigger the variant
VARIANT_PATTERNS: Dict[str, Dict[str, Any]] = {
    "001": {
        # "patterns": [
        #     "summary",
        #     "beginning balance",
        #     "pay in",
        #     "pay out",
        #     "online banking",
        #     "ending balance",
        # ],
        # "min_hits": 3,
    },
    # "002": {
    #     "patterns": [
    #         re.compile(r"\btransaction\s+date\b", re.I),
    #         re.compile(r"\bvalue\s+date\b", re.I),
    #         # add any unique words/lines you notice for this variant
    #         "some unique header text",
    #     ],
    #     "min_hits": 2,
    # },
}

# Map variant key -> parser callable
PARSER_MAP: Dict[str, Callable[[str], List[Dict[str, str]]]] = {
    "001": parse_001,
    # "002": parse_002,
}


def _count_hits(page_text: str, patterns: List[Any]) -> int:
    t = (page_text or "").lower()
    hits = 0
    for p in patterns:
        if isinstance(p, str):
            if p.lower() in t:
                hits += 1
        elif isinstance(p, re.Pattern):
            if p.search(t):
                hits += 1
    return hits


def _match_variant_on_page(
    variant_key: str, cfg: Dict[str, Any], page_text: str
) -> bool:
    patterns = cfg.get("patterns", [])
    min_hits = int(cfg.get("min_hits", max(1, len(patterns))))
    return _count_hits(page_text, patterns) >= min_hits


def detect_variant(path: str) -> Optional[Callable[[str], List[Dict[str, str]]]]:
    try:
        with pdfplumber.open(path) as pdf:
            if not pdf.pages:
                return parse_universal

            # Check page 1, then page 2 if nothing matches (some PDFs shift content)
            texts = [
                pdf.pages[0].extract_text() or "",
                (pdf.pages[1].extract_text() or "") if len(pdf.pages) > 1 else "",
            ]

            for page_text in texts:
                if not page_text:
                    continue
                for key, cfg in VARIANT_PATTERNS.items():
                    if _match_variant_on_page(key, cfg, page_text):
                        parser = PARSER_MAP.get(key, parse_universal)
                        print(f"Detected variant: {key}", file=sys.stderr)
                        return parser

            # No variant matched → universal
            return parse_universal

    except Exception as e:
        print(f"Detector error, falling back to universal: {e}", file=sys.stderr)
        return parse_universal
