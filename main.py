# main.py
import os
import time
import sys
import json
import threading
from typing import TypedDict, List, Dict, Any

from dotenv import load_dotenv
load_dotenv()

from langgraph.graph import StateGraph, START, END
from neo4j import GraphDatabase

# project modules
from parse_resume import parse_resume
from parse_jobs import parse_jobs
from ollama_extractor import extract_from_resume, extract_from_job
from skill_normalizer import get_normalizer
from graph_writer import GraphWriter


# ----------- small logging helper -----------
def log(msg: str):
    print(time.strftime("%H:%M:%S"), msg)
    sys.stdout.flush()


# ----------- LangGraph state schema -----------
class State(TypedDict, total=False):
    # Inputs (optional - at least one must be provided)
    resume_path: str
    jobs_path: str  # Can be CSV or XLSX

    # Parsed
    resume_text: str  # Legacy format: single text string
    resumes: List[Dict[str, Any]]  # XLSX format: list of {"text": str, "name": str, "email": str, "domain": str}
    jobs: List[Dict[str, Any]]

    # Extracted
    resume_extraction: Dict[str, Any]          # Legacy: single candidate extraction
    resume_extractions: List[Dict[str, Any]]   # XLSX: list of candidate extractions {"name":..., "email":..., "experience":..., "education":..., "skills":[...], "domain":...}
    jobs_extractions: List[Dict[str, Any]]     # list of job extraction dicts with skills, location, experience, etc.

    # Normalized (canonical)
    canonical_resume_skills: List[str]  # Legacy: single candidate skills
    canonical_resumes_skills: List[List[str]]  # XLSX: list of skill lists, one per candidate
    canonical_jobs_skills: List[List[str]]

    # Skill normalizer instance (shared)
    skill_normalizer: Any

    # Shared cache for skill-dedup embeddings (per-run, in-memory)
    skills_cache: Dict[str, Any]               # {"vectors": {canonical: tensor}}
    skills_lock: Any                           # threading.Lock

    # Flags to track what was processed
    has_resume: bool
    has_jobs: bool

    # Output summary
    results: Dict[str, Any]


# ----------- LangGraph nodes -----------
def n_parse_resume(state: State) -> State:
    log("LG: parse_resume")
    resume_path = state.get("resume_path")
    has_resume = state.get("has_resume", False)
    
    if not has_resume or not resume_path:
        log("No resume path provided or file doesn't exist, skipping resume parsing")
        return {"resume_text": "", "resumes": [], "resume_extraction": {}, "canonical_resume_skills": []}
    
    try:
        result = parse_resume(resume_path)
        
        # Handle XLSX format (returns list) vs legacy format (returns string)
        if isinstance(result, list):
            # XLSX format with multiple resumes
            log(f"Parsed {len(result)} resume(s) from XLSX file")
            return {"resumes": result}
        else:
            # Legacy format (PDF, TXT, DOCX) - returns string
            return {"resume_text": result}
    except Exception as e:
        log(f"Error parsing resume: {e}")
        import traceback
        traceback.print_exc()
        return {"resume_text": "", "resumes": [], "resume_extraction": {}, "canonical_resume_skills": []}


