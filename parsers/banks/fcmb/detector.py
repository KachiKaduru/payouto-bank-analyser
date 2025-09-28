import pdfplumber
import re
import sys
from typing import Callable, Optional, List, Dict
from .universal import parse as parse_universal
from .parser_001 import parse as parse_001  # Import the new parser

# Define patterns for different variants
VARIANT_PATTERNS = {
    "001": [
        "STATEMENT OF ACCOUNT",
        "STATEMENT OF ACCOUN",
        "START DATE",
        "END DATE",
        "TXN DATE",
        "VAL DATE",
    ],
    # Add more for other FCMB variants later
}


def detect_variant(path: str) -> Optional[Callable[[str], List[Dict[str, str]]]]:
    try:
        with pdfplumber.open(path) as pdf:
            if not pdf.pages:
                return None

            # Check only the first page text for patterns
            text = pdf.pages[0].extract_text() or ""
            text_lower = text.lower()

            for variant, patterns in VARIANT_PATTERNS.items():
                if all(p.lower() in text_lower for p in patterns if isinstance(p, str)):
                    print(f"Detected variant: {variant}", file=sys.stderr)
                    return globals()[f"parse_{variant}"]  # Calls parse_001, etc.

        # Default to universal if no match
        return parse_universal
    except Exception as e:
        print(f"Detector error: {e}", file=sys.stderr)
        return parse_universal
