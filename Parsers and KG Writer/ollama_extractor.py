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

def _extract_years_of_experience(text) -> int:
    """
    Extract years of experience from text and return as integer.
    Examples: "3+ years" -> 3, "5 years experience" -> 5, "10+ years" -> 10
    Returns 0 if no valid years found.
    
    Handles string, list, or other types by converting to string first.
    """
    if not text:
        return 0
    
    # Convert to string if it's not already
    if isinstance(text, list):
        # If it's a list, join it or take the first element
        text = " ".join(str(item) for item in text) if text else ""
    elif not isinstance(text, str):
        text = str(text)
    
    if not text:
        return 0
    
    import re
    # Pattern to match years: "3+ years", "5 years", "10+ years experience", "2-5 years", etc.
    patterns = [
        r'(\d+)\s*\+\s*years?',  # "3+ years", "5+ years"
        r'(\d+)\s*years?\s*(?:of\s*)?experience',  # "5 years experience", "3 years of experience"
        r'minimum\s*(\d+)\s*years?',  # "minimum 3 years"
        r'at\s*least\s*(\d+)\s*years?',  # "at least 5 years"
        r'(\d+)\s*-\s*(\d+)\s*years?',  # "2-5 years", "3-7 years" (take minimum)
        r'(\d+)\s+to\s+(\d+)\s*years?',  # "2 to 5 years", "3 to 7 years" (take minimum)
        r'(\d+)\s*years?',  # "5 years" (more general, check last)
    ]
    
    text_lower = text.lower()
    for pattern in patterns:
        match = re.search(pattern, text_lower)
        if match:
            try:
                # Handle range patterns (e.g., "2-5 years")
                if len(match.groups()) > 1:
                    # For ranges, take the minimum (first number)
                    years = int(match.group(1))
                else:
                    years = int(match.group(1))
                return years
            except (ValueError, IndexError):
                continue
    
    # Try to find standalone numbers that might represent years
    # Look for numbers between 1-50 that could be years
    numbers = re.findall(r'\b([1-9]|[1-4][0-9]|50)\b', text_lower)
    if numbers:
        # If there's a number near "year" or "experience", use it
        if 'year' in text_lower or 'experience' in text_lower:
            try:
                return int(numbers[0])
            except ValueError:
                pass
    
    return 0


def _normalize_education(education_text) -> str:
    """
    Normalize education to only: "bachelor's", "master's", or "phd".
    Returns empty string if no valid education level found.
    
    Handles string, list, or other types by converting to string first.
    """
    if not education_text:
        return ""
    
    # Convert to string if it's not already
    if isinstance(education_text, list):
        # If it's a list, join it or take the first element
        education_text = " ".join(str(item) for item in education_text) if education_text else ""
    elif not isinstance(education_text, str):
        education_text = str(education_text)
    
    if not education_text:
        return ""
    
    import re
    education_lower = education_text.lower().strip()
    
    # Patterns for bachelor's
    bachelor_patterns = [
        r"bachelor",
        r"b\.?s\.?",
        r"b\.?a\.?",
        r"b\.?e\.?",
        r"b\.?tech",
        r"undergraduate",
        r"bsc",
        r"bs\b"
    ]
    
    # Patterns for master's
    master_patterns = [
        r"master",
        r"m\.?s\.?",
        r"m\.?a\.?",
        r"m\.?e\.?",
        r"m\.?tech",
        r"mba",
        r"msc",
        r"ms\b",
        r"m\.?eng"
    ]
    
    # Patterns for phd
    phd_patterns = [
        r"ph\.?d\.?",
        r"doctorate",
        r"d\.?phil",
        r"phd\b"
    ]
    
    # Check for phd first (most specific)
    for pattern in phd_patterns:
        if re.search(pattern, education_lower):
            return "phd"
    
    # Check for master's
    for pattern in master_patterns:
        if re.search(pattern, education_lower):
            return "master's"
    
    # Check for bachelor's
    for pattern in bachelor_patterns:
        if re.search(pattern, education_lower):
            return "bachelor's"
    
    return ""


