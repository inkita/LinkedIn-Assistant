# hf_extractor.py
# Purpose: turn free text into {"skills": [...]}, nothing else.
# Backends:
#   - HF local (transformers) [default]
#   - vLLM OpenAI-compatible server (set EXTRACTOR_BACKEND=vllm)
#
# Env:
#   HF_LLM_MODEL      (e.g., Qwen/Qwen2.5-0.5B-Instruct)
#   HF_HOME           (cache dir)
#   EXTRACTOR_BACKEND ("hf" | "vllm")
#   VLLM_ENDPOINT     (e.g., http://127.0.0.1:8000/v1)

import os, json, re
from typing import Dict, Any

BACKEND = os.getenv("EXTRACTOR_BACKEND", "hf").lower()
MODEL_ID = os.getenv("HF_LLM_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")
CACHE_DIR = os.getenv("HF_HOME", "./Models")

_SYS = (
    "You are a strict JSON extractor. "
    "Return ONLY valid JSON that matches the schema and rules."
)

# ---- helpers ---------------------------------------------------------------
def _safe_parse_json(s: str) -> Dict[str, Any]:
    """Try to parse JSON, otherwise try to pull the largest {...} block."""
    s = (s or "").strip()
    try:
        return json.loads(s)
    except Exception:
        pass
    # try to extract a top-level JSON object
    m = re.search(r"\{.*\}", s, flags=re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return {}
    return {}

# ---- vLLM backend ----------------------------------------------------------
def _gen_json_vllm(prompt: str, max_tokens: int = 256) -> Dict[str, Any]:
    from openai import OpenAI
    endpoint = os.getenv("VLLM_ENDPOINT", "http://127.0.0.1:8000/v1")
    client = OpenAI(base_url=endpoint, api_key="NOT_NEEDED")

    resp = client.chat.completions.create(
        model=MODEL_ID,
        messages=[
            {"role": "system", "content": _SYS},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=max_tokens,
    )
    return _safe_parse_json(resp.choices[0].message.content)

# ---- HF local backend ------------------------------------------------------
_HF = {"tok": None, "model": None}
def _load_hf():
    if _HF["tok"] is not None:
        return _HF["tok"], _HF["model"]
    from transformers import AutoTokenizer, AutoModelForCausalLM
    tok = AutoTokenizer.from_pretrained(MODEL_ID, cache_dir=CACHE_DIR)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        cache_dir=CACHE_DIR,
        device_map="auto",
        torch_dtype="auto",
    )
    _HF["tok"], _HF["model"] = tok, model
    return tok, model

def _gen_json_hf(prompt: str, max_new_tokens: int = 256) -> Dict[str, Any]:
    import torch
    from transformers import GenerationConfig
    tok, model = _load_hf()
    text = f"<|system|>\n{_SYS}\n<|user|>\n{prompt}\n<|assistant|>\n"
    inputs = tok(text, return_tensors="pt").to(model.device)
    cfg = GenerationConfig(
        do_sample=False,
        max_new_tokens=max_new_tokens,
        eos_token_id=tok.eos_token_id,
    )
    with torch.inference_mode():
        out = model.generate(**inputs, generation_config=cfg)
    decoded = tok.decode(out[0], skip_special_tokens=True)
    content = decoded.split("<|assistant|>")[-1].strip()
    return _safe_parse_json(content)

def _gen_json(prompt: str, max_tokens: int = 256) -> Dict[str, Any]:
    if BACKEND == "vllm":
        return _gen_json_vllm(prompt, max_tokens=max_tokens)
    return _gen_json_hf(prompt, max_new_tokens=max_tokens)

# ---- public API: PROMPTS live here ----------------------------------------
def extract_skills_from_resume(text: str) -> Dict[str, Any]:
    """
    PROMPT for resume → skills
    """
    prompt = (
        'Schema: {"skills": ["..."]}\n'
        "Rules:\n"
        "- Return ONLY valid JSON.\n"
        "- Extract capability skills (programming languages, frameworks, tools, cloud/services, ML/DS methods, databases, libraries).\n"
        "- Exclude soft skills (teamwork, communication) and generic verbs (lead, built).\n"
        "- Deduplicate.\n\n"
        f"Resume text (may be long):\n{text[:4000]}\n"
    )
    out = _gen_json(prompt, max_tokens=256)
    if not isinstance(out, dict): out = {}
    out.setdefault("skills", [])
    return out

def extract_skills_from_job(title: str, company: str, description: str, skills_hint: str|None=None) -> Dict[str, Any]:
    """
    PROMPT for job post → skills
    """
    hint = f"\nExisting skills list to consider: {skills_hint}\n" if skills_hint else ""
    prompt = (
        'Schema: {"skills": ["..."]}\n'
        "Rules:\n"
        "- Return ONLY valid JSON.\n"
        "- Extract capability skills required or strongly preferred for THIS job.\n"
        "- Prefer concrete tools/tech (e.g., Python, React, AWS, Tableau, Kubernetes, SQL, scikit-learn).\n"
        "- Exclude soft skills, generic duties, or degrees.\n"
        "- Deduplicate.\n\n"
        f"Job title: {title}\nCompany: {company}\n"
        f"Description:\n{(description or '')[:4000]}\n"
        f"{hint}"
    )
    out = _gen_json(prompt, max_tokens=256)
    if not isinstance(out, dict): out = {}
    out.setdefault("skills", [])
    return out
