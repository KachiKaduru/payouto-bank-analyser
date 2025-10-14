import pdfplumber
import re
import sys
from typing import Callable, Optional, List, Dict
from .universal import parse as parse_universal
from .model_1 import parse as parse_model_1

# Map variant keys directly to their parser functions
PARSER_MAP: Dict[str, Callable[[str], List[Dict[str, str]]]] = {
    "001": parse_model_1,
}

# Define text patterns unique to each WEMA statement variant
VARIANT_PATTERNS = {
    "001": [
        "acct name",
        "statement period",
        "current bal:",
        "eff. avail. bal:",
    ],
    # Add more variants as needed (e.g. model_2, model_3)
}


def detect_variant(path: str) -> Optional[Callable[[str], List[Dict[str, str]]]]:
    """
    Detect which WEMA statement variant this PDF matches, based on text patterns.
    Returns the appropriate parser function.
    """
    try:
        with pdfplumber.open(path) as pdf:
            if not pdf.pages:
                return None

            # Extract text from the first page for variant detection
            text = pdf.pages[0].extract_text() or ""
            text_lower = text.lower()

            # Try to match each known variant
            for variant, patterns in VARIANT_PATTERNS.items():
                if all(
                    (isinstance(p, str) and p in text_lower)
                    or (isinstance(p, re.Pattern) and p.search(text_lower))
                    for p in patterns
                ):
                    print(
                        f"(wema_detector): Detected WEMA variant: {variant}",
                        file=sys.stderr,
                    )
                    return PARSER_MAP.get(variant, parse_universal)

            # Default fallback if no match is found
            print(
                "(wema_detector): No specific variant detected, using universal parser",
                file=sys.stderr,
            )
            return parse_universal

    except Exception as e:
        print(f"(wema_detector): Error during detection: {e}", file=sys.stderr)
        return parse_universal