def _classify_domain(text: str = "", existing_domain: str = "", job_title: str = "") -> str:
    """
    Classify domain as 'sales' or 'technology' based primarily on job title.
    Falls back to text analysis if job title is not available or unclear.
    
    Args:
        text: Full text content (fallback for classification)
        existing_domain: Pre-existing domain value (takes priority)
        job_title: Job title string (primary classification source)
    
    Returns:
        'sales', 'technology', or empty string if unclear
    """
    # If existing domain is one of the valid ones, use it (but validate it makes sense)
    if existing_domain:
        if isinstance(existing_domain, list):
            existing_domain = " ".join(str(item) for item in existing_domain) if existing_domain else ""
        elif not isinstance(existing_domain, str):
            existing_domain = str(existing_domain) if existing_domain else ""
        
        existing_lower = existing_domain.lower().strip()
        if existing_lower in ["sales", "technology"]:
            # If existing domain is "sales" but we have strong technical indicators, re-evaluate
            if existing_lower == "sales" and text:
                text_lower_check = text.lower() if isinstance(text, str) else str(text).lower()
                technical_indicators = ["apex", "lightning", "lwc", "vlocity", "copado", "jenkins", 
                                       "bitbucket", "github", "jira", "developer", "engineer", 
                                       "programming", "coding", "python", "java", "javascript"]
                has_tech_indicators = any(ind in text_lower_check for ind in technical_indicators)
                if has_tech_indicators:
                    # Technical skills present, override "sales" domain
                    print(f"  ⚠ Overriding existing 'sales' domain - technical skills detected in text")
                    # Continue to classification logic below
                else:
                    return existing_lower
            else:
                return existing_lower
    
    # PRIORITY 1: Classify based on job title if available
    if job_title:
        job_title_lower = str(job_title).lower().strip()
        
        # Technology job title keywords
        tech_title_keywords = [
            "developer", "engineer", "programmer", "architect", "administrator", "admin",
            "scientist", "analyst", "specialist", "consultant", "technician", "technologist",
            "software", "hardware", "systems", "network", "database", "devops", "sre",
            "security", "cybersecurity", "qa", "quality assurance", "test", "testing",
            "data engineer", "data scientist", "machine learning", "ai", "ml engineer",
            "frontend", "backend", "full stack", "mobile", "web developer",
            "salesforce developer", "salesforce architect", "salesforce admin"
        ]
        
        # Sales job title keywords
        sales_title_keywords = [
            "sales", "account executive", "account manager", "account representative",
            "business development", "bd", "inside sales", "outside sales",
            "sales manager", "sales director", "sales representative", "sales rep",
            "sales specialist", "sales consultant", "sales associate",
            "territory manager", "regional sales", "national sales",
            "client acquisition", "customer success", "account management"
        ]
        
        # Check job title for domain keywords
        for keyword in tech_title_keywords:
            if keyword in job_title_lower:
                return "technology"
        
        for keyword in sales_title_keywords:
            if keyword in job_title_lower:
                return "sales"
    
    # PRIORITY 2: Fall back to text analysis if job title not available or unclear
    if not text:
        return ""
    
    # Ensure text is a string
    if not isinstance(text, str):
        text = str(text)
    
    text_lower = text.lower()
    
    # Check for technical skills/indicators first (strong signal)
    technical_skill_indicators = [
        "apex", "lightning", "lwc", "visualforce", "vlocity", "copado", "soql",
        "python", "java", "javascript", "typescript", "c++", "c#", "go", "rust",
        "react", "angular", "vue", "node.js", "django", "flask", "spring",
        "docker", "kubernetes", "jenkins", "bitbucket", "github", "git", "jira",
        "aws", "azure", "gcp", "sql", "postgresql", "mysql", "mongodb",
        "terraform", "ansible", "ci/cd", "cicd", "devops", "mlops"
    ]
    
    # Check if technical skills are mentioned (this is a strong indicator of technology domain)
    has_technical_skills = any(indicator in text_lower for indicator in technical_skill_indicators)
    
    # Technology keywords in text (job roles/descriptions)
    tech_keywords = [
        "software developer", "software engineer", "programming", "coding",
        "engineer", "engineering", "technical", "technology", "it", "computer science",
        "data science", "machine learning", "ai", "artificial intelligence", "devops",
        "cloud", "database", "api", "backend", "frontend",
        "full stack", "web development", "mobile development", "cybersecurity",
        "system administrator", "system admin", "infrastructure",
        "salesforce developer", "salesforce architect", "salesforce admin"
    ]
    
    # Sales keywords in text (exclude "sales" if it's part of "salesforce" in technical context)
    sales_keywords = [
        "account executive", "account manager", "business development",
        "bd", "revenue", "territory", "quota", "lead generation", "prospecting",
        "closing", "deal", "pipeline", "inside sales", "outside sales",
        "account management", "client acquisition", "sales representative"
    ]
    
    # Check for "sales" keyword but exclude if it's part of "salesforce" in technical context
    sales_mentioned = "sales" in text_lower
    salesforce_technical_context = False
    if sales_mentioned and "salesforce" in text_lower:
        # Check if Salesforce appears with technical indicators
        salesforce_pos = text_lower.find("salesforce")
        context_window = text_lower[max(0, salesforce_pos-100):salesforce_pos+200]
        technical_context_indicators = [
            "developer", "architect", "admin", "apex", "lightning", "lwc",
            "vlocity", "copado", "customization", "integration", "soql",
            "jenkins", "bitbucket", "github", "git", "deployment"
        ]
        salesforce_technical_context = any(indicator in context_window for indicator in technical_context_indicators)
    
    # Count keyword matches in text
    tech_count = sum(1 for keyword in tech_keywords if keyword in text_lower)
    # Only count "sales" if it's not part of technical Salesforce context
    sales_count = sum(1 for keyword in sales_keywords if keyword in text_lower)
    if sales_mentioned and not salesforce_technical_context and "sales" not in [kw for kw in sales_keywords]:
        # Check if "sales" appears as standalone word (not in "salesforce")
        import re
        # Look for "sales" as a whole word, not part of "salesforce"
        sales_pattern = r'\bsales\b'
        if re.search(sales_pattern, text_lower) and not salesforce_technical_context:
            sales_count += 1
    
    # If technical skills are present, strongly favor technology
    if has_technical_skills:
        tech_count += 3  # Heavy weight for technical skills
    
    # Classify based on keyword counts
    if tech_count > sales_count and tech_count > 0:
        return "technology"
    elif sales_count > tech_count and sales_count > 0:
        return "sales"
    elif tech_count == sales_count and tech_count > 0:
        # Tie-breaker: prefer technology, especially if technical skills present
        if has_technical_skills:
            return "technology"
        return "technology"
    else:
        # If no clear match, return empty string
        return ""