def n_extract_resume(state: State) -> State:
    log("LG: extract_resume")
    has_resume = state.get("has_resume", False)
    
    if not has_resume:
        log("Skipping resume extraction - no resume flag")
        return {"resume_extraction": {}, "resume_extractions": []}
    
    # Check if we have XLSX format (list of resumes) or legacy format (single text)
    resumes = state.get("resumes", [])
    resume_text = state.get("resume_text", "")
    
    # Handle XLSX format with multiple resumes
    if resumes:
        log(f"Extracting from {len(resumes)} resume(s)")
        extractions = []
        for idx, resume_data in enumerate(resumes):
            text = resume_data.get("text", "")
            parsed_name = resume_data.get("name")
            parsed_email = resume_data.get("email")
            parsed_domain = resume_data.get("domain", "")
            
            if not text:
                log(f"  Skipping resume {idx+1}: no text content")
                continue
            
            log(f"  Extracting from resume {idx+1}/{len(resumes)} (length: {len(text)} chars)")
            try:
                # Extract skills, experience, education from text
                data = extract_from_resume(text)
                if not isinstance(data, dict):
                    log(f"  Warning: Extraction returned non-dict for resume {idx+1}, using defaults")
                    data = {"name": None, "email": None, "experience": "", "experience_years": 0, "education": "", "skills": []}
                
                data.setdefault("name", None)
                data.setdefault("email", None)
                data.setdefault("experience", "")
                data.setdefault("experience_years", 0)
                data.setdefault("education", "")
                data.setdefault("skills", [])
                
                # Use parsed name/email from XLSX if available
                if parsed_name:
                    data["name"] = parsed_name
                if parsed_email:
                    data["email"] = parsed_email
                
                # Prioritize experience from file column over LLM extraction
                parsed_experience = resume_data.get("experience", "")
                parsed_years = resume_data.get("experience_years", 0)
                extracted_experience = data.get("experience", "")
                extracted_years = data.get("experience_years", 0)
                
                # Use parsed experience from file if available, otherwise use extracted
                if parsed_experience or parsed_years > 0:
                    data["experience"] = parsed_experience
                    data["experience_years"] = parsed_years
                    log(f"  Using experience from file: '{parsed_experience[:50]}' -> {parsed_years} years")
                elif extracted_experience or extracted_years > 0:
                    data["experience"] = extracted_experience
                    data["experience_years"] = extracted_years
                    log(f"  Using experience from LLM extraction: '{extracted_experience[:50]}' -> {extracted_years} years")
                else:
                    data["experience"] = ""
                    data["experience_years"] = 0
                
                # Classify domain from resume content (validate parsed domain if provided)
                from ollama_extractor import _classify_domain
                resume_domain = _classify_domain(text, parsed_domain)
                if resume_domain in ["sales", "technology"]:
                    data["domain"] = resume_domain
                else:
                    data["domain"] = ""  # Empty if unclear
                
                log(f"  Extracted resume {idx+1}: name={data.get('name')}, email={data.get('email')}, domain={data.get('domain', '')}, skills_count={len(data.get('skills', []))}")
                extractions.append(data)
            except Exception as e:
                log(f"  Error extracting resume {idx+1}: {e}")
                # Still add with parsed data if available, but classify domain
                from ollama_extractor import _classify_domain
                resume_domain = _classify_domain(text, parsed_domain)
                if resume_domain not in ["sales", "technology"]:
                    resume_domain = ""
                # Get experience from file if available
                parsed_experience = resume_data.get("experience", "")
                parsed_years = resume_data.get("experience_years", 0)
                extractions.append({
                    "name": parsed_name,
                    "email": parsed_email,
                    "domain": resume_domain,
                    "experience": parsed_experience,
                    "experience_years": parsed_years,
                    "education": "",
                    "skills": []
                })
        
        log(f"Successfully extracted {len(extractions)} resume(s)")
        return {"resume_extractions": extractions}
    
    # Handle legacy format (single resume text)
    elif resume_text:
        log(f"Extracting from resume (length: {len(resume_text)} chars)")
        try:
            data = extract_from_resume(resume_text)
            if not isinstance(data, dict):
                log("Warning: Extraction returned non-dict, using defaults")
                data = {"name": None, "email": None, "experience": "", "education": "", "skills": []}
            data.setdefault("name", None)
            data.setdefault("email", None)
            data.setdefault("experience", "")
            data.setdefault("education", "")
            data.setdefault("skills", [])
            log(f"Extracted: name={data.get('name')}, email={data.get('email')}, skills_count={len(data.get('skills', []))}")
            return {"resume_extraction": data}
        except Exception as e:
            log(f"Error during resume extraction: {e}")
            import traceback
            traceback.print_exc()
            return {"resume_extraction": {"name": None, "email": None, "experience": "", "education": "", "skills": []}}
    else:
        log("Skipping resume extraction - no resume text or resumes")
        return {"resume_extraction": {}, "resume_extractions": []}


