"""
FastAPI service wrapper for KG Builder
Run with: uvicorn service:api_app --host 0.0.0.0 --port 8000

This service accepts only XLSX files for both resumes and jobs.
"""
import os
import tempfile
import shutil
from pathlib import Path
from typing import Optional, List
from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn


def validate_xlsx_file(filename: str) -> None:
    """Validate that the file is an XLSX file."""
    if not filename:
        raise HTTPException(
            status_code=400,
            detail="File must have a filename"
        )
    
    ext = Path(filename).suffix.lower()
    valid_extensions = ['.xlsx', '.xls']
    
    if ext not in valid_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Only XLSX files are accepted. Got: {ext}. Valid extensions: {valid_extensions}"
        )

from dotenv import load_dotenv
load_dotenv()

from neo4j import GraphDatabase
from main import app as langgraph_app, log, State
from graph_writer import GraphWriter
from ollama_extractor import _extract_years_of_experience, _normalize_education, extract_from_resume, extract_from_job, _classify_domain

# Initialize FastAPI app
api_app = FastAPI(title="KG Builder API", version="1.0.0")

# Global Neo4j driver and normalizer (initialized at startup)
driver = None
normalizer = None


@api_app.on_event("startup")
async def startup_event():
    """Initialize Neo4j connection and skill normalizer on startup."""
    global driver, normalizer
    try:
        from skill_normalizer import get_normalizer
        
        driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI"),
            auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD"))
        )
        normalizer = get_normalizer(driver)
        log("Service started: Neo4j connection established")
    except Exception as e:
        log(f"Error initializing service: {e}")
        raise


@api_app.on_event("shutdown")
async def shutdown_event():
    """Close Neo4j connection on shutdown."""
    global driver
    if driver:
        driver.close()
        log("Service stopped: Neo4j connection closed")


@api_app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "service": "KG Builder API",
        "status": "running",
        "version": "1.0.0"
    }


@api_app.get("/health")
async def health():
    """Health check endpoint."""
    global driver
    if driver:
        try:
            with driver.session() as session:
                session.run("RETURN 1")
            return {"status": "healthy", "neo4j": "connected"}
        except Exception as e:
            return {"status": "unhealthy", "neo4j": f"error: {str(e)}"}
    return {"status": "unhealthy", "neo4j": "not initialized"}


class ProcessResponse(BaseModel):
    """Response model for process endpoints."""
    success: bool
    results: dict
    message: Optional[str] = None


class CandidateInput(BaseModel):
    """Input model for candidate JSON endpoint - matches resume XLSX format."""
    name: Optional[str] = None  # Name column
    email: str  # Email column (required)
    text: Optional[str] = ""  # Resume_sthesume_html or resume text content
    experience: Optional[str] = ""  # Experience column - can be "3 years", "5+ years", or direct number
    experience_years: Optional[int] = None  # Direct years as integer (takes priority)
    education: Optional[str] = ""  # Education column - will be normalized to bachelor's, master's, or phd
    category: Optional[str] = ""  # Category column - domain (sales or technology)
    skills: Optional[List[str]] = []  # Skills (optional, will be extracted from text if not provided)


class CandidateResponse(BaseModel):
    """Response model for candidate creation endpoint."""
    success: bool
    candidate_id: Optional[str] = None
    message: Optional[str] = None


class JobInput(BaseModel):
    """Input model for job JSON endpoint - matches jobs XLSX format."""
    title: str  # title column (required)
    company_name: str  # company_name column (required)
    description: str  # description column (required, used for extraction)
    location: Optional[str] = ""  # location column
    posted_date: Optional[str] = ""  # posted_date column
    experience: Optional[str] = ""  # experience column - can be "3 years", "5+ years", or direct number
    experience_years: Optional[int] = None  # Direct years as integer (takes priority)
    education: Optional[str] = ""  # education column - will be normalized
    category: Optional[str] = ""  # category/domain column (sales or technology)
    domain: Optional[str] = ""  # domain column (sales or technology) - alias for category


class JobResponse(BaseModel):
    """Response model for job creation endpoint."""
    success: bool
    job_id: Optional[str] = None
    message: Optional[str] = None


