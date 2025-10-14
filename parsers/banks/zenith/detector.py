import pdfplumber
import re
import sys
from typing import Callable, Optional, List, Dict
from .universal import parse as parse_universal
from .model_01 import parse as parse_model_01  # Updated name

# Map variant keys directly to their parser functions
PARSER_MAP: Dict[str, Callable[[str], List[Dict[str, str]]]] = {
    "model_01": parse_model_01,
}

# Define text patterns unique to each Zenith statement variant
VARIANT_PATTERNS = {
    "model_01": [
        "date posted",
        "value date",
        "description",
        "debit",
        "credit",
        "balance",
    ],
    # Add new variants (e.g. model_02) as needed
}


def detect_variant(path: str) -> Optional[Callable[[str], List[Dict[str, str]]]]:
    """
    Detect which Zenith Bank statement variant this PDF matches, based on text patterns.
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
                        f"(zenith_detector): Detected Zenith variant: {variant}",
                        file=sys.stderr,
                    )
                    return PARSER_MAP.get(variant, parse_universal)

            # Default fallback if no variant matched
            print(
                "(zenith_detector): No specific variant detected, using universal parser",
                file=sys.stderr,
            )
            return parse_universal

    except Exception as e:
        print(f"(zenith_detector): Error during detection: {e}", file=sys.stderr)
        return parse_universal