def n_normalize_resume(state: State) -> State:
    log("LG: normalize_resume")
    has_resume = state.get("has_resume", False)
    
    if not has_resume:
        log("Skipping resume normalization - no resume")
        return {"canonical_resume_skills": [], "canonical_resumes_skills": []}
    
    normalizer = state.get("skill_normalizer")
    
    # Handle XLSX format with multiple resumes
    resume_extractions = state.get("resume_extractions", [])
    if resume_extractions:
        log(f"Normalizing skills for {len(resume_extractions)} resume(s)")
        all_canonical_skills = []
        
        if not normalizer:
            log("Warning: No skill normalizer available, using simple cleaning")
            from skill_normalizer import _clean
            for extraction in resume_extractions:
                skills = extraction.get("skills", []) or []
                canon = [_clean(s) for s in skills if s]
                all_canonical_skills.append(canon)
        else:
            for idx, extraction in enumerate(resume_extractions):
                skills = extraction.get("skills", []) or []
                canon = []
                for s in skills:
                    if s:
                        canonical, _ = normalizer.normalize_skill(s)
                        if canonical:
                            canon.append(canonical)
                all_canonical_skills.append(canon)
                log(f"  Normalized {len(canon)} skills for resume {idx+1}")
        
        log(f"Normalized skills for {len(all_canonical_skills)} resume(s)")
        return {"canonical_resumes_skills": all_canonical_skills}
    
    # Handle legacy format (single resume)
    if not normalizer:
        log("Warning: No skill normalizer available, using simple cleaning")
        from skill_normalizer import _clean
        skills = (state.get("resume_extraction") or {}).get("skills", []) or []
        canon = [_clean(s) for s in skills if s]
    else:
        skills = (state.get("resume_extraction") or {}).get("skills", []) or []
        canon = []
        for s in skills:
            if s:
                canonical, _ = normalizer.normalize_skill(s)
                if canonical:
                    canon.append(canonical)
    return {"canonical_resume_skills": canon}


def n_parse_jobs(state: State) -> State:
    log("LG: parse_jobs")
    jobs_path = state.get("jobs_path")
    has_jobs = state.get("has_jobs", False)
    
    if not has_jobs or not jobs_path:
        log("No jobs path provided or file doesn't exist, skipping jobs parsing")
        return {"jobs": [], "jobs_extractions": [], "canonical_jobs_skills": []}
    
    try:
        jobs = parse_jobs(jobs_path)
        if not isinstance(jobs, list):
            jobs = []
        return {"jobs": jobs}
    except Exception as e:
        log(f"Error parsing jobs: {e}")
        return {"jobs": [], "jobs_extractions": [], "canonical_jobs_skills": []}


def n_extract_jobs(state: State) -> State:
    log("LG: extract_jobs")
    has_jobs = state.get("has_jobs", False)
    jobs = state.get("jobs", []) or []
    
    if not has_jobs or not jobs:
        log("Skipping job extraction - no jobs")
        return {"jobs_extractions": []}
    
    all_extractions: List[Dict[str, Any]] = []
    for job in jobs:
        j = extract_from_job(job)
        if not isinstance(j, dict):
            j = {"skills": [], "location": "", "experience": "", "experience_years": 0, "education": "", "posting_date": "", "domain": ""}
        j.setdefault("skills", [])
        j.setdefault("location", "")
        j.setdefault("experience", "")
        j.setdefault("experience_years", 0)
        j.setdefault("education", "")
        j.setdefault("posting_date", "")
        j.setdefault("domain", "")
        # Preserve original job data
        j["title"] = job.get("title", "")
        j["company"] = job.get("company", "")
        j["location"] = j.get("location") or job.get("location", "")
        # Prioritize experience from file column over LLM extraction
        parsed_experience = job.get("experience", "")
        parsed_years = job.get("experience_years", 0)
        extracted_experience = j.get("experience", "")
        extracted_years = j.get("experience_years", 0)
        
        # Use parsed experience from file if available, otherwise use extracted
        if parsed_experience or parsed_years > 0:
            j["experience"] = parsed_experience
            j["experience_years"] = parsed_years
            log(f"  Using experience from file: '{parsed_experience[:50]}' -> {parsed_years} years")
        elif extracted_experience or extracted_years > 0:
            j["experience"] = extracted_experience
            j["experience_years"] = extracted_years
            log(f"  Using experience from LLM extraction: '{extracted_experience[:50]}' -> {extracted_years} years")
        else:
            j["experience"] = ""
            j["experience_years"] = 0
        j["education"] = j.get("education") or job.get("education", "")
        j["posting_date"] = j.get("posting_date") or job.get("posting_date", "")
        # Support both domain and category for backward compatibility
        # But validate it's either "sales" or "technology"
        raw_domain = j.get("domain") or job.get("domain") or job.get("category", "")
        from ollama_extractor import _classify_domain
        job_text = f"{job.get('title', '')} {job.get('description', '')}"
        classified_domain = _classify_domain(job_text, raw_domain)
        if classified_domain in ["sales", "technology"]:
            j["domain"] = classified_domain
        else:
            j["domain"] = ""  # Empty if unclear
        all_extractions.append(j)
    return {"jobs_extractions": all_extractions}


