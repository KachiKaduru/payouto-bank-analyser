import pdfplumber
import re
import sys
from typing import Callable, Optional, List, Dict
from app.parsers.banks.fcmb.universal import parse as parse_universal
from app.parsers.banks.fcmb.model_01 import parse as parse_model_01
from app.parsers.banks.fcmb.model_02 import parse as parse_model_02

# Map variant keys directly to their parser functions
PARSER_MAP: Dict[str, Callable[[str], List[Dict[str, str]]]] = {
    "model_01": parse_model_01,
    "model_02": parse_model_02,
}

# Define text patterns unique to each FCMB statement variant
VARIANT_PATTERNS = {
    "model_01": [
        "statement of account",
        "start date",
        "end date",
        "txn date",
        "val date",
    ],
    "model_02": [
        "first city monument bank limited",
        "a subsidiary of fcmb group plc",
        "overdraft limit",
    ],
    # Add new variants like model_02 here when discovered
}


def detect_variant(path: str) -> Optional[Callable[[str], List[Dict[str, str]]]]:
    """
    Detect which FCMB statement variant this PDF matches, based on text patterns.
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
                        f"(fcmb_detector): Detected FCMB variant: {variant}",
                        file=sys.stderr,
                    )
                    return PARSER_MAP.get(variant, parse_universal)

            # Default fallback if no variant matched
            print(
                "(fcmb_detector): No specific variant detected, using universal parser",
                file=sys.stderr,
            )
            return parse_universal

    except Exception as e:
        print(f"(fcmb_detector): Error during detection: {e}", file=sys.stderr)
        return parse_universal
