# graph_state.py
from typing import Dict, List, Any, Optional, Set, Tuple

# We'll keep it simple: a dict-based state. LangGraph accepts plain dicts.
# Keys:
# - resume_path: str
# - jobs_csv_path: str
# - resume_text: str
# - resume_extraction: dict {name, email, skills: []}
# - jobs: List[dict] (parsed rows)
# - jobs_extractions: List[List[str]] (list of skill lists per job)
# - canonical_resume_skills: List[str]
# - canonical_jobs_skills: List[List[str]]
# - skills_cache: Dict[str, Any]  (local cache for embeddings/vectors)
# - results: Dict[str, Any]
