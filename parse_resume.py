# parse_resume.py
import os, re
from typing import List, Dict
import pandas as pd

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WEIRD_BYTES_RE = re.compile(r"[^\x09\x0A\x0D\x20-\x7E]")

def _clean_text(s: str) -> str:
    if not s: return ""
    s = s.replace("\u00A0", " ").replace("Â", " ")
    s = _WEIRD_BYTES_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _strip_html(s: str) -> str:
    if not s: return ""
    return _clean_text(_HTML_TAG_RE.sub(" ", s))

def _read_txt(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return _clean_text(f.read())

def _read_docx(path: str) -> str:
    from docx import Document
    doc = Document(path)
    return _clean_text("\n".join(p.text for p in doc.paragraphs))

def _read_pdf_with_pymupdf(path: str) -> str:
    import fitz
    parts = []
    with fitz.open(path) as doc:
        for page in doc:
            parts.append(page.get_text("text"))
    return _clean_text("\n".join(parts))

def _read_pdf_with_pdfminer(path: str) -> str:
    from pdfminer.high_level import extract_text
    return _clean_text(extract_text(path))

def parse_resume(file_path: str) -> str:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Resume file not found: {file_path}")
    lower = file_path.lower()
    try:
        if lower.endswith(".pdf"):
            try:
                return _read_pdf_with_pymupdf(file_path)
            except Exception:
                return _read_pdf_with_pdfminer(file_path)
        if lower.endswith(".txt"):  return _read_txt(file_path)
        if lower.endswith(".docx"): return _read_docx(file_path)
        raise ValueError("Unsupported file type. Use .pdf, .txt, or .docx")
    except Exception as e:
        raise RuntimeError(f"Failed to parse resume '{file_path}': {e}")