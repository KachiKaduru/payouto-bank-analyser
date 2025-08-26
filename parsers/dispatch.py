import sys
import json
import argparse
import os
import tempfile
from typing import List, Dict, Callable
import importlib
import pikepdf
from PyPDF2 import PdfReader, PdfWriter
from validator import is_valid_parse
from main_parser import main_parse
from utils import decrypt_pdf


def dispatch_parse(
    pdf_path: str, bank: str = None, password: str = None
) -> List[Dict[str, str]]:
    if not bank:
        raise ValueError("Bank must be specified via --bank.")

    # Determine the path to use (original or decrypted temp file)
    effective_path = pdf_path
    temp_file_path = None

    try:
        # Check if PDF is encrypted and decrypt if necessary
        reader = PdfReader(pdf_path)
        if reader.is_encrypted:
            if not password:
                raise ValueError("Encrypted PDF detected. Please provide a password.")
            reader.decrypt(password)
            print("PDF decrypted successfully.")
            # Create a temporary file for the decrypted PDF
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
                writer = PdfWriter()
                for page in reader.pages:
                    writer.add_page(page)
                writer.write(temp_file)
                temp_file_path = temp_file.name
                effective_path = temp_file_path
        else:
            print("PDF is not encrypted.")

        # temp_file_path = decrypt_pdf(pdf_path, password)
        # if temp_file_path:
        #     effective_path = temp_file_path
        # elif temp_file_path is None:
        #     raise ValueError("Failed to decrypt PDF with provided password.")

        # Proceed with parsing using the effective path
        try:
            bank_module_path = f"parsers.banks.{bank.replace('-', '_')}"
            detector_module = importlib.import_module(f"{bank_module_path}.detector")
            detector = detector_module.detect_variant
        except (ImportError, AttributeError):
            print(
                f"No specific parsers for bank '{bank}', using main parser",
                file=sys.stderr,
            )
            result = main_parse(effective_path)
            if is_valid_parse(result):
                return result
            raise ValueError(f"No suitable parser for {bank} statement.")

        parser_func: Callable[[str], List[Dict[str, str]]] = detector(effective_path)
        if not parser_func:
            universal_module = importlib.import_module(f"{bank_module_path}.universal")
            parser_func = universal_module.parse

        try:
            result = parser_func(effective_path)
            if is_valid_parse(result):
                print(
                    f"Success with {bank} parser: {parser_func.__module__}",
                    file=sys.stderr,
                )
                return result
        except Exception as e:
            print(f"Failed {bank} parser: {e}", file=sys.stderr)

        # Global fallback
        result = main_parse(effective_path)
        if is_valid_parse(result):
            print("Success with main parser", file=sys.stderr)
            return result

        raise ValueError(
            "No suitable parser found for this statement. Please check the PDF or add a new variant."
        )

    finally:
        # Clean up temporary file if it was created
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
            print(f"Cleaned up temporary file: {temp_file_path}")


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
