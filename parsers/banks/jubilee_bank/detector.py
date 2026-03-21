import pdfplumber
import re
import sys
from typing import Callable, Optional, List, Dict

from .universal import parse as parse_universal

# Example imports (uncomment as you add more models)
# from .model_01 import parse as parse_001
# from .model_02 import parse as parse_002

# ----------------------------
# 1. Map variant keys to parsers
# ----------------------------
PARSER_MAP: Dict[str, Callable[[str], List[Dict[str, str]]]] = {
    # "001": parse_001,
    # "002": parse_002,
}

# ----------------------------
# 2. Variant detection patterns
# ----------------------------
VARIANT_PATTERNS = {
    # Example structure
    # "001": ["Transaction details", "Value Date", "Transaction description"],
    # "002": ["Statement from:", "Stanbic IBTC Bank", "Transaction date"],
}


# ----------------------------
# 3. Detector function
# ----------------------------
def detect_variant(path: str) -> Optional[Callable[[str], List[Dict[str, str]]]]:
    """
    Detects which Stanbic statement variant to use based on text patterns.
    Returns the matching parser function or defaults to `parse_universal`.
    """
    try:
        with pdfplumber.open(path) as pdf:
            if not pdf.pages:
                return None

            # Extract text from first page
            text = pdf.pages[0].extract_text() or ""
            text_lower = text.lower()

            for variant, patterns in VARIANT_PATTERNS.items():
                if all(
                    (isinstance(p, str) and p.lower() in text_lower)
                    or (isinstance(p, re.Pattern) and p.search(text_lower))
                    for p in patterns
                ):
                    print(
                        f"(jubilee_bank_detector): Detected variant: {variant}",
                        file=sys.stderr,
                    )
                    return PARSER_MAP.get(variant, parse_universal)

        # Default to universal if nothing matched
        return parse_universal

    except Exception as e:
        print(f"(jubilee_bank_detector): Error during detection: {e}", file=sys.stderr)
        return parse_universal
