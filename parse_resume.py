# parse_resume.py
import os

def _read_txt(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def _read_docx(path: str) -> str:
    from docx import Document
    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs)

def _read_pdf_with_pymupdf(path: str) -> str:
    import fitz  # PyMuPDF
    text_parts = []
    with fitz.open(path) as doc:
        for page in doc:
            text_parts.append(page.get_text("text"))
    return "\n".join(text_parts)

def _read_pdf_with_pdfminer(path: str) -> str:
    # slower fallback for odd PDFs
    from pdfminer.high_level import extract_text
    return extract_text(path)

def parse_resume(file_path: str) -> str:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Resume file not found: {file_path}")

    lower = file_path.lower()
    try:
        if lower.endswith(".pdf"):
            # Try PyMuPDF first, then pdfminer
            try:
                return _read_pdf_with_pymupdf(file_path)
            except Exception:
                return _read_pdf_with_pdfminer(file_path)

        elif lower.endswith(".txt"):
            return _read_txt(file_path)

        elif lower.endswith(".docx"):
            return _read_docx(file_path)

        else:
            raise ValueError("Unsupported resume file type. Use .pdf, .txt, or .docx")

    except Exception as e:
        raise RuntimeError(f"Failed to parse resume '{file_path}': {e}")
