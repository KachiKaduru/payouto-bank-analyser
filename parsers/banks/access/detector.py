import sys
import re
import pdfplumber
from typing import Callable, Optional, List, Dict
from .universal import parse as parse_universal

# Import more as you add variants, e.g.:
# from .parser_001 import parse as parse_001

VARIANT_PATTERNS = {
    # Add patterns for future variants, e.g.:
    # "001": ["ACCOUNT STATEMENT", re.compile(r"Access Bank")],
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
                    print(f"Detected Access variant: {variant}", file=sys.stderr)
                    return globals()[f"parse_{variant}"]

        return parse_universal  # Default to universal if no match or no variants
    except Exception:
        return parse_universal
