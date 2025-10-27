# parse_jobs.py
import re
import pandas as pd
import os # Import os for path checking

# Flexible header mapping (rest of COLMAP remains the same)
COLMAP = {
    "job_id": "job_id", "id": "job_id",
    "title": "title", "Title": "title",
    "company_name": "company", "Company": "company", "company": "company",
    "description": "description", "Description": "description",
    "location": "location", "Location": "location",
    "skills_desc": "skills", "skills": "skills", "Skills": "skills",
}

_SKILL_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z\+\#\.\-\s]{0,40}[A-Za-z0-9]")

def _split_skills(val):
    # ... (rest of _split_skills function remains the same)
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    if not s:
        return None
    parts = [p.strip() for p in re.split(r"[;,]", s) if p.strip()]
    if len(parts) <= 1 and len(s) > 120:
        parts = [m.group(0).strip() for m in _SKILL_TOKEN_RE.finditer(s)]
    seen, out = set(), []
    for p in parts:
        k = p.lower()
        if k not in seen:
            seen.add(k); out.append(p)
    return out or None

# --- MODIFIED FUNCTION ---
def parse_jobs(file_path: str): # Renamed csv_path to file_path
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.csv':
        df = pd.read_csv(file_path, low_memory=False)
    elif ext in ('.xlsx', '.xls'):
        # Use read_excel for .xlsx files
        df = pd.read_excel(file_path) 
    else:
        raise ValueError("Unsupported file type for job parsing. Use .csv or .xlsx")
        
    # ... (rest of the function remains the same)
    nd = {}
    for src, dst in COLMAP.items():
        if src in df.columns:
            nd.setdefault(dst, df[src])
    ndf = pd.DataFrame(nd)
    if "job_id" not in ndf:
      ndf["job_id"] = ndf.index.astype(str)
    if "title" not in ndf:
       ndf["title"] = "Unknown"
    if "company" not in ndf:
     ndf["company"] = "Unknown"
    if "description" not in ndf:  ndf["description"] = ""
    if "location" not in ndf:     ndf["location"] = ""

    if "skills" in ndf:
        ndf["skills"] = ndf["skills"].apply(_split_skills)

    jobs = []
    for _, r in ndf.iterrows():
        jobs.append({
            "job_id": str(r["job_id"]),
            "title": str(r["title"]) if pd.notna(r["title"]) else "Unknown",
            "company": str(r["company"]) if pd.notna(r["company"]) else "Unknown",
            "description": str(r["description"]) if pd.notna(r["description"]) else "",
            "location": str(r["location"]) if pd.notna(r["location"]) else "",
            # may be None → LLM will fill; if present, it’s a list of strings
            "skills": (list(r["skills"]) if "skills" in ndf and isinstance(r["skills"], list) else None),
        })
    return jobs