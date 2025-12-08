# Parsing Agents and KG Writer Agent

Parses resumes and job postings and writes to the knowledge graph using LangGraph, Ollama, and Neo4j AuraDB.

## Graph Schema

Entities: Candidate, Skill, Job, Domain

Relationships:
- `(:Candidate)-[:HAS_SKILL]->(:Skill)`
- `(:Job)-[:REQUIRES_SKILL]->(:Skill)`
- `(:Domain)-[:HAS_JOB]->(:Job)`

## Setup

### 1. Install Dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install langchain langgraph neo4j pandas sentence-transformers python-dotenv requests python-docx PyMuPDF pdfminer.six openpyxl beautifulsoup4 fastapi uvicorn
```

**Note**: 
- `openpyxl` is required for reading Excel files (`.xlsx`, `.xls`)
- `beautifulsoup4` is required for parsing HTML content from resume XLSX files

### 2. Configure Environment Variables

The `.env` file is already configured with AuraDB credentials. It contains:
- `NEO4J_URI` - AuraDB connection URI (neo4j+s://...)
- `NEO4J_USER` - AuraDB username
- `NEO4J_PASSWORD` - AuraDB password
- `OLLAMA_HOST` - Ollama host (default: 127.0.0.1)
- `OLLAMA_MODEL` - Model to use (default: llama3.2:3b)
- `RESUME_PATH` - (Optional) Path to resume XLSX file - **only needed if running `main.py` directly**
- `JOBS_PATH` - (Optional) Path to jobs XLSX file - **only needed if running `main.py` directly**

**Note**: 
- If using the **service API** (`service.py`), you don't need `RESUME_PATH` or `JOBS_PATH` in `.env` - files are uploaded via API
- If running **`main.py` directly**, at least one of `RESUME_PATH` or `JOBS_PATH` must be provided

### 3. Set Up Ollama

**On macOS:**
1. Open the Ollama app from Applications, or run:
   ```bash
   open -a Ollama
   ```
2. Wait a few seconds for Ollama to start
3. Pull the required model:
   ```bash
   ollama pull llama3.2:3b
   ```

Note: Ollama runs as a background service on macOS - no need to run `ollama serve`.

## Running the KG Builder

### Quick Start

**Process only resume:**
```bash
cd "KG Builder"
source venv/bin/activate
RESUME_PATH=samples/candidate1.pdf python main.py
```

**Process only jobs:**
```bash
JOBS_PATH=samples/jobs.csv python main.py
```

**Process both resume and jobs:**
```bash
RESUME_PATH=samples/candidate1.pdf JOBS_PATH=samples/jobs.xlsx python main.py
```

### Using Environment Variables

You can also set paths in your `.env` file:
```bash
RESUME_PATH=samples/candidate1.pdf
JOBS_PATH=samples/jobs.csv
```

Then run:
```bash
python main.py
```

## Running as a Service (API)

The KG Builder can be run as an HTTP API service that other applications can call.

**Note:** The API service accepts **only XLSX files** (.xlsx or .xls) for both resumes and jobs.

### Start the Service

```bash
# Using uvicorn directly
uvicorn service:api_app --host 0.0.0.0 --port 8000

# Or run the service file directly
python service.py

# With custom host/port (via environment variables)
SERVICE_HOST=0.0.0.0 SERVICE_PORT=8000 python service.py
```

The service will be available at: `http://localhost:8000`

### API Endpoints

**Health Check:**
```bash
curl http://localhost:8000/health
```

**Process Resume:**
```bash
curl -X POST "http://localhost:8000/process/resume" \
  -F "file=@path/to/resumes.xlsx"
```

**Process Jobs:**
```bash
curl -X POST "http://localhost:8000/process/jobs" \
  -F "file=@path/to/jobs.xlsx"
```

**Process Both:**
```bash
curl -X POST "http://localhost:8000/process" \
  -F "resume_file=@path/to/resumes.xlsx" \
  -F "jobs_file=@path/to/jobs.xlsx"
```

## Input Files

### Resume Files

**XLSX Format (Recommended):**
- Columns required:
  - `ID` - Unique identifier
  - `Resume_sthesume_html` (or column containing "resume" and "html") - HTML content of resume
  - `Category` - Domain/category for the candidate
  - `Name` - Candidate name
  - `Email` - Candidate email
- The system extracts plain text from HTML and uses it to extract skills, experience, and education
- Example: `RESUME_PATH=samples/resumes.xlsx python main.py`

**Legacy Formats (still supported):**
- `.txt`, `.pdf`, or `.docx` formats
- Example: `RESUME_PATH=samples/candidate1.pdf python main.py`

### Job Files

**XLSX Format (Recommended):**
- Columns required:
  - `job_id` - Unique identifier
  - `company_name` - Company name
  - `title` - Job title
  - `description` - Job description (used for extracting skills, experience, education)
  - `location` - Job location (optional)
  - `posted_date` - Posting date (optional)
- Example: `JOBS_PATH=samples/jobs.xlsx python main.py`

**Note**: At least one of `RESUME_PATH` or `JOBS_PATH` must be provided.
