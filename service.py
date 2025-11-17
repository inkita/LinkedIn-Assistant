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

