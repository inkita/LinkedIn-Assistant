# ollama_extractor.py
import os
import json
import requests
import re
from dotenv import load_dotenv

load_dotenv()

# Common soft skills to filter out (case-insensitive)
# These are non-technical skills that should not be in the knowledge graph
SOFT_SKILLS = {
    "communication", "leadership", "teamwork", "collaboration", "problem solving",
    "problem-solving", "time management", "organization", "analytical thinking",
    "critical thinking", "creativity", "adaptability", "flexibility", "work ethic",
    "interpersonal", "presentation", "negotiation", "mentoring", "coaching",
    "detail oriented", "attention to detail", "multitasking", "self motivated",
    "self-motivated", "proactive", "initiative", "decision making", "decision-making",
    "strategic thinking", "business acumen", "customer service", "client facing",
    "written communication", "verbal communication", "public speaking", "training",
    "teaching", "supervision", "people management", "emotional intelligence",
    "conflict resolution", "stress management", "work-life balance"
}

def _is_soft_skill(skill: str) -> bool:
    """Check if a skill is a soft skill (non-technical)."""
    if not skill:
        return True
    skill_lower = skill.lower().strip()
    
    # Check exact match
    if skill_lower in SOFT_SKILLS:
        return True
    
    # Check if it contains soft skill keywords (but be careful not to exclude technical terms)
    soft_keywords = [
        "communication", "leadership", "teamwork", "people management",
        "problem solving", "interpersonal", "presentation", "negotiation",
        "time management", "organization", "multitasking", "self motivated",
        "customer service", "client facing", "public speaking"
    ]
    for keyword in soft_keywords:
        # Only exclude if it's the main term, not if it's part of a technical term
        if keyword == skill_lower or (len(skill_lower) < 30 and keyword in skill_lower):
            # But allow technical terms that might contain these words
            if any(tech in skill_lower for tech in ["api", "sdk", "framework", "library", "tool", "platform"]):
                continue
            return True
    
    # Exclude generic management terms (unless they're technical like "project management software")
    if skill_lower in ["management", "project management", "product management"]:
        # Only exclude if it's just "management" without technical context
        if skill_lower == "management":
            return True
    
    return False

def _classify_domain(text: str, existing_domain: str = "") -> str:
    """
    Classify domain as 'sales' or 'technology' based on content.
    Returns 'sales', 'technology', or empty string if unclear.
    """
    if not text:
        return existing_domain.lower() if existing_domain else ""
    
    text_lower = text.lower()
    
    # Technology keywords
    tech_keywords = [
        "software", "developer", "programming", "coding", "python", "java", "javascript",
        "engineer", "engineering", "technical", "technology", "it", "computer science",
        "data science", "machine learning", "ai", "artificial intelligence", "devops",
        "cloud", "aws", "azure", "database", "sql", "api", "backend", "frontend",
        "full stack", "web development", "mobile development", "cybersecurity",
        "network", "system administrator", "system admin", "infrastructure"
    ]
    
    # Sales keywords
    sales_keywords = [
        "sales", "account executive", "account manager", "business development",
        "bd", "revenue", "client", "customer", "account", "territory", "quota",
        "crm", "salesforce", "lead generation", "prospecting", "closing",
        "relationship", "partnership", "negotiation", "deal", "pipeline"
    ]
    
    # Count keyword matches
    tech_count = sum(1 for keyword in tech_keywords if keyword in text_lower)
    sales_count = sum(1 for keyword in sales_keywords if keyword in text_lower)
    
    # If existing domain is one of the valid ones, use it
    existing_lower = existing_domain.lower().strip()
    if existing_lower in ["sales", "technology"]:
        return existing_lower
    
    # Classify based on keyword counts
    if tech_count > sales_count and tech_count > 0:
        return "technology"
    elif sales_count > tech_count and sales_count > 0:
        return "sales"
    elif tech_count == sales_count and tech_count > 0:
        # Tie-breaker: if both are present, prefer technology for technical roles
        return "technology"
    else:
        # If no clear match, return empty string
        return ""

