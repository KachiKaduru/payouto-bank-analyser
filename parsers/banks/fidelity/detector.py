import pdfplumber
import re
import sys
from typing import Callable, Optional, List, Dict
from .universal import parse as parse_universal

# Import more as you add variants, e.g.:
# from .parser_001 import parse as parse_001

# Bank-level pattern to confirm it's a Fidelity statement
BANK_PATTERN = ["fidelitybank.ng", re.compile(r"fidelity\s+bank", re.IGNORECASE)]

VARIANT_PATTERNS = {
    # Add variant-specific patterns here, e.g.:
    # "001": ["personal account", re.compile(r"transaction\s+date")],
}


def detect_variant(path: str) -> Optional[Callable[[str], List[Dict[str, str]]]]:
    try:
        with pdfplumber.open(path) as pdf:
            if not pdf.pages:
                return None

            # Extract first page text for matching
            first_page_text = pdf.pages[0].extract_text() or ""
            first_page_text_lower = first_page_text.lower()

            # Check if it's a Fidelity bank statement
            if all(
                (isinstance(p, str) and p.lower() in first_page_text_lower)
                or (isinstance(p, re.Pattern) and p.search(first_page_text_lower))
                for p in BANK_PATTERN
            ):
                print("[INFO] Confirmed Fidelity bank statement", file=sys.stderr)
            else:
                print(
                    "[WARN] Not a Fidelity statement, defaulting to universal",
                    file=sys.stderr,
                )
                return parse_universal

            # Check for variants
            for variant, patterns in VARIANT_PATTERNS.items():
                if all(
                    (isinstance(p, str) and p.lower() in first_page_text_lower)
                    or (isinstance(p, re.Pattern) and p.search(first_page_text_lower))
                    for p in patterns
                ):
                    print(
                        f"[INFO] Detected Fidelity variant: {variant}", file=sys.stderr
                    )
                    # Return variant-specific parser, e.g., return parse_001
                    return parse_universal  # For now, use universal

        return parse_universal  # Fallback if nothing matched
    except Exception as e:
        print(f"[WARN] Detector error, defaulting to universal: {e}", file=sys.stderr)
        return parse_universal
