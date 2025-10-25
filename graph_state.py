# graph_state.py
from typing import Dict, List, Any

# LangGraph accepts plain dict state. We keep the keys documented here.
# Keys:
# - resume_path: str            # path to one resume file (txt/pdf/docx) for smoke tests
# - resume_csv_path: str        # (optional) bulk Kaggle resumes CSV path
# - jobs_csv_path: str          # LinkedIn postings CSV path
#
# - resume_text: str
# - jobs: List[dict]            # parsed job rows
#
# - resume_extraction: dict     # {"name": str|None, "email": str|None, "skills": List[str]}
# - jobs_extractions: List[List[str]]   # each item: skills list for matching job in `jobs`
#
# - canonical_resume_skills: List[str]
# - canonical_jobs_skills: List[List[str]]
#
# - results: Dict[str, Any]     # summary/stats