def _filter_technical_skills(skills: list) -> list:
    """Filter out soft skills and keep only technical skills."""
    if not skills:
        return []
    
    filtered = []
    seen = set()  # Track seen skills (case-insensitive) to avoid duplicates
    
    for skill in skills:
        if not skill:
            continue
        skill_str = str(skill).strip()
        if not skill_str or skill_str.lower() == "null":
            continue
        
        skill_lower = skill_str.lower()
        
        # Skip soft skills
        if _is_soft_skill(skill_str):
            continue
        
        # Skip if it's just a number (years of experience)
        if skill_str.replace("+", "").replace("-", "").replace(" ", "").strip().isdigit():
            continue
        
        # Skip generic phrases about experience
        if any(phrase in skill_lower for phrase in [
            "years of", "years experience", "year of experience", "years' experience",
            "years of experience", "year experience", "plus years"
        ]):
            continue
        
        # Skip education levels if they're listed as skills
        if skill_lower in ["bachelor", "master", "phd", "doctorate", "degree", "diploma", "certification"]:
            continue
        
        # Skip if it's too generic
        if skill_lower in ["experience", "knowledge", "familiarity", "proficiency", "expertise"]:
            continue
        
        # Skip duplicates (case-insensitive)
        if skill_lower not in seen:
            seen.add(skill_lower)
            filtered.append(skill_str)
    
    return filtered

# Config via .env (with sensible defaults)
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "127.0.0.1")  # or a remote host/IP
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")  # small/fast for tests
BASE = f"http://{OLLAMA_HOST}:11434"

def _get_models(timeout=3):
    try:
        r = requests.get(f"{BASE}/api/tags", timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return {m.get("name") for m in data.get("models", [])}
    except Exception as e:
        raise RuntimeError(
            f"Cannot reach Ollama at {BASE}. Is it running? ({e})"
        )

def _post(path, payload, timeout=(3, 45)):
    """
    Try /api/generate first; if 404, fall back to /api/chat
    so we work across different Ollama builds/routes.
    """
    url = f"{BASE}{path}"
    r = requests.post(url, json=payload, timeout=timeout)
    if r.status_code == 404 and path == "/api/generate":
        # Fallback to chat-style endpoint
        chat_payload = {
            "model": payload["model"],
            "messages": [{"role": "user", "content": payload["prompt"]}],
            "stream": False,
            "options": payload.get("options", {}),
        }
        r = requests.post(f"{BASE}/api/chat", json=chat_payload, timeout=timeout)
    r.raise_for_status()
    return r.json()

def _ollama_generate(prompt: str, model: str = OLLAMA_MODEL, maxtokens: int = 512) -> str:
    # Ensure the model exists (clearer error than a vague 404)
    models = _get_models()
    if model not in models:
        raise RuntimeError(
            f"Ollama model '{model}' not found on {BASE}. "
            f"Install it: `ollama pull {model}`. Installed: {sorted(models)}"
        )

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": maxtokens},
    }

    data = _post("/api/generate", payload)
    # Normalize response shape between /generate and /chat
    if "response" in data:
        return (data["response"] or "").strip()
    if "message" in data and isinstance(data["message"], dict):
        return (data["message"].get("content") or "").strip()
    return ""

