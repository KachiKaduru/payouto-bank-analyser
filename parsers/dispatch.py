import sys
import json
import argparse
from typing import List, Dict, Callable
import importlib

from validator import is_valid_parse
from main_parser import main_parse


def dispatch_parse(path: str, bank: str = None) -> List[Dict[str, str]]:
    if not bank:
        raise ValueError("Bank must be specified via --bank.")

    try:
        bank_module_path = f"parsers.banks.{bank.replace('-', '_')}"  # Handle hyphens (e.g., first-bank -> first_bank)
        detector_module = importlib.import_module(f"{bank_module_path}.detector")
        detector = detector_module.detect_variant
    except (ImportError, AttributeError):
        print(
            f"No specific parsers for bank '{bank}', using main parser", file=sys.stderr
        )
        result = main_parse(path)
        if is_valid_parse(result):
            return result
        raise ValueError(f"No suitable parser for {bank} statement. (dispatch.py)")

    parser_func: Callable[[str], List[Dict[str, str]]] = detector(path)
    if not parser_func:
        universal_module = importlib.import_module(f"{bank_module_path}.universal")
        parser_func = universal_module.parse

    try:
        result = parser_func(path)
        if is_valid_parse(result):
            print(
                f"Success with {bank} parser: {parser_func.__module__}", file=sys.stderr
            )
            return result
    except Exception as e:
        print(f"Failed {bank} parser: {e}", file=sys.stderr)

    # Global fallback
    result = main_parse(path)
    if is_valid_parse(result):
        print("Success with main parser", file=sys.stderr)
        return result

    raise ValueError(
        "No suitable parser found for this statement. Please check the PDF or add a new variant."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_path", help="Path to the PDF file")
    parser.add_argument(
        "--bank", help="Bank name (e.g., zenith, first-bank)", default=None
    )
    args = parser.parse_args()

    try:
        result = dispatch_parse(args.pdf_path, args.bank)
        print(json.dumps(result, indent=2))
    except ValueError as ve:
        print(f"Error: {ve}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)
