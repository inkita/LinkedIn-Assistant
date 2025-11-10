import pandas as pd
import os

def parse_jobs(file_path):
    """Parse jobs from CSV or XLSX file.
    
    Expected columns for XLSX:
    - job_id
    - company_name
    - title
    - description (used for extracting skills, experience, education)
    - location
    - posted_date
    
    Also supports legacy CSV format with: Title, Company, Description, etc.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Jobs file not found: {file_path}")
    
    file_lower = file_path.lower()
    
    # Read CSV or XLSX
    if file_lower.endswith('.xlsx') or file_lower.endswith('.xls'):
        try:
            df = pd.read_excel(file_path)
        except ImportError:
            raise ImportError(
                "openpyxl is required for reading Excel files. "
                "Install it with: pip install openpyxl"
            )
    elif file_lower.endswith('.csv'):
        df = pd.read_csv(file_path)
    else:
        raise ValueError(f"Unsupported file format. Use .csv, .xlsx, or .xls")
    
    jobs = []
    for _, row in df.iterrows():
        # Support new XLSX format first
        if "company_name" in df.columns:
            job = {
                "title": str(row.get("title", "")).strip(),
                "company": str(row.get("company_name", "")).strip(),
                "description": str(row.get("description", "")).strip(),
                "location": str(row.get("location", "")).strip() if "location" in df.columns else "",
                "posting_date": str(row.get("posted_date", "")).strip() if "posted_date" in df.columns else ""
            }
        else:
            # Legacy CSV format support
            job = {
                "title": str(row.get("Title", "")).strip(),
                "company": str(row.get("Company", "")).strip(),
                "description": str(row.get("Description", "")).strip()
            }
            # Optional fields (use if present in file)
            if "Location" in df.columns:
                job["location"] = str(row.get("Location", "")).strip()
            if "Experience" in df.columns:
                job["experience"] = str(row.get("Experience", "")).strip()
            if "Education" in df.columns:
                job["education"] = str(row.get("Education", "")).strip()
            if "Posting Date" in df.columns or "PostingDate" in df.columns:
                job["posting_date"] = str(row.get("Posting Date") or row.get("PostingDate", "")).strip()
            if "Domain" in df.columns or "Category" in df.columns:
                # Support both Domain and Category for backward compatibility
                job["domain"] = str(row.get("Domain") or row.get("Category", "")).strip()
        
        jobs.append(job)
    return jobs