def _filter_skills_by_domain(skills: list, domain: str = "") -> list:
    """Filter out soft skills while keeping domain-relevant skills.
    
    Args:
        skills: List of skill strings
        domain: Domain classification ('sales', 'technology', or empty string)
    
    Returns:
        Filtered list of skills with only soft skills removed
    """
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
        
        # Skip soft skills (regardless of domain)
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

def _filter_technical_skills(skills: list) -> list:
    """Legacy function - calls _filter_skills_by_domain for backward compatibility."""
    return _filter_skills_by_domain(skills, "")

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

def _post(path, payload, timeout=(3, 120), max_retries=2):
    """
    Try /api/generate first; if 404, fall back to /api/chat
    so we work across different Ollama builds/routes.
    
    Includes retry logic for timeout errors.
    """
    import time
    
    url = f"{BASE}{path}"
    
    for attempt in range(max_retries + 1):
        try:
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
        except requests.exceptions.Timeout as e:
            if attempt < max_retries:
                wait_time = (attempt + 1) * 2  # Exponential backoff: 2s, 4s
                print(f"  ⚠ Ollama timeout (attempt {attempt + 1}/{max_retries + 1}), retrying in {wait_time}s...")
                time.sleep(wait_time)
                # Increase timeout for retry
                timeout = (timeout[0], timeout[1] + 30)  # Add 30s to read timeout
            else:
                raise RuntimeError(
                    f"Ollama request timed out after {max_retries + 1} attempts. "
                    f"The model may be too slow or the input too large. "
                    f"Consider using a faster model or reducing input size."
                ) from e
        except requests.exceptions.RequestException as e:
            # For other errors, don't retry
            raise

def _ollama_generate(prompt: str, model: str = OLLAMA_MODEL, maxtokens: int = 512) -> str:
    # Ensure the model exists (clearer error than a vague 404)
    models = _get_models()
    if model not in models:
        raise RuntimeError(
            f"Ollama model '{model}' not found on {BASE}. "
            f"Install it: `ollama pull {model}`. Installed: {sorted(models)}"
        )

    # Get timeout from environment or use default (connect: 3s, read: 120s)
    connect_timeout = int(os.getenv("OLLAMA_CONNECT_TIMEOUT", "3"))
    read_timeout = int(os.getenv("OLLAMA_READ_TIMEOUT", "120"))
    timeout = (connect_timeout, read_timeout)

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": maxtokens},
    }

    data = _post("/api/generate", payload, timeout=timeout)
    # Normalize response shape between /generate and /chat
    if "response" in data:
        return (data["response"] or "").strip()
    if "message" in data and isinstance(data["message"], dict):
        return (data["message"].get("content") or "").strip()
    return ""