def n_normalize_jobs(state: State) -> State:
    log("LG: normalize_jobs")
    has_jobs = state.get("has_jobs", False)
    ext = state.get("jobs_extractions", []) or []
    
    if not has_jobs or not ext:
        log("Skipping job normalization - no jobs")
        return {"canonical_jobs_skills": []}
    
    normalizer = state.get("skill_normalizer")
    out: List[List[str]] = []
    
    if not normalizer:
        log("Warning: No skill normalizer available, using simple cleaning")
        from skill_normalizer import _clean
        for job_extraction in ext:
            skills = job_extraction.get("skills", []) or []
            canon = [_clean(s) for s in skills if s]
            out.append(canon)
    else:
        for job_extraction in ext:
            skills = job_extraction.get("skills", []) or []
            canon = []
            for s in skills:
                if s:
                    canonical, _ = normalizer.normalize_skill(s)
                    if canonical:
                        canon.append(canonical)
            out.append(canon)
    
    return {"canonical_jobs_skills": out}


def n_write_graph(state: State) -> State:
    log("LG: write_graph")
    normalizer = state.get("skill_normalizer")
    writer = GraphWriter(
        uri=os.getenv("NEO4J_URI"),
        user=os.getenv("NEO4J_USER"),
        password=os.getenv("NEO4J_PASSWORD"),
        normalizer=normalizer,
    )

    results = {}
    
    # Candidates (only if resume was processed)
    has_resume = state.get("has_resume", False)
    resume_text = state.get("resume_text", "")
    resume_extractions = state.get("resume_extractions", [])
    
    log(f"Write graph: has_resume={has_resume}")
    
    candidates_added = 0
    candidates_failed = 0
    
    # Handle XLSX format with multiple resumes
    if has_resume and resume_extractions:
        canonical_resumes_skills = state.get("canonical_resumes_skills", []) or []
        log(f"Writing {len(resume_extractions)} candidate(s) to graph")
        
        for idx, cand in enumerate(resume_extractions):
            name = cand.get("name") if cand else None
            email = cand.get("email") if cand else None
            
            # Get skills for this candidate
            cskills = canonical_resumes_skills[idx] if idx < len(canonical_resumes_skills) else []
            
            # Always create an email if missing
            if not email or email == "null" or email == "":
                if name and name != "null" and name != "":
                    email = f"{name.replace(' ', '').lower()}@local"
                else:
                    # Generate unique email
                    import hashlib
                    import time
                    text_content = cand.get("text", "") or str(cand)
                    content_hash = hashlib.md5(text_content.encode()).hexdigest()[:8]
                    email = f"candidate_{content_hash}_{int(time.time())}@local"
            
            # If no name, use a default
            if not name or name == "null" or name == "":
                name = f"Unknown Candidate {idx+1}"
            
            experience_years = cand.get("experience_years", 0) if cand else 0
            education = cand.get("education", "") if cand else ""
            
            log(f"  Adding candidate {idx+1}/{len(resume_extractions)}: name='{name}', email='{email}', experience_years={experience_years}, education='{education}', skills_count={len(cskills)}")
            
            try:
                writer.merge_candidate(name, email, experience_years, education, cskills)
                candidates_added += 1
                log(f"  ✓ Successfully added candidate {idx+1}: {name} ({email})")
            except Exception as e:
                candidates_failed += 1
                log(f"  ✗ Error adding candidate {idx+1}: {e}")
                import traceback
                traceback.print_exc()
        
        results["candidates_added"] = candidates_added
        results["candidates_failed"] = candidates_failed
        results["candidates_total"] = len(resume_extractions)
    
    # Handle legacy format (single resume)
    elif has_resume and resume_text:
        cand = state.get("resume_extraction") or {}
        name = cand.get("name") if cand else None
        email = cand.get("email") if cand else None
        
        log(f"Candidate extraction: name={name}, email={email}")
        
        # Always create an email if we have a resume - use name or generate one
        if not email or email == "null" or email == "":
            if name and name != "null" and name != "":
                email = f"{name.replace(' ', '').lower()}@local"
            elif resume_text:
                # Generate a unique email based on resume content hash
                import hashlib
                content_hash = hashlib.md5(resume_text.encode()).hexdigest()[:8]
                email = f"candidate_{content_hash}@local"
                log(f"Generated email for candidate from resume content: {email}")
            else:
                # Last resort: generate email from timestamp
                import time
                email = f"candidate_{int(time.time())}@local"
                log(f"Generated email for candidate from timestamp: {email}")
        
        # If no name, use a default
        if not name or name == "null" or name == "":
            name = "Unknown Candidate"
        
        experience_years = cand.get("experience_years", 0) if cand else 0
        education = cand.get("education", "") if cand else ""
        cskills = state.get("canonical_resume_skills", []) or []
        
        log(f"Adding candidate: name='{name}', email='{email}', experience_years={experience_years}, education='{education}', skills_count={len(cskills)}")
        
        try:
            writer.merge_candidate(name, email, experience_years, education, cskills)
            results["candidate_skills"] = cskills
            results["candidate_added"] = True
            results["candidate_email"] = email
            results["candidate_name"] = name
            log(f"✓ Successfully added candidate: {name} ({email})")
        except Exception as e:
            log(f"✗ Error adding candidate: {e}")
            import traceback
            traceback.print_exc()
            results["candidate_added"] = False
            results["candidate_error"] = str(e)
            results["candidate_email"] = email
            results["candidate_name"] = name
    else:
        log(f"Skipping candidates: has_resume={has_resume}")
        results["candidate_added"] = False
        results["candidates_added"] = 0
        if not has_resume:
            results["candidate_skip_reason"] = "has_resume_flag_false"
            log("  Reason: has_resume flag is False - resume path not provided or file doesn't exist")

    # Jobs (only if jobs were processed)
    has_jobs = state.get("has_jobs", False)
    if has_jobs:
        jobs_extractions = state.get("jobs_extractions", []) or []
        jobs_written = 0
        for job_extraction in jobs_extractions:
            title = job_extraction.get("title", "")
            company = job_extraction.get("company", "")
            location = job_extraction.get("location", "")
            experience_years = job_extraction.get("experience_years", 0)
            education = job_extraction.get("education", "")
            posting_date = job_extraction.get("posting_date", "")
            domain = job_extraction.get("domain", "")
            
            # Get skills for this job - match by index
            jobs_extractions_list = state.get("jobs_extractions", [])
            canonical_jobs_skills = state.get("canonical_jobs_skills", []) or []
            idx = jobs_extractions_list.index(job_extraction) if job_extraction in jobs_extractions_list else -1
            skills = canonical_jobs_skills[idx] if 0 <= idx < len(canonical_jobs_skills) else []
            
            if title and company:
                writer.merge_job(title, company, location, experience_years, education, posting_date, domain, skills)
                jobs_written += 1
        results["jobs_written"] = jobs_written
    else:
        results["jobs_written"] = 0

    writer.close()
    return {"results": results}