def extract_from_resume(text: str):
    prompt = (
        "You are a JSON-only extractor for resume data. Respond ONLY with valid JSON, no markdown, no code blocks, no explanations.\n\n"
        "Extract the following information from the resume:\n"
        'Schema: {\n'
        '  "name": "string or null",\n'
        '  "email": "string or null",\n'
        '  "experience": "string summary of work experience or empty string",\n'
        '  "education": "string summary of education or empty string",\n'
        '  "skills": ["skill1", "skill2", ...]\n'
        '}\n\n'
        "SKILLS EXTRACTION RULES - Extract ONLY technical/hard skills:\n"
        "INCLUDE:\n"
        "- Programming languages: Python, Java, JavaScript, TypeScript, C++, C#, Go, Rust, Ruby, PHP, etc.\n"
        "- Frameworks & Libraries: React, Angular, Vue, Django, Flask, Spring, TensorFlow, PyTorch, Scikit-learn, etc.\n"
        "- Tools & Technologies: Docker, Kubernetes, Git, Jenkins, Terraform, Ansible, etc.\n"
        "- Platforms & Cloud: AWS, Azure, GCP, Heroku, DigitalOcean, etc.\n"
        "- Databases: SQL, PostgreSQL, MySQL, MongoDB, Redis, Cassandra, Elasticsearch, etc.\n"
        "- Operating Systems: Linux, Unix, Windows Server, etc.\n"
        "- Methodologies & Domains: Machine Learning, Deep Learning, NLP, Computer Vision, Data Science, MLOps, DevOps, etc.\n"
        "- Specific technologies: Spark, Hadoop, Kafka, RabbitMQ, GraphQL, REST API, etc.\n\n"
        "EXCLUDE (do not extract these):\n"
        "- Soft skills: communication, leadership, teamwork, problem-solving, time management, etc.\n"
        "- Generic phrases: 'experience with', 'familiarity with', 'knowledge of', 'proficiency in'\n"
        "- Years of experience: '5 years', '3+ years', '10 years experience'\n"
        "- Education levels: 'Bachelor's degree', 'Master's', 'PhD' (extract in education field instead)\n"
        "- Company names, job titles, or location names\n"
        "- Generic terms: experience, knowledge, familiarity, expertise (without context)\n\n"
        "Normalize skill names to lowercase and remove extra spaces (e.g., 'PYTHON' -> 'python', 'ML Ops' -> 'mlops').\n"
        "Return only distinct, meaningful technical skills that are specific and actionable.\n\n"
        f"Resume text:\n{text[:4000]}\n\n"
        "Return valid JSON only. Use null for missing name/email, empty string for missing experience/education, empty array [] if no technical skills found."
    )
    out = _ollama_generate(prompt, maxtokens=1024)
    try:
        # Try to extract JSON from response (handle markdown code blocks if present)
        out_clean = out.strip()
        if out_clean.startswith("```"):
            # Remove markdown code blocks
            lines = out_clean.split("\n")
            out_clean = "\n".join(lines[1:-1]) if len(lines) > 2 else out_clean
        if out_clean.startswith("```json"):
            lines = out_clean.split("\n")
            out_clean = "\n".join(lines[1:-1]) if len(lines) > 2 else out_clean
        
        # Try to extract just the JSON object if there's extra content
        # Find the first { and try to find matching }
        if "{" in out_clean:
            start_idx = out_clean.find("{")
            # Try to find the matching closing brace
            brace_count = 0
            end_idx = start_idx
            for i in range(start_idx, len(out_clean)):
                if out_clean[i] == "{":
                    brace_count += 1
                elif out_clean[i] == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i + 1
                        break
            if end_idx > start_idx:
                out_clean = out_clean[start_idx:end_idx]
        
        data = json.loads(out_clean)
        # Ensure all fields exist
        data.setdefault("name", None)
        data.setdefault("email", None)
        data.setdefault("experience", "")
        data.setdefault("education", "")
        data.setdefault("skills", [])
        
        # Filter out soft skills and clean up skills list
        original_skills = data.get("skills", [])
        if original_skills:
            filtered_skills = _filter_technical_skills(original_skills)
            filtered_out = len(original_skills) - len(filtered_skills)
            if filtered_out > 0:
                print(f"  Filtered out {filtered_out} non-technical skill(s) from resume")
            data["skills"] = filtered_skills
        
        return data
    except Exception as e:
        print(f"Warning: Failed to parse resume extraction: {e}")
        print(f"Raw output: {out[:200]}")
        return {"name": None, "email": None, "experience": "", "education": "", "skills": []}

