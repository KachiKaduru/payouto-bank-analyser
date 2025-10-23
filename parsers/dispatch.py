import sys
import json
import argparse
import os
from typing import List, Dict, Callable, Any
import importlib

from validator import is_valid_parse
from main_parser import main_parse
from utils import decrypt_pdf
from main_metadata import extract_metadata, verify_legitimacy


def dispatch_parse(pdf_path: str, bank: str, password: str = "") -> Dict[str, Any]:
    """
    Parses a statement PDF using bank-specific or universal parsers.\n
    Returns a single payload:\n
    {\n
      "meta": Dict[str, Any],\n
      "transactions": List[Dict[str, str]],\n
      "checks": List[Dict[str, Any]]\n
    }
    """
    if not bank:
        raise ValueError("Bank must be specified via --bank.")

    temp_file_path = None
    effective_path = pdf_path
    transactions: List[Dict[str, str]] = []

    try:
        # Decrypt if necessary (your utils returns (temp_path, effective_path))
        temp_file_path, effective_path = decrypt_pdf(pdf_path, password)

        # Prefer bank-specific parser via detector → universal
        try:
            bank_module_path = f"banks.{bank.replace('-', '_')}"
            detector_module = importlib.import_module(f"{bank_module_path}.detector")
            detect_variant = getattr(detector_module, "detect_variant")
        except (ImportError, AttributeError):
            print(
                f"No specific parsers for bank, '{bank}' (dispatch.py)",
                file=sys.stderr,
            )
            detect_variant = None

        parser_func: Callable[[str], List[Dict[str, str]]] | None = None
        if detect_variant:
            parser_func = detect_variant(effective_path)

        if parser_func is None and detect_variant is not None:
            # fall back to bank universal if detector could not resolve a variant
            try:
                universal_module = importlib.import_module(
                    f"{bank_module_path}.universal"
                )
                parser_func = getattr(universal_module, "parse")
            except (ImportError, AttributeError):
                parser_func = None

        # Try chosen bank parser first
        if parser_func:
            try:
                result = parser_func(effective_path)
                if is_valid_parse(result):
                    print(
                        f"Success with {bank} parser: {parser_func.__module__}",
                        file=sys.stderr,
                    )
                    transactions = result
                else:
                    print(
                        f"{bank} parser returned invalid parse; falling back to main parser",
                        file=sys.stderr,
                    )
            except Exception as e:
                print(f"Failed {bank} parser: {e}", file=sys.stderr)

        # If still empty/invalid, use global fallback
        if not transactions:
            result = main_parse(effective_path)
            if is_valid_parse(result):
                print("Success with main parser", file=sys.stderr)
                transactions = result

        # If nothing worked, error out as before
        if not transactions:
            raise ValueError(
                "No suitable parser found for this statement. Please check the PDF or add a new variant. (dispatch.py)"
            )

        # === New bits: metadata + legitimacy checks ===
        meta = extract_metadata(effective_path)
        checks = verify_legitimacy(meta, transactions, meta.get("raw_header"))

        # Overall parse quality (kept from your original flow)
        checks.append(
            {
                "id": "parse_quality_gate",
                "ok": is_valid_parse(transactions),
                "severity": "good" if is_valid_parse(transactions) else "fail",
                "message": "Overall parse quality threshold (table detection/normalization).",
            }
        )

        return {
            "meta": meta,
            "transactions": transactions,
            "checks": checks,
        }

    finally:
        # Clean up temporary file if it was created
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
                print(f"Cleaned up temporary file: {temp_file_path}", file=sys.stderr)
            except Exception as e:
                print(f"Failed to delete temp file: {e}", file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_path", help="Path to the PDF file")
    parser.add_argument(
        "--bank", help="Bank name (e.g., zenith, first-bank)", default=None
    )
    parser.add_argument("--password", help="Password for encrypted PDF", default=None)
    args = parser.parse_args()

    try:
        result = dispatch_parse(args.pdf_path, args.bank, args.password)
        print(json.dumps(result, indent=2))
    except ValueError as ve:
        print(f"Error: {ve}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)