# ----------- Router node to initialize flags -----------
def n_router(state: State) -> State:
    """Router node that checks what inputs are available and sets flags."""
    log("LG: router")
    resume_path = state.get("resume_path")
    jobs_path = state.get("jobs_path")
    
    has_resume = bool(resume_path and os.path.exists(resume_path))
    has_jobs = bool(jobs_path and os.path.exists(jobs_path))
    
    log(f"Router: has_resume={has_resume}, has_jobs={has_jobs}")
    
    return {
        "has_resume": has_resume,
        "has_jobs": has_jobs
    }

# ----------- Passthrough nodes for skipping -----------
def n_resume_done(state: State) -> State:
    """Passthrough node when resume processing is complete or skipped."""
    log("LG: resume_done")
    return {}

def n_jobs_done(state: State) -> State:
    """Passthrough node when jobs processing is complete or skipped."""
    log("LG: jobs_done")
    return {}

# ----------- Build the LangGraph DAG -----------
graph = StateGraph(State)

# nodes
graph.add_node("router", n_router)
graph.add_node("parse_resume", n_parse_resume)
graph.add_node("extract_resume", n_extract_resume)
graph.add_node("normalize_resume", n_normalize_resume)
graph.add_node("resume_done", n_resume_done)

graph.add_node("parse_jobs", n_parse_jobs)
graph.add_node("extract_jobs", n_extract_jobs)
graph.add_node("normalize_jobs", n_normalize_jobs)
graph.add_node("jobs_done", n_jobs_done)

