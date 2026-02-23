import pdfplumber
import re
import sys
from typing import Callable, Optional, List, Dict
from .universal import parse as parse_universal
from .model_01 import parse as parse_001
from .model_02 import parse as parse_002

# Map variant keys directly to their parser functions
PARSER_MAP: Dict[str, Callable[[str], List[Dict[str, str]]]] = {
    "001": parse_001,
    "002": parse_002,
}

VARIANT_PATTERNS = {
    "001": [
        "Here is your Account Summary",
        re.compile(r"Account Summary", re.IGNORECASE),
    ],
    "002": ["Account Statement", "Your Transactions"],
    # Add more patterns for other variants if needed
}


def detect_variant(path: str) -> Optional[Callable[[str], List[Dict[str, str]]]]:
    try:
        with pdfplumber.open(path) as pdf:
            if not pdf.pages:
                return None

            # Look at the first page text only
            text = pdf.pages[0].extract_text() or ""
            text_lower = text.lower()

            for variant, patterns in VARIANT_PATTERNS.items():
                if all(
                    (isinstance(p, str) and p.lower() in text_lower)
                    or (isinstance(p, re.Pattern) and p.search(text_lower))
                    for p in patterns
                ):
                    print(f"Detected variant: {variant}", file=sys.stderr)
                    return PARSER_MAP.get(variant, parse_universal)

        # Default to universal if nothing matched
        return parse_universal

    except Exception as e:
        print(f"(uba detector): Error during detection: {e}", file=sys.stderr)
        return parse_universal