def extract_from_resume(text: str):
    # Extract job title from resume text (usually near the top or in name/header)
    # Look for common patterns like "Job Title" or "Position: Job Title" or just the title after name
    import re
    job_title = ""
    
    # Try to extract job title from the first few lines or common patterns
    lines = text.split('\n')[:10]  # Check first 10 lines
    for i, line in enumerate(lines):
        line_lower = line.lower().strip()
        # Skip empty lines and name/email lines
        if not line_lower or '@' in line_lower or 'email' in line_lower or 'phone' in line_lower:
            continue
        # Look for title keywords followed by a title
        if any(keyword in line_lower for keyword in ['title', 'position', 'role', 'current role']):
            # Extract the part after the keyword
            parts = re.split(r'[:|•]', line, maxsplit=1)
            if len(parts) > 1:
                job_title = parts[1].strip()
                break
        # If line looks like a job title (capitalized, short, not email/phone)
        elif len(line.strip()) < 60 and line.strip() and not re.search(r'\d{3}[-.]?\d{3}[-.]?\d{4}', line):
            # Check if it contains title-like words
            title_indicators = ['developer', 'engineer', 'manager', 'sales', 'executive', 'analyst', 
                              'specialist', 'consultant', 'architect', 'administrator', 'director']
            if any(indicator in line_lower for indicator in title_indicators):
                job_title = line.strip()
                break
    
    # First classify the domain to inform skill extraction (prioritize job title)
    domain = _classify_domain(text=text, job_title=job_title)
    
    # Build domain-specific skill extraction instructions
    if domain == "sales":
        skill_instructions = (
            "SKILLS EXTRACTION FOR SALES DOMAIN:\n"
            "Extract ONLY the following types of skills IF EXPLICITLY mentioned in the resume:\n"
            "- CRM systems: Salesforce, HubSpot, Zoho, Microsoft Dynamics, Pipedrive, etc.\n"
            "- Sales tools: Outreach.io, Gong, ZoomInfo, LinkedIn Sales Navigator, etc.\n"
            "- Marketing platforms: Marketo, HubSpot Marketing, Mailchimp, etc.\n"
            "- Sales methodologies: SPIN, MEDDIC, Challenger Sale, etc.\n"
            "- Business intelligence tools: Tableau, Power BI, etc. (if mentioned)\n"
            "- Payment/transaction systems: Stripe, PayPal, etc. (if mentioned)\n"
            "- DO NOT extract programming languages or technical IT skills unless explicitly listed\n"
            "- DO NOT infer technical skills based on job titles or responsibilities\n\n"
        )
    elif domain == "technology":
        skill_instructions = (
            "SKILLS EXTRACTION FOR TECHNOLOGY DOMAIN:\n"
            "Extract ONLY the following types of skills IF EXPLICITLY mentioned in the resume:\n"
            "- Programming languages: Python, Java, JavaScript, TypeScript, C++, C#, Go, Rust, Ruby, PHP, Swift, Kotlin, etc.\n"
            "- Frameworks & Libraries: React, Angular, Vue, Node.js, Django, Flask, Spring, TensorFlow, PyTorch, Scikit-learn, etc.\n"
            "- Tools & Technologies: Docker, Kubernetes, Git, Jenkins, Terraform, Ansible, CI/CD tools, etc.\n"
            "- Platforms & Cloud: AWS, Azure, GCP, Heroku, DigitalOcean, etc.\n"
            "- Databases: SQL, PostgreSQL, MySQL, MongoDB, Redis, Cassandra, Elasticsearch, etc.\n"
            "- Operating Systems: Linux, Unix, Windows Server, macOS, etc.\n"
            "- Methodologies: Machine Learning, Deep Learning, NLP, Computer Vision, Data Science, MLOps, DevOps, etc.\n"
            "- Specific technologies: Spark, Hadoop, Kafka, RabbitMQ, GraphQL, REST API, Microservices, etc.\n"
            "- DO NOT extract sales tools or CRM systems unless explicitly mentioned\n\n"
        )
    else:
        skill_instructions = (
            "SKILLS EXTRACTION:\n"
            "Extract ONLY skills that are EXPLICITLY mentioned, whether technical or business-related.\n"
            "Do NOT infer skills based on job titles, education, or responsibilities.\n\n"
        )
    
    prompt = (
        "You are a JSON-only extractor for resume data. Respond ONLY with valid JSON, no markdown, no code blocks, no explanations.\n\n"
        "CRITICAL RULES - ABSOLUTELY NO HALLUCINATION:\n"
        "1. Extract ONLY information that is EXPLICITLY stated in the resume text below\n"
        "2. Do NOT infer, assume, guess, or fabricate any information\n"
        "3. Do NOT add skills based on job titles, education degrees, or responsibilities\n"
        "4. If a skill is not explicitly listed in the resume, DO NOT include it\n"
        "5. Carefully read through the entire resume text to find skills mentioned in:\n"
        "   - A dedicated 'Skills' section (if present)\n"
        "   - Job descriptions/experience sections that mention specific tools or technologies\n"
        "   - Project descriptions that list technologies used\n"
        "   - Any bullet points or lists that mention technical or business tools\n\n"
        "Extract the following information from the resume:\n"
        'Schema: {\n'
        '  "name": "string or null",\n'
        '  "email": "string or null",\n'
        '  "experience": "string summary of work experience or empty string",\n'
        '  "education": "string summary of education or empty string",\n'
        '  "skills": ["skill1", "skill2", ...]\n'
        '}\n\n'
        f"{skill_instructions}"
        "SKILLS EXTRACTION - WHERE TO LOOK IN RESUME:\n"
        "1. Look for a dedicated 'Skills', 'Technical Skills', 'Tools', or 'Technologies' section\n"
        "2. Look in work experience/job descriptions that mention specific tools (e.g., 'Developed applications using Python and React')\n"
        "3. Look in project descriptions that list technologies used\n"
        "4. Extract skills that are explicitly mentioned, even if embedded in sentences (e.g., 'Worked with Django and PostgreSQL' -> extract 'django' and 'postgresql')\n"
        "5. If the resume says 'experience with X' or 'proficient in Y', extract X and Y as skills\n"
        "6. Extract all skills mentioned throughout the resume\n\n"
        "WHAT TO EXCLUDE (NEVER extract these as skills):\n"
        "- Soft skills: communication, leadership, teamwork, collaboration, problem-solving, time management, public speaking, presentation, negotiation, etc.\n"
        "- Generic phrases without tool names: 'experience with', 'familiarity with', 'knowledge of', 'proficiency in' (only extract if followed by a specific tool/technology)\n"
        "- Years of experience: '5 years', '3+ years', '10 years experience'\n"
        "- Education levels: 'Bachelor's degree', 'Master's', 'PhD' (extract in education field instead)\n"
        "- Company names, job titles, department names, or location names\n"
        "- Generic terms without context: experience, knowledge, familiarity, expertise, proficiency (without specific tool/technology name)\n\n"
        "Normalize skill names to lowercase and remove extra spaces (e.g., 'PYTHON' -> 'python', 'ML Ops' -> 'mlops', 'Salesforce CRM' -> 'salesforce crm').\n"
        "Return distinct skills only (no duplicates).\n"
        "If no explicit skills are mentioned in the resume, return an empty array [].\n\n"
        f"Resume text:\n{text[:6000]}\n\n"
        "Return valid JSON only. Use null for missing name/email, empty string for missing experience/education, empty array [] if no skills are explicitly mentioned."
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
        
        # Ensure skills is a list (handle cases where LLM returns null, string, or other types)
        skills_raw = data.get("skills", [])
        if skills_raw is None:
            skills_raw = []
        elif isinstance(skills_raw, str):
            # If skills is a string, try to parse it or split by comma
            if skills_raw.strip().startswith("[") or skills_raw.strip().startswith("{"):
                try:
                    parsed = json.loads(skills_raw)
                    skills_raw = parsed if isinstance(parsed, list) else [parsed] if parsed else []
                except:
                    # Split by comma if it's a simple comma-separated string
                    skills_raw = [s.strip() for s in skills_raw.split(",") if s.strip()]
            else:
                skills_raw = [s.strip() for s in skills_raw.split(",") if s.strip()]
        elif not isinstance(skills_raw, list):
            # Convert other types to list
            skills_raw = [str(skills_raw)] if skills_raw else []
        
        # Clean and normalize skills list
        cleaned_skills = []
        for skill in skills_raw:
            if skill and isinstance(skill, str):
                cleaned_skills.append(skill.strip())
            elif skill:
                cleaned_skills.append(str(skill).strip())
        data["skills"] = cleaned_skills
        
        # Convert experience to string if it's a list or other type
        experience_raw = data.get("experience", "")
        if isinstance(experience_raw, list):
            experience_text = " ".join(str(item) for item in experience_raw) if experience_raw else ""
        elif not isinstance(experience_raw, str):
            experience_text = str(experience_raw) if experience_raw else ""
        else:
            experience_text = experience_raw
        
        # Extract years of experience from experience text
        experience_years = _extract_years_of_experience(experience_text)
        data["experience_years"] = experience_years  # Store as integer
        
        # Convert education to string if it's a list or other type
        education_raw = data.get("education", "")
        if isinstance(education_raw, list):
            education_text = " ".join(str(item) for item in education_raw) if education_raw else ""
        elif not isinstance(education_raw, str):
            education_text = str(education_raw) if education_raw else ""
        else:
            education_text = education_raw
        
        # Normalize education to only: bachelor's, master's, or phd
        normalized_education = _normalize_education(education_text)
        data["education"] = normalized_education  # Replace with normalized value
        
        # Filter out soft skills and clean up skills list
        original_skills = data.get("skills", [])
        if original_skills:
            print(f"  Extracted {len(original_skills)} skill(s) from LLM: {original_skills[:5]}")
            
            # Validate that extracted skills actually appear in the original text
            # This prevents hallucinated skills, but use lenient matching
            import re
            # Clean text: remove HTML tags, normalize whitespace, lowercase
            text_clean = re.sub(r'<[^>]+>', ' ', text)  # Remove HTML tags
            text_clean = re.sub(r'\s+', ' ', text_clean)  # Normalize whitespace
            text_lower = text_clean.lower()
            
            validated_skills = []
            for skill in original_skills:
                if not skill:
                    continue
                skill_str = str(skill).strip()
                skill_lower = skill_str.lower()
                
                # Remove common punctuation for matching
                skill_clean = re.sub(r'[^\w\s-]', '', skill_lower)  # Keep alphanumeric, spaces, hyphens
                skill_words = [w for w in skill_clean.split() if len(w) > 1]  # Words longer than 1 char
                
                if not skill_words:
                    continue
                
                # Check if skill appears in text using multiple strategies
                found = False
                
                # Strategy 1: Exact match (case-insensitive)
                if skill_lower in text_lower:
                    found = True
                # Strategy 2: All significant words appear (for multi-word skills)
                elif len(skill_words) > 1 and all(word in text_lower for word in skill_words):
                    found = True
                # Strategy 3: Single significant word appears (for single-word skills)
                elif len(skill_words) == 1 and skill_words[0] in text_lower:
                    found = True
                # Strategy 4: Check variations (spaces, hyphens, underscores)
                else:
                    variations = [
                        skill_clean,
                        skill_clean.replace(" ", ""),
                        skill_clean.replace("-", ""),
                        skill_clean.replace("_", ""),
                        skill_clean.replace(" ", "-"),
                        skill_clean.replace("-", " "),
                    ]
                    for variation in variations:
                        if variation and len(variation) > 2 and variation in text_lower:
                            found = True
                            break
                
                if not found:
                    print(f"  ⚠ Warning: Extracted skill '{skill}' not found in resume text, removing (possible hallucination)")
                    continue
                
                validated_skills.append(skill_str)
            
            if len(validated_skills) < len(original_skills):
                removed = len(original_skills) - len(validated_skills)
                print(f"  Removed {removed} skill(s) that were not found in resume text")
            else:
                print(f"  ✓ All {len(validated_skills)} extracted skill(s) validated against resume text")
            
            # Filter skills based on domain (keep domain-relevant skills, filter only soft skills)
            # Re-classify domain if needed (job_title was extracted above)
            domain = _classify_domain(text=text, job_title=job_title if 'job_title' in locals() else "")
            filtered_skills = _filter_skills_by_domain(validated_skills, domain)
            filtered_out = len(validated_skills) - len(filtered_skills)
            if filtered_out > 0:
                print(f"  Filtered out {filtered_out} soft skill(s) from resume")
            if len(filtered_skills) == 0 and len(original_skills) > 0:
                print(f"  ⚠ Warning: All {len(original_skills)} extracted skill(s) were filtered out or not found in text. Original skills: {original_skills[:5]}")
            data["skills"] = filtered_skills
        else:
            print(f"  ⚠ Warning: No skills extracted from resume text (text length: {len(text)})")
        
        return data
    except Exception as e:
        print(f"Warning: Failed to parse resume extraction: {e}")
        print(f"Raw output: {out[:200]}")
        return {"name": None, "email": None, "experience": "", "experience_years": 0, "education": "", "skills": []}

def extract_from_job(job: dict):
    # First classify the domain to inform skill extraction (prioritize job title)
    job_title = job.get('title', '')
    job_text = f"{job_title} {job.get('description', '')}"
    domain = _classify_domain(text=job_text, existing_domain=job.get('domain', ''), job_title=job_title)
    
    # Build domain-specific skill extraction instructions
    if domain == "sales":
        skill_instructions = (
            "SKILLS EXTRACTION FOR SALES DOMAIN:\n"
            "Extract ONLY the following types of skills IF EXPLICITLY mentioned in the job description:\n"
            "- CRM systems: Salesforce, HubSpot, Zoho, Microsoft Dynamics, Pipedrive, etc.\n"
            "- Sales tools: Outreach.io, Gong, ZoomInfo, LinkedIn Sales Navigator, etc.\n"
            "- Marketing platforms: Marketo, HubSpot Marketing, Mailchimp, etc.\n"
            "- Sales methodologies: SPIN, MEDDIC, Challenger Sale, etc.\n"
            "- Business intelligence tools: Tableau, Power BI, etc. (if mentioned)\n"
            "- Payment/transaction systems: Stripe, PayPal, etc. (if mentioned)\n"
            "- DO NOT extract programming languages or technical IT skills unless explicitly listed\n"
            "- DO NOT infer technical skills based on job title or company type\n\n"
        )
    elif domain == "technology":
        skill_instructions = (
            "SKILLS EXTRACTION FOR TECHNOLOGY DOMAIN:\n"
            "Extract ONLY the following types of skills IF EXPLICITLY mentioned in the job description:\n"
            "- Programming languages: Python, Java, JavaScript, TypeScript, C++, C#, Go, Rust, Ruby, PHP, Swift, Kotlin, etc.\n"
            "- Frameworks & Libraries: React, Angular, Vue, Node.js, Django, Flask, Spring, TensorFlow, PyTorch, Scikit-learn, etc.\n"
            "- Tools & Technologies: Docker, Kubernetes, Git, Jenkins, Terraform, Ansible, CI/CD tools, etc.\n"
            "- Platforms & Cloud: AWS, Azure, GCP, Heroku, DigitalOcean, etc.\n"
            "- Databases: SQL, PostgreSQL, MySQL, MongoDB, Redis, Cassandra, Elasticsearch, etc.\n"
            "- Operating Systems: Linux, Unix, Windows Server, macOS, etc.\n"
            "- Methodologies: Machine Learning, Deep Learning, NLP, Computer Vision, Data Science, MLOps, DevOps, etc.\n"
            "- Specific technologies: Spark, Hadoop, Kafka, RabbitMQ, GraphQL, REST API, Microservices, etc.\n"
            "- DO NOT extract sales tools or CRM systems unless explicitly mentioned\n\n"
        )
    else:
        skill_instructions = (
            "SKILLS EXTRACTION:\n"
            "Extract ONLY skills that are EXPLICITLY mentioned, whether technical or business-related.\n"
            "Do NOT infer skills based on job title, company type, or responsibilities.\n\n"
        )
    
    prompt = (
        "You are a JSON-only extractor for job posting data. Respond ONLY with valid JSON, no markdown, no code blocks, no explanations.\n\n"
        "CRITICAL RULES - ABSOLUTELY NO HALLUCINATION:\n"
        "1. Extract ONLY information that is EXPLICITLY stated in the job description text below\n"
        "2. Do NOT infer, assume, guess, or fabricate any information\n"
        "3. Do NOT add skills based on job titles, company names, or responsibilities\n"
        "4. If a skill is not explicitly listed in the job description, DO NOT include it\n"
        "5. Carefully read through the entire job description text to find skills mentioned in:\n"
        "   - Requirements/Qualifications sections\n"
        "   - 'Required Skills', 'Preferred Skills', 'Technical Skills', 'Must Have' sections\n"
        "   - Job responsibilities that mention specific tools, technologies, or platforms\n"
        "   - Any bullet points or lists that mention technical or business tools\n\n"
        "Extract the following information from the job posting:\n"
        'Schema: {\n'
        '  "skills": ["skill1", "skill2", ...],\n'
        '  "location": "string or empty string",\n'
        '  "experience": "REQUIRED - Extract years of experience requirement as a string (e.g., "3+ years", "5 years experience", "minimum 2 years", "2-5 years", "at least 4 years"). If no experience requirement is mentioned, return empty string.",\n'
        '  "education": "string requirements or empty string (e.g., "Bachelor\'s degree", "Master\'s in Computer Science")",\n'
        '  "posting_date": "YYYY-MM-DD format or empty string",\n'
        '  "domain": "MUST be either "sales" or "technology" based on the job description. Classify the job as sales-related (sales, account management, business development) or technology-related (software, engineering, IT, data science). Return empty string if unclear."\n'
        '}\n\n'
        "EXPERIENCE EXTRACTION - IMPORTANT:\n"
        "- Look for phrases like: 'X years', 'X+ years', 'minimum X years', 'at least X years', 'X-Y years', 'X to Y years'\n"
        "- Extract the full experience requirement text exactly as written (e.g., '3+ years', '5 years of experience', 'minimum 2 years')\n"
        "- If the job mentions experience in ranges (e.g., '2-5 years'), extract the minimum value or the full range\n"
        "- If no experience requirement is specified, return empty string\n\n"
        f"{skill_instructions}"
        "SKILLS EXTRACTION - WHERE TO LOOK IN JOB DESCRIPTION:\n"
        "1. Look for sections titled: 'Requirements', 'Qualifications', 'Required Skills', 'Preferred Skills', 'Technical Skills', 'Must Have', 'Nice to Have'\n"
        "2. Look in bullet points that list skills, tools, or technologies\n"
        "3. Look in job responsibilities that mention specific tools (e.g., 'Experience with Python', 'Proficiency in Salesforce')\n"
        "4. Extract skills that are explicitly mentioned, even if embedded in sentences (e.g., 'Experience with React and Node.js' -> extract 'react' and 'node.js')\n"
        "5. If the description says 'experience with X' or 'knowledge of Y', extract X and Y as skills\n"
        "6. Extract all skills mentioned, whether required or preferred\n\n"
        "WHAT TO EXCLUDE (NEVER extract these as skills):\n"
        "- Soft skills: communication, leadership, teamwork, collaboration, problem-solving, time management, public speaking, presentation, negotiation, etc.\n"
        "- Generic phrases without tool names: 'experience with', 'familiarity with', 'knowledge of', 'proficiency in' (only extract if followed by a specific tool/technology)\n"
        "- Years of experience: '5 years', '3+ years', '10 years experience', 'minimum 2 years'\n"
        "- Education requirements: 'Bachelor's degree', 'Master's', 'PhD' (extract in education field instead)\n"
        "- Company names, job titles, department names, or location names\n"
        "- Generic terms without context: experience, knowledge, familiarity, expertise, proficiency (without specific tool/technology name)\n"
        "- Requirements that are not skills: 'remote work', 'full-time', 'contract', salary ranges, etc.\n\n"
        "DOMAIN CLASSIFICATION:\n"
        "- Return 'technology' for: software engineering, IT, data science, programming, technical roles, engineering positions\n"
        "- Return 'sales' for: sales roles, account management, business development, revenue generation, client relationship roles\n"
        "- Return empty string if the job doesn't clearly fit into either category\n\n"
        "Normalize skill names to lowercase and remove extra spaces (e.g., 'PYTHON' -> 'python', 'ML Ops' -> 'mlops', 'Salesforce CRM' -> 'salesforce crm').\n"
        "Return distinct skills only (no duplicates).\n"
        "If no explicit skills are mentioned in the job description, return an empty array [].\n\n"
        f"Job Title: {job.get('title', '')}\n"
        f"Company: {job.get('company', '')}\n"
        f"Job Description:\n{job.get('description', '')[:6000]}\n\n"
        "Return valid JSON only. Use empty string for missing fields, empty array [] if no skills are explicitly mentioned."
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
        
        # Ensure skills is a list (handle cases where LLM returns null, string, or other types)
        skills_raw = data.get("skills", [])
        if skills_raw is None:
            skills_raw = []
        elif isinstance(skills_raw, str):
            # If skills is a string, try to parse it or split by comma
            if skills_raw.strip().startswith("[") or skills_raw.strip().startswith("{"):
                try:
                    parsed = json.loads(skills_raw)
                    skills_raw = parsed if isinstance(parsed, list) else [parsed] if parsed else []
                except:
                    # Split by comma if it's a simple comma-separated string
                    skills_raw = [s.strip() for s in skills_raw.split(",") if s.strip()]
            else:
                skills_raw = [s.strip() for s in skills_raw.split(",") if s.strip()]
        elif not isinstance(skills_raw, list):
            # Convert other types to list
            skills_raw = [str(skills_raw)] if skills_raw else []
        
        # Clean and normalize skills list
        cleaned_skills = []
        for skill in skills_raw:
            if skill and isinstance(skill, str):
                cleaned_skills.append(skill.strip())
            elif skill:
                cleaned_skills.append(str(skill).strip())
        data["skills"] = cleaned_skills
        
        # Convert location to string if it's a list or other type
        location_raw = data.get("location", "")
        if isinstance(location_raw, list):
            data["location"] = " ".join(str(item) for item in location_raw) if location_raw else ""
        elif not isinstance(location_raw, str):
            data["location"] = str(location_raw) if location_raw else ""
        
        # Convert posting_date to string if it's a list or other type
        posting_date_raw = data.get("posting_date", "")
        if isinstance(posting_date_raw, list):
            data["posting_date"] = " ".join(str(item) for item in posting_date_raw) if posting_date_raw else ""
        elif not isinstance(posting_date_raw, str):
            data["posting_date"] = str(posting_date_raw) if posting_date_raw else ""
        
        # Convert experience to string if it's a list or other type
        experience_raw = data.get("experience", "")
        if isinstance(experience_raw, list):
            experience_text = " ".join(str(item) for item in experience_raw) if experience_raw else ""
        elif not isinstance(experience_raw, str):
            experience_text = str(experience_raw) if experience_raw else ""
        else:
            experience_text = experience_raw
        
        # Extract years of experience from experience text
        experience_years = _extract_years_of_experience(experience_text)
        data["experience_years"] = experience_years  # Store as integer
        
        # Debug logging: show what was extracted for jobs
        if experience_text and experience_years == 0:
            print(f"  ⚠ Warning: Could not extract years from job experience text: '{experience_text[:100]}'")
        elif experience_text:
            print(f"  ✓ Extracted job experience: '{experience_text[:50]}' -> {experience_years} years")
        
        # Convert education to string if it's a list or other type
        education_raw = data.get("education", "")
        if isinstance(education_raw, list):
            education_text = " ".join(str(item) for item in education_raw) if education_raw else ""
        elif not isinstance(education_raw, str):
            education_text = str(education_raw) if education_raw else ""
        else:
            education_text = education_raw
        
        # Normalize education to only: bachelor's, master's, or phd
        normalized_education = _normalize_education(education_text)
        data["education"] = normalized_education  # Replace with normalized value
        
        # Filter out soft skills and clean up skills list
        original_skills = data.get("skills", [])
        if original_skills:
            print(f"  Extracted {len(original_skills)} skill(s) from LLM: {original_skills[:5]}")
            
            # Validate that extracted skills actually appear in the original text
            # This prevents hallucinated skills, but use lenient matching
            import re
            job_desc = job.get('description', '')
            job_title_text = job.get('title', '')
            full_text = f"{job_title_text} {job_desc}"
            
            # Clean text: remove HTML tags, normalize whitespace, lowercase
            text_clean = re.sub(r'<[^>]+>', ' ', full_text)  # Remove HTML tags
            text_clean = re.sub(r'\s+', ' ', text_clean)  # Normalize whitespace
            text_lower = text_clean.lower()
            
            validated_skills = []
            for skill in original_skills:
                if not skill:
                    continue
                skill_str = str(skill).strip()
                skill_lower = skill_str.lower()
                
                # Remove common punctuation for matching
                skill_clean = re.sub(r'[^\w\s-]', '', skill_lower)  # Keep alphanumeric, spaces, hyphens
                skill_words = [w for w in skill_clean.split() if len(w) > 1]  # Words longer than 1 char
                
                if not skill_words:
                    continue
                
                # Check if skill appears in text using multiple strategies
                found = False
                
                # Strategy 1: Exact match (case-insensitive)
                if skill_lower in text_lower:
                    found = True
                # Strategy 2: All significant words appear (for multi-word skills)
                elif len(skill_words) > 1 and all(word in text_lower for word in skill_words):
                    found = True
                # Strategy 3: Single significant word appears (for single-word skills)
                elif len(skill_words) == 1 and skill_words[0] in text_lower:
                    found = True
                # Strategy 4: Check variations (spaces, hyphens, underscores)
                else:
                    variations = [
                        skill_clean,
                        skill_clean.replace(" ", ""),
                        skill_clean.replace("-", ""),
                        skill_clean.replace("_", ""),
                        skill_clean.replace(" ", "-"),
                        skill_clean.replace("-", " "),
                    ]
                    for variation in variations:
                        if variation and len(variation) > 2 and variation in text_lower:
                            found = True
                            break
                
                if not found:
                    print(f"  ⚠ Warning: Extracted skill '{skill}' not found in job posting, removing (possible hallucination)")
                    continue
                
                validated_skills.append(skill_str)
            
            if len(validated_skills) < len(original_skills):
                removed = len(original_skills) - len(validated_skills)
                print(f"  Removed {removed} skill(s) that were not found in job posting")
            else:
                print(f"  ✓ All {len(validated_skills)} extracted skill(s) validated against job posting text")
            
            # Filter skills based on domain (keep domain-relevant skills, filter only soft skills)
            job_desc = job.get('description', '')
            job_title_text = job.get('title', '')
            full_text = f"{job_title_text} {job_desc}"
            domain = _classify_domain(text=full_text, existing_domain=job.get('domain', ''), job_title=job_title_text)
            filtered_skills = _filter_skills_by_domain(validated_skills, domain)
            filtered_out = len(validated_skills) - len(filtered_skills)
            if filtered_out > 0:
                print(f"  Filtered out {filtered_out} soft skill(s) from job posting")
            if len(filtered_skills) == 0 and len(original_skills) > 0:
                print(f"  ⚠ Warning: All {len(original_skills)} extracted skill(s) were filtered out or not found in text. Original skills: {original_skills[:5]}")
            data["skills"] = filtered_skills
        else:
            job_title = job.get('title', 'Unknown')
            job_desc_len = len(job.get('description', ''))
            print(f"  ⚠ Warning: No skills extracted from job posting '{job_title}' (description length: {job_desc_len})")
        
        # Classify and validate domain
        job_title = job.get('title', '')
        job_description = f"{job_title} {job.get('description', '')}"
        # Convert domain to string if it's a list or other type
        domain_raw = data.get("domain", "")
        if isinstance(domain_raw, list):
            extracted_domain = " ".join(str(item) for item in domain_raw).strip().lower() if domain_raw else ""
        elif not isinstance(domain_raw, str):
            extracted_domain = str(domain_raw).strip().lower() if domain_raw else ""
        else:
            extracted_domain = domain_raw.strip().lower()
        classified_domain = _classify_domain(text=job_description, existing_domain=extracted_domain, job_title=job_title)
        
        # Only allow "sales" or "technology"
        if classified_domain in ["sales", "technology"]:
            data["domain"] = classified_domain
        else:
            data["domain"] = ""  # Empty if unclear
        
        return data
    except Exception as e:
        print(f"Warning: Failed to parse job extraction: {e}")
        print(f"Raw output: {out[:200]}")
        return {"skills": [], "location": "", "experience": "", "experience_years": 0, "education": "", "posting_date": "", "domain": ""}
