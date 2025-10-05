# ollama_extractor.py
import json, requests

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:3b"  # use a small model for faster tests; later switch back to mistral

def _ollama_generate(prompt: str, model: str = OLLAMA_MODEL, maxtokens=256) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": maxtokens}
    }
    # (connect timeout, read timeout) — adjust as needed
    resp = requests.post(OLLAMA_URL, json=payload, timeout=(3, 45))
    resp.raise_for_status()
    data = resp.json()
    return data.get("response", "").strip()

def extract_from_resume(text: str):
    prompt = (
        "You are a JSON-only extractor. Respond ONLY valid JSON.\n"
        'Schema: {"name": "...", "email": "...", "skills": ["..."]}\n'
        f"Text:\n{text[:4000]}\n"  # safety truncation for speed
        "If missing fields, use null for name/email and [] for skills."
    )
    out = _ollama_generate(prompt)
    try:
        return json.loads(out)
    except Exception:
        # minimal resilience
        return {"name": None, "email": None, "skills": []}

def extract_from_job(job: dict):
    prompt = (
        "You are a JSON-only extractor. Respond ONLY valid JSON.\n"
        'Schema: {"skills": ["..."]}\n'
        f"Title: {job.get('title')}\nCompany: {job.get('company')}\n"
        f"Description:\n{job.get('description','')[:4000]}\n"
        "Return {\"skills\": []} if unsure."
    )
    out = _ollama_generate(prompt)
    try:
        return json.loads(out)
    except Exception:
        return {"skills": []}
