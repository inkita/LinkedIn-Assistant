# parse_resume.py
import os
import pandas as pd

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

def _extract_text_from_html(html_content: str) -> str:
    """Extract plain text from HTML content, ignoring formatting."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        # Get text and clean it up
        text = soup.get_text(separator='\n', strip=True)
        # Remove extra whitespace
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        return '\n'.join(lines)
    except ImportError:
        # Fallback: simple regex-based HTML tag removal if BeautifulSoup not available
        import re
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', html_content)
        # Decode HTML entities
        text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
        # Clean up whitespace
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        return '\n'.join(lines)

def parse_resume(file_path: str):
    """
    Parse resume from file.
    
    For XLSX files, expects columns:
    - ID
    - Resume_sthesume_html (or Resume_html, or similar) - HTML content
    - Category - domain
    - Name
    - Email
    
    Returns list of dicts for XLSX: [{"text": str, "name": str, "email": str, "domain": str}, ...]
    For non-XLSX files, returns just the text as string (backward compatibility).
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Resume file not found: {file_path}")

    lower = file_path.lower()
    
    # Handle XLSX files with structured data
    if lower.endswith('.xlsx') or lower.endswith('.xls'):
        try:
            df = pd.read_excel(file_path)
        except ImportError:
            raise ImportError(
                "openpyxl is required for reading Excel files. "
                "Install it with: pip install openpyxl"
            )
        
        # Find the HTML column (could be named various ways)
        html_col = None
        for col in df.columns:
            col_lower = str(col).lower()
            if 'resume' in col_lower and ('html' in col_lower or 'content' in col_lower):
                html_col = col
                break
        
        if html_col is None:
            raise ValueError(f"Could not find resume HTML column in XLSX file. Expected column containing 'resume' and 'html'")
        
        # Process all rows in the XLSX file
        resumes = []
        for idx, row in df.iterrows():
            html_content = str(row.get(html_col, ""))
            if not html_content or html_content.lower() == "nan":
                continue  # Skip empty rows
            
            text = _extract_text_from_html(html_content)
            
            # Get other fields
            name = str(row.get("Name", "")).strip() if "Name" in df.columns else None
            email = str(row.get("Email", "")).strip() if "Email" in df.columns else None
            domain = str(row.get("Category", "")).strip() if "Category" in df.columns else ""
            
            # Skip if no text content
            if not text or len(text.strip()) < 10:
                continue
            
            resumes.append({
                "text": text,
                "name": name,
                "email": email,
                "domain": domain
            })
        
        if not resumes:
            raise ValueError("No valid resumes found in XLSX file")
        
        return resumes
    
    # Handle legacy file formats (PDF, TXT, DOCX)
    try:
        if lower.endswith(".pdf"):
            # Try PyMuPDF first, then pdfminer
            try:
                text = _read_pdf_with_pymupdf(file_path)
            except Exception:
                text = _read_pdf_with_pdfminer(file_path)
            return text

        elif lower.endswith(".txt"):
            return _read_txt(file_path)

        elif lower.endswith(".docx"):
            return _read_docx(file_path)

        else:
            raise ValueError("Unsupported resume file type. Use .pdf, .txt, .docx, or .xlsx")

    except Exception as e:
        raise RuntimeError(f"Failed to parse resume '{file_path}': {e}")