graph.add_node("write_graph", n_write_graph)

# Start from router
graph.add_edge(START, "router")

# Router routes to both branches in parallel
graph.add_edge("router", "parse_resume")
graph.add_edge("router", "parse_jobs")

# Resume branch (nodes will skip internally if no resume)
graph.add_edge("parse_resume", "extract_resume")
graph.add_edge("extract_resume", "normalize_resume")
graph.add_edge("normalize_resume", "resume_done")
graph.add_edge("resume_done", "write_graph")

# Jobs branch (nodes will skip internally if no jobs)
graph.add_edge("parse_jobs", "extract_jobs")
graph.add_edge("extract_jobs", "normalize_jobs")
graph.add_edge("normalize_jobs", "jobs_done")
graph.add_edge("jobs_done", "write_graph")

# Final edge - write_graph waits for both branches
graph.add_edge("write_graph", END)

app = graph.compile()


# ----------- Entrypoint -----------
if __name__ == "__main__":
    # Get input paths from environment or command line
    resume_path = os.getenv("RESUME_PATH", "")
    jobs_path = os.getenv("JOBS_PATH", "") or os.getenv("JOBS_CSV_PATH", "")
    
    # Validate that at least one input is provided
    if not resume_path and not jobs_path:
        print("Error: At least one of RESUME_PATH or JOBS_PATH must be provided")
        print("Usage:")
        print("  RESUME_PATH=path/to/resume.pdf python main.py")
        print("  JOBS_PATH=path/to/jobs.csv python main.py")
        print("  RESUME_PATH=resume.pdf JOBS_PATH=jobs.xlsx python main.py")
        sys.exit(1)
    
    # Validate files exist if provided
    if resume_path and not os.path.exists(resume_path):
        print(f"Error: Resume file not found: {resume_path}")
        sys.exit(1)
    
    if jobs_path and not os.path.exists(jobs_path):
        print(f"Error: Jobs file not found: {jobs_path}")
        sys.exit(1)
    
    # Initialize Neo4j driver for skill normalizer
    driver = GraphDatabase.driver(
        os.getenv("NEO4J_URI"),
        auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD"))
    )
    normalizer = get_normalizer(driver)
    
    initial: State = {
        "skills_cache": {"vectors": {}},
        "skills_lock": threading.Lock(),
        "skill_normalizer": normalizer,
        "has_resume": False,
        "has_jobs": False,
    }
    
    # Add paths if provided
    if resume_path:
        initial["resume_path"] = resume_path
        print(f"Processing resume: {resume_path}")
    
    if jobs_path:
        initial["jobs_path"] = jobs_path
        print(f"Processing jobs: {jobs_path}")
    
    try:
        result = app.invoke(initial)
        print("DONE:", json.dumps(result.get("results", {}), indent=2))
    finally:
        driver.close()