@api_app.post("/process/resume", response_model=ProcessResponse)
async def process_resume(
    file: UploadFile = File(...),
    resume_path: Optional[str] = Form(None)
):
    """
    Process a resume XLSX file and add candidate(s) to knowledge graph.
    
    **Accepts only XLSX files** (.xlsx or .xls)
    
    The XLSX file should contain columns:
    - `ID` - Unique identifier
    - `Resume_sthesume_html` (or column containing "resume" and "html") - HTML content of resume
    - `Category` - Domain/category for the candidate (optional)
    - `Name` - Candidate name (optional, will be extracted if missing)
    - `Email` - Candidate email (optional, will be extracted if missing)
    """
    global normalizer
    
    # Validate file extension
    if not resume_path:
        if not file.filename:
            raise HTTPException(status_code=400, detail="File must have a filename")
        validate_xlsx_file(file.filename)
    
    # Use provided path or save uploaded file to temp location
    temp_file_path = None
    try:
        if resume_path and os.path.exists(resume_path):
            # Validate path extension
            if not resume_path.lower().endswith(('.xlsx', '.xls')):
                raise HTTPException(
                    status_code=400,
                    detail="Only XLSX files are accepted for resume_path"
                )
            file_path = resume_path
        else:
            # Save uploaded file to temporary location
            suffix = Path(file.filename).suffix.lower() if file.filename else ".xlsx"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                shutil.copyfileobj(file.file, tmp)
                temp_file_path = tmp.name
            file_path = temp_file_path
        
        # Prepare initial state
        initial: State = {
            "resume_path": file_path,
            "skills_cache": {"vectors": {}},
            "skills_lock": __import__("threading").Lock(),
            "skill_normalizer": normalizer,
            "has_resume": True,
            "has_jobs": False,
        }
        
        # Process resume
        result = langgraph_app.invoke(initial)
        
        return ProcessResponse(
            success=True,
            results=result.get("results", {}),
            message=f"Resume processed successfully"
        )
        
    except Exception as e:
        log(f"Error processing resume: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Clean up temp file
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)


@api_app.post("/process/jobs", response_model=ProcessResponse)
async def process_jobs(
    file: UploadFile = File(...),
    jobs_path: Optional[str] = Form(None)
):
    """
    Process a jobs XLSX file and add jobs to knowledge graph.
    
    **Accepts only XLSX files** (.xlsx or .xls)
    
    The XLSX file should contain columns:
    - `job_id` - Unique identifier
    - `company_name` - Company name
    - `title` - Job title
    - `description` - Job description (used for extracting skills, experience, education)
    - `location` - Job location (optional)
    - `posted_date` - Posting date (optional)
    - `category` or `domain` - Job domain/category (optional, will be classified if missing)
    """
    global normalizer
    
    # Validate file extension
    if not jobs_path:
        if not file.filename:
            raise HTTPException(status_code=400, detail="File must have a filename")
        validate_xlsx_file(file.filename)
    
    temp_file_path = None
    try:
        if jobs_path and os.path.exists(jobs_path):
            # Validate path extension
            if not jobs_path.lower().endswith(('.xlsx', '.xls')):
                raise HTTPException(
                    status_code=400,
                    detail="Only XLSX files are accepted for jobs_path"
                )
            file_path = jobs_path
        else:
            # Save uploaded file to temporary location
            suffix = Path(file.filename).suffix.lower() if file.filename else ".xlsx"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                shutil.copyfileobj(file.file, tmp)
                temp_file_path = tmp.name
            file_path = temp_file_path
        
        # Prepare initial state
        initial: State = {
            "jobs_path": file_path,
            "skills_cache": {"vectors": {}},
            "skills_lock": __import__("threading").Lock(),
            "skill_normalizer": normalizer,
            "has_resume": False,
            "has_jobs": True,
        }
        
        # Process jobs
        result = langgraph_app.invoke(initial)
        
        return ProcessResponse(
            success=True,
            results=result.get("results", {}),
            message=f"Jobs processed successfully"
        )
        
    except Exception as e:
        log(f"Error processing jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Clean up temp file
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)


