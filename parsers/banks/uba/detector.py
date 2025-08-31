import pdfplumber
import re
import sys
from typing import Callable, Optional, List, Dict
from .universal import parse as parse_universal
from .parser_001 import parse as parse_001  # Import the new parser

VARIANT_PATTERNS = {
    "001": [
        "Here is your Account Summary",
        re.compile(r"Account Summary", re.IGNORECASE),
    ],
    # Add more variants as needed, e.g., "002" for other formats
}


def detect_variant(path: str) -> Optional[Callable[[str], List[Dict[str, str]]]]:
    try:
        with pdfplumber.open(path) as pdf:
            if not pdf.pages:
                return None
            text = pdf.pages[0].extract_text() or ""  # Check first page
            text_lower = text.lower()

            for variant, patterns in VARIANT_PATTERNS.items():
                if all(
                    (isinstance(p, str) and p.lower() in text_lower)
                    or (isinstance(p, re.Pattern) and p.search(text_lower))
                    for p in patterns
                ):
                    print(f"Detected variant: {variant}", file=sys.stderr)
                    return globals()[f"parse_{variant}"]  # e.g., parse_001

        return parse_universal  # Default to universal if no match
    except Exception:
        return parse_universal