def extract_from_job(job: dict):
    prompt = (
        "You are a JSON-only extractor for job posting data. Respond ONLY with valid JSON, no markdown, no code blocks, no explanations.\n\n"
        "Extract the following information from the job posting:\n"
        'Schema: {\n'
        '  "skills": ["skill1", "skill2", ...],\n'
        '  "location": "string or empty string",\n'
        '  "experience": "string requirements or empty string (e.g., "3+ years", "5 years experience")",\n'
        '  "education": "string requirements or empty string (e.g., "Bachelor\'s degree", "Master\'s in Computer Science")",\n'
        '  "posting_date": "YYYY-MM-DD format or empty string",\n'
        '  "domain": "MUST be either "sales" or "technology" based on the job description. Classify the job as sales-related (sales, account management, business development) or technology-related (software, engineering, IT, data science). Return empty string if unclear."\n'
        '}\n\n'
        "SKILLS EXTRACTION RULES - Extract ONLY technical/hard skills required for the job:\n"
        "INCLUDE:\n"
        "- Programming languages: Python, Java, JavaScript, TypeScript, C++, C#, Go, Rust, Ruby, PHP, Swift, Kotlin, etc.\n"
        "- Frameworks & Libraries: React, Angular, Vue, Node.js, Django, Flask, Spring, TensorFlow, PyTorch, Scikit-learn, etc.\n"
        "- Tools & Technologies: Docker, Kubernetes, Git, Jenkins, Terraform, Ansible, CI/CD tools, etc.\n"
        "- Platforms & Cloud Services: AWS, Azure, GCP, Heroku, DigitalOcean, AWS S3, EC2, Lambda, etc.\n"
        "- Databases & Data Stores: SQL, PostgreSQL, MySQL, MongoDB, Redis, Cassandra, Elasticsearch, etc.\n"
        "- Operating Systems: Linux, Unix, Windows Server, macOS, etc.\n"
        "- Methodologies & Domains: Machine Learning, Deep Learning, NLP, Computer Vision, Data Science, Data Engineering, MLOps, DevOps, etc.\n"
        "- Specific technologies: Spark, Hadoop, Kafka, RabbitMQ, GraphQL, REST API, Microservices, etc.\n\n"
        "EXCLUDE (do not extract these):\n"
        "- Soft skills: communication, leadership, teamwork, collaboration, problem-solving, time management, etc.\n"
        "- Generic phrases: 'experience with', 'familiarity with', 'knowledge of', 'proficiency in', 'strong background in'\n"
        "- Years of experience: '5 years', '3+ years', '10 years experience', 'minimum 2 years'\n"
        "- Education requirements: 'Bachelor's degree', 'Master's', 'PhD' (extract in education field instead)\n"
        "- Company names, job titles, department names, or location names\n"
        "- Generic terms: experience, knowledge, familiarity, expertise, proficiency (without technical context)\n"
        "- Requirements that are not skills: 'remote work', 'full-time', 'contract', salary ranges, etc.\n\n"
        "Normalize skill names to lowercase and remove extra spaces (e.g., 'PYTHON' -> 'python', 'ML Ops' -> 'mlops').\n"
        "Return only distinct, meaningful technical skills that are specific, actionable, and relevant for the knowledge graph.\n\n"
        "DOMAIN CLASSIFICATION:\n"
        "- Return 'technology' for: software engineering, IT, data science, programming, technical roles, engineering positions\n"
        "- Return 'sales' for: sales roles, account management, business development, revenue generation, client relationship roles\n"
        "- Return empty string if the job doesn't clearly fit into either category\n\n"
        f"Job Title: {job.get('title', '')}\n"
        f"Company: {job.get('company', '')}\n"
        f"Description:\n{job.get('description', '')[:4000]}\n\n"
        "Return valid JSON only. Use empty string for missing fields, empty array [] if no technical skills found."
    )
    out = _ollama_generate(prompt, maxtokens=1024)
    try:
        # Try to extract JSON from response (handle markdown code blocks if present)
        out_clean = out.strip()
        if out_clean.startswith("```"):
            # Remove markdown code blocks
            lines = out_clean.split("\n")
            out_clean = "\n".join(lines[1:-1]) if len(lines) > 2 else out_clean
        if out_clean.startswith("```json"):
            lines = out_clean.split("\n")
            out_clean = "\n".join(lines[1:-1]) if len(lines) > 2 else out_clean
        
        # Try to extract just the JSON object if there's extra content
        # Find the first { and try to find matching }
        if "{" in out_clean:
            start_idx = out_clean.find("{")
            # Try to find the matching closing brace
            brace_count = 0
            end_idx = start_idx
            for i in range(start_idx, len(out_clean)):
                if out_clean[i] == "{":
                    brace_count += 1
                elif out_clean[i] == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i + 1
                        break
            if end_idx > start_idx:
                out_clean = out_clean[start_idx:end_idx]
        
        data = json.loads(out_clean)
        # Ensure all fields exist
        data.setdefault("skills", [])
        data.setdefault("location", "")
        data.setdefault("experience", "")
        data.setdefault("education", "")
        data.setdefault("posting_date", "")
        data.setdefault("domain", "")
        
        # Filter out soft skills and clean up skills list
        original_skills = data.get("skills", [])
        if original_skills:
            filtered_skills = _filter_technical_skills(original_skills)
            filtered_out = len(original_skills) - len(filtered_skills)
            if filtered_out > 0:
                print(f"  Filtered out {filtered_out} non-technical skill(s) from job posting")
            data["skills"] = filtered_skills
        
        # Classify and validate domain
        job_description = f"{job.get('title', '')} {job.get('description', '')}"
        extracted_domain = data.get("domain", "").strip().lower()
        classified_domain = _classify_domain(job_description, extracted_domain)
        
        # Only allow "sales" or "technology"
        if classified_domain in ["sales", "technology"]:
            data["domain"] = classified_domain
        else:
            data["domain"] = ""  # Empty if unclear
        
        return data
    except Exception as e:
        print(f"Warning: Failed to parse job extraction: {e}")
        print(f"Raw output: {out[:200]}")
        return {"skills": [], "location": "", "experience": "", "education": "", "posting_date": "", "domain": ""}