@api_app.post("/candidate", response_model=CandidateResponse)
async def create_candidate(candidate: CandidateInput):
    """
    Create a candidate in the knowledge graph from JSON input.
    
    Uses the same extraction logic as resume parsing (extract_from_resume).
    
    **Accepts JSON with candidate details (matching resume XLSX format):**
    - `email` (required) - Candidate email (used as unique identifier)
    - `name` (optional) - Candidate name
    - `text` (optional) - Resume text/HTML content (used for extraction)
    - `experience` (optional) - Experience column value (e.g., "3 years", "5+ years")
    - `experience_years` (optional) - Direct years as integer (takes priority)
    - `education` (optional) - Education column value (will be normalized)
    - `category` (optional) - Domain/category (sales or technology)
    - `skills` (optional) - Pre-extracted skills (if not provided, extracted from text)
    
    Returns the candidate node ID created in the knowledge graph.
    """
    global normalizer
    
    try:
        # Validate email
        if not candidate.email or not candidate.email.strip():
            raise HTTPException(status_code=400, detail="Email is required")
        
        email = candidate.email.strip()
        name = candidate.name.strip() if candidate.name else None
        resume_text = candidate.text.strip() if candidate.text else ""
        parsed_domain = candidate.category.strip() if candidate.category else ""
        
        # Use extraction logic similar to resume parsing
        extracted_data = {}
        if resume_text:
            log(f"Extracting candidate data from resume text for: {email}")
            extracted_data = extract_from_resume(resume_text)
            if not isinstance(extracted_data, dict):
                extracted_data = {}
        
        # Use parsed name/email from input if available
        if name:
            extracted_data["name"] = name
        extracted_data["email"] = email
        
        # Process experience - prioritize from input, then from extraction
        experience_years = 0
        if candidate.experience_years is not None:
            experience_years = int(candidate.experience_years)
        elif candidate.experience:
            experience_years = _extract_years_of_experience(candidate.experience)
        elif extracted_data.get("experience_years", 0) > 0:
            experience_years = extracted_data.get("experience_years", 0)
        elif extracted_data.get("experience"):
            experience_years = _extract_years_of_experience(extracted_data.get("experience", ""))
        
        # Normalize education - prioritize from input, then from extraction
        education = ""
        if candidate.education:
            education = _normalize_education(candidate.education)
        elif extracted_data.get("education"):
            education = _normalize_education(extracted_data.get("education", ""))
        
        # Process skills - normalize provided skills or extract from text
        skills = []
        if candidate.skills:
            # Normalize provided skills
            for skill in candidate.skills:
                if skill and skill.strip():
                    canonical, _ = normalizer.normalize_skill(skill.strip())
                    if canonical:
                        skills.append(canonical)
        elif extracted_data.get("skills"):
            # Use extracted skills from resume text
            for skill in extracted_data.get("skills", []):
                if skill and skill.strip():
                    canonical, _ = normalizer.normalize_skill(skill.strip())
                    if canonical:
                        skills.append(canonical)
        
        # Classify domain from resume content
        if resume_text:
            classified_domain = _classify_domain(resume_text, parsed_domain)
            if classified_domain not in ["sales", "technology"]:
                classified_domain = ""
        else:
            classified_domain = parsed_domain if parsed_domain in ["sales", "technology"] else ""
        
        # Create GraphWriter instance
        writer = GraphWriter(
            uri=os.getenv("NEO4J_URI"),
            user=os.getenv("NEO4J_USER"),
            password=os.getenv("NEO4J_PASSWORD"),
            normalizer=normalizer
        )
        
        try:
            # Add candidate to knowledge graph
            candidate_id = writer.merge_candidate(
                name=name or extracted_data.get("name"),
                email=email,
                experience_years=experience_years,
                education=education,
                skills=skills
            )
            
            if not candidate_id:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to create candidate - no ID returned"
                )
            
            log(f"Created candidate: {email} with ID: {candidate_id}")
            
            return CandidateResponse(
                success=True,
                candidate_id=candidate_id,
                message=f"Candidate created successfully"
            )
        finally:
            writer.close()
        
    except HTTPException:
        raise
    except Exception as e:
        log(f"Error creating candidate: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@api_app.post("/job", response_model=JobResponse)
async def create_job(job: JobInput):
    """
    Create a job listing in the knowledge graph from JSON input.
    
    Uses the same extraction logic as job parsing (extract_from_job).
    
    **Accepts JSON with job details (matching jobs XLSX format):**
    - `title` (required) - Job title
    - `company_name` (required) - Company name
    - `description` (required) - Job description (used for extraction)
    - `location` (optional) - Job location
    - `posted_date` (optional) - Posting date
    - `experience` (optional) - Experience column value (e.g., "3 years", "5+ years")
    - `experience_years` (optional) - Direct years as integer (takes priority)
    - `education` (optional) - Education column value (will be normalized)
    - `category` or `domain` (optional) - Domain/category (sales or technology)
    
    Returns the job node ID created in the knowledge graph.
    """
    global normalizer
    
    try:
        # Validate required fields
        if not job.title or not job.title.strip():
            raise HTTPException(status_code=400, detail="Title is required")
        if not job.company_name or not job.company_name.strip():
            raise HTTPException(status_code=400, detail="Company name is required")
        if not job.description or not job.description.strip():
            raise HTTPException(status_code=400, detail="Description is required")
        
        title = job.title.strip()
        company = job.company_name.strip()
        description = job.description.strip()
        location = job.location.strip() if job.location else ""
        posting_date = job.posted_date.strip() if job.posted_date else ""
        
        # Build job dict similar to parse_jobs format
        job_dict = {
            "title": title,
            "company": company,
            "description": description,
            "location": location,
            "posting_date": posting_date
        }
        
        # Process experience from input
        if job.experience_years is not None:
            job_dict["experience_years"] = int(job.experience_years)
            job_dict["experience"] = f"{int(job.experience_years)} years"
        elif job.experience:
            experience_text = job.experience.strip()
            job_dict["experience"] = experience_text
            job_dict["experience_years"] = _extract_years_of_experience(experience_text)
        else:
            job_dict["experience"] = ""
            job_dict["experience_years"] = 0
        
        # Add education if provided
        if job.education:
            job_dict["education"] = job.education.strip()
        
        # Add domain/category if provided
        raw_domain = job.domain or job.category or ""
        if raw_domain:
            job_dict["domain"] = raw_domain.strip()
        
        # Use extraction logic similar to job parsing (extract_from_job)
        log(f"Extracting job data from description for: {title} at {company}")
        extracted_data = extract_from_job(job_dict)
        if not isinstance(extracted_data, dict):
            extracted_data = {}
        
        # Preserve original job data
        extracted_data["title"] = title
        extracted_data["company"] = company
        extracted_data["location"] = extracted_data.get("location") or location
        extracted_data["posting_date"] = extracted_data.get("posting_date") or posting_date
        
        # Prioritize experience from input over extraction
        parsed_experience = job_dict.get("experience", "")
        parsed_years = job_dict.get("experience_years", 0)
        extracted_experience = extracted_data.get("experience", "")
        extracted_years = extracted_data.get("experience_years", 0)
        
        if parsed_experience or parsed_years > 0:
            final_experience_years = parsed_years
        elif extracted_experience or extracted_years > 0:
            final_experience_years = extracted_years
        else:
            final_experience_years = 0
        
        # Normalize education - prioritize from input, then from extraction
        education = ""
        if job.education:
            education = _normalize_education(job.education)
        elif extracted_data.get("education"):
            education = _normalize_education(extracted_data.get("education", ""))
        
        # Classify domain
        job_text = f"{title} {description}"
        raw_domain = extracted_data.get("domain") or job_dict.get("domain") or raw_domain
        classified_domain = _classify_domain(job_text, raw_domain)
        if classified_domain in ["sales", "technology"]:
            final_domain = classified_domain
        else:
            final_domain = None
        
        # Normalize skills
        skills = []
        extracted_skills = extracted_data.get("skills", [])
        for skill in extracted_skills:
            if skill and skill.strip():
                canonical, _ = normalizer.normalize_skill(skill.strip())
                if canonical:
                    skills.append(canonical)
        
        # Create GraphWriter instance
        writer = GraphWriter(
            uri=os.getenv("NEO4J_URI"),
            user=os.getenv("NEO4J_USER"),
            password=os.getenv("NEO4J_PASSWORD"),
            normalizer=normalizer
        )
        
        try:
            # Add job to knowledge graph
            job_id = writer.merge_job(
                title=title,
                company=company,
                location=extracted_data.get("location") or location,
                experience_years=final_experience_years,
                education=education,
                posting_date=extracted_data.get("posting_date") or posting_date,
                domain=final_domain,
                skills=skills
            )
            
            if not job_id:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to create job - no ID returned"
                )
            
            log(f"Created job: {title} at {company} with ID: {job_id}")
            
            return JobResponse(
                success=True,
                job_id=job_id,
                message=f"Job created successfully"
            )
        finally:
            writer.close()
        
    except HTTPException:
        raise
    except Exception as e:
        log(f"Error creating job: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@api_app.post("/process", response_model=ProcessResponse)
async def process_both(
    resume_file: Optional[UploadFile] = File(None),
    jobs_file: Optional[UploadFile] = File(None),
    resume_path: Optional[str] = Form(None),
    jobs_path: Optional[str] = Form(None)
):
    """
    Process both resume and jobs XLSX files in a single request.
    
    **Accepts only XLSX files** (.xlsx or .xls) for both resume and jobs.
    
    At least one file must be provided.
    
    See `/process/resume` and `/process/jobs` endpoints for expected file formats.
    """
    global normalizer
    
    if not resume_file and not jobs_file and not resume_path and not jobs_path:
        raise HTTPException(
            status_code=400,
            detail="At least one of resume_file or jobs_file must be provided"
        )
    
    resume_temp_path = None
    jobs_temp_path = None
    
    try:
        # Handle resume file
        resume_file_path = None
        if resume_path and os.path.exists(resume_path):
            # Validate path extension
            if not resume_path.lower().endswith(('.xlsx', '.xls')):
                raise HTTPException(
                    status_code=400,
                    detail="Only XLSX files are accepted for resume_path"
                )
            resume_file_path = resume_path
        elif resume_file:
            # Validate file extension
            if resume_file.filename:
                validate_xlsx_file(resume_file.filename)
            suffix = Path(resume_file.filename).suffix.lower() if resume_file.filename else ".xlsx"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                shutil.copyfileobj(resume_file.file, tmp)
                resume_temp_path = tmp.name
            resume_file_path = resume_temp_path
        
        # Handle jobs file
        jobs_file_path = None
        if jobs_path and os.path.exists(jobs_path):
            # Validate path extension
            if not jobs_path.lower().endswith(('.xlsx', '.xls')):
                raise HTTPException(
                    status_code=400,
                    detail="Only XLSX files are accepted for jobs_path"
                )
            jobs_file_path = jobs_path
        elif jobs_file:
            # Validate file extension
            if jobs_file.filename:
                validate_xlsx_file(jobs_file.filename)
            suffix = Path(jobs_file.filename).suffix.lower() if jobs_file.filename else ".xlsx"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                shutil.copyfileobj(jobs_file.file, tmp)
                jobs_temp_path = tmp.name
            jobs_file_path = jobs_temp_path
        
        # Prepare initial state
        initial: State = {
            "skills_cache": {"vectors": {}},
            "skills_lock": __import__("threading").Lock(),
            "skill_normalizer": normalizer,
            "has_resume": bool(resume_file_path),
            "has_jobs": bool(jobs_file_path),
        }
        
        if resume_file_path:
            initial["resume_path"] = resume_file_path
        
        if jobs_file_path:
            initial["jobs_path"] = jobs_file_path
        
        # Process both
        result = langgraph_app.invoke(initial)
        
        return ProcessResponse(
            success=True,
            results=result.get("results", {}),
            message="Processing completed successfully"
        )
        
    except Exception as e:
        log(f"Error processing files: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Clean up temp files
        for temp_path in [resume_temp_path, jobs_temp_path]:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)


if __name__ == "__main__":
    port = int(os.getenv("SERVICE_PORT", "8000"))
    host = os.getenv("SERVICE_HOST", "0.0.0.0")
    
    log(f"Starting KG Builder service on {host}:{port}")
    uvicorn.run(api_app, host=host, port=port)

