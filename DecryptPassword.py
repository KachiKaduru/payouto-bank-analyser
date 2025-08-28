from PyPDF2 import PdfReader, PdfWriter
import pikepdf

def decrypt_pdf(input_path, password, output_path="decrypted_statement.pdf"):
    """
    Decrypt a password-protected PDF.
    1. Try PyPDF2 first (fast, works for simple encryption).
    2. If PyPDF2 fails, fallback to pikepdf (handles stronger encryption).
    
    Returns the path to the decrypted PDF if successful, else None.
    """
    # ---- Try PyPDF2 ----
    try:
        reader = PdfReader(input_path)
        if reader.is_encrypted:
            result = reader.decrypt(password)
            if result:  # Success (1 or True)
                writer = PdfWriter()
                for page in reader.pages:
                    writer.add_page(page)
                with open(output_path, "wb") as f:
                    writer.write(f)
                print("✅ Decrypted successfully with PyPDF2")
                return output_path
            else:
                print("⚠️  PyPDF2 failed, trying pikepdf...")
        else:
            print("ℹ️  PDF is not encrypted")
            return input_path
    except Exception as e:
        print(f"⚠️  PyPDF2 error: {e} → trying pikepdf...")

    # ---- Fallback: pikepdf ----
    try:
        with pikepdf.open(input_path, password=password) as pdf:
            pdf.save(output_path)
        print("✅ Decrypted successfully with pikepdf")
        return output_path
    except Exception as e:
        print(f"❌ Both PyPDF2 and pikepdf failed: {e}")
        return None