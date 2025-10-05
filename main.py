# main.py
import os
import re
import time
import sys
import json
from typing import TypedDict, List, Dict, Any

from langgraph.graph import StateGraph, START, END

# project modules (ensure these files exist as we discussed)
from parse_resume import parse_resume
from parse_jobs import parse_jobs
from ollama_extractor import extract_from_resume, extract_from_job
from skill_normalizer import model as emb_model, util as emb_util
from graph_writer import GraphWriter


# ----------- small logging helper -----------
def log(msg: str):
    print(time.strftime("%H:%M:%S"), msg)
    sys.stdout.flush()


# ----------- LangGraph state schema -----------
class State(TypedDict, total=False):
    # Inputs
    resume_path: str
    jobs_csv_path: str

    # Parsed
    resume_text: str
    jobs: List[Dict[str, Any]]

    # Extracted
    resume_extraction: Dict[str, Any]          # {"name":..., "email":..., "skills":[...]}
    jobs_extractions: List[List[str]]          # list of skills per job

    # Normalized (canonical)
    canonical_resume_skills: List[str]
    canonical_jobs_skills: List[List[str]]

    # Shared cache for skill-dedup embeddings
    # We keep vectors in-memory so both branches share them during a single run
    skills_cache: Dict[str, Any]               # {"vectors": {canonical: tensor}}

    # Output summary
    results: Dict[str, Any]


# ----------- shared normalization using state cache -----------
def normalize_skill_shared(raw: str, state: Dict[str, Any], threshold: float = 0.85) -> str:
    """
    Canonicalize a raw skill string using sentence-transformer similarity against
    a shared state cache. Returns the canonical string used as node name.
    """
    if not raw:
        return ""
    cleaned = re.sub(r"[\s\\-_/]+", " ", raw.strip().lower())
    if not cleaned:
        return ""

    if "skills_cache" not in state or "vectors" not in state["skills_cache"]:
        state["skills_cache"] = {"vectors": {}}

    vectors = state["skills_cache"]["vectors"]
    vec = emb_model.encode(cleaned, convert_to_tensor=True)

    # dedup against existing canonical skills
    for canon, v in vectors.items():
        if emb_util.cos_sim(vec, v).item() > threshold:
            return canon

    # new canonical
    vectors[cleaned] = vec
    return cleaned


# ----------- LangGraph nodes -----------
def n_parse_resume(state: State) -> State:
    log("LG: parse_resume")
    text = parse_resume(state["resume_path"])
    return {"resume_text": text}


def n_extract_resume(state: State) -> State:
    log("LG: extract_resume")
    data = extract_from_resume(state["resume_text"])
    # enforce shape
    if not isinstance(data, dict):
        data = {"name": None, "email": None, "skills": []}
    data.setdefault("name", None)
    data.setdefault("email", None)
    data.setdefault("skills", [])
    return {"resume_extraction": data}


def n_normalize_resume(state: State) -> State:
    log("LG: normalize_resume")
    skills = (state.get("resume_extraction") or {}).get("skills", []) or []
    canon = [s for s in (normalize_skill_shared(s, state) for s in skills) if s]
    return {"canonical_resume_skills": canon}


def n_parse_jobs(state: State) -> State:
    log("LG: parse_jobs")
    jobs = parse_jobs(state["jobs_csv_path"])
    # enforce list of dicts
    if not isinstance(jobs, list):
        jobs = []
    return {"jobs": jobs}


def n_extract_jobs(state: State) -> State:
    log("LG: extract_jobs")
    jobs = state.get("jobs", []) or []
    all_skills: List[List[str]] = []
    for job in jobs:
        j = extract_from_job(job)
        if not isinstance(j, dict):
            j = {"skills": []}
        skills = j.get("skills", []) or []
        all_skills.append(skills)
    return {"jobs_extractions": all_skills}


def n_normalize_jobs(state: State) -> State:
    log("LG: normalize_jobs")
    ext = state.get("jobs_extractions", []) or []
    out: List[List[str]] = []
    for skills in ext:
        canon = [s for s in (normalize_skill_shared(s, state) for s in skills) if s]
        out.append(canon)
    return {"canonical_jobs_skills": out}


def n_write_graph(state: State) -> State:
    log("LG: write_graph")

    writer = GraphWriter(
        uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        user=os.getenv("NEO4J_USER", "neo4j"),
        password=os.getenv("NEO4J_PASSWORD", "password"),
    )

    # ---- Candidate write
    cand = state.get("resume_extraction") or {}
    name = cand.get("name")
    email = cand.get("email")
    # if email missing, synthesize a local one so we have a stable key
    if not email and name:
        email = f"{name.replace(' ', '').lower()}@local"
    cskills = state.get("canonical_resume_skills", []) or []

    if email or name:
        writer.merge_candidate(name, email or "unknown@local", cskills)

    # ---- Jobs write
    jobs = state.get("jobs", []) or []
    jskills = state.get("canonical_jobs_skills", []) or []
    for job, skills in zip(jobs, jskills):
        writer.merge_job(job.get("title"), job.get("company"), skills)

    writer.close()

    return {"results": {"candidate_skills": cskills, "jobs_written": len(jobs)}}


# ----------- Build the LangGraph DAG -----------
graph = StateGraph(State)

# nodes
graph.add_node("parse_resume", n_parse_resume)
graph.add_node("extract_resume", n_extract_resume)
graph.add_node("normalize_resume", n_normalize_resume)

graph.add_node("parse_jobs", n_parse_jobs)
graph.add_node("extract_jobs", n_extract_jobs)
graph.add_node("normalize_jobs", n_normalize_jobs)

graph.add_node("write_graph", n_write_graph)

# edges: two branches from START, converge at write_graph, then END
graph.add_edge(START, "parse_resume")
graph.add_edge("parse_resume", "extract_resume")
graph.add_edge("extract_resume", "normalize_resume")

graph.add_edge(START, "parse_jobs")
graph.add_edge("parse_jobs", "extract_jobs")
graph.add_edge("extract_jobs", "normalize_jobs")

graph.add_edge("normalize_resume", "write_graph")
graph.add_edge("normalize_jobs", "write_graph")
graph.add_edge("write_graph", END)

app = graph.compile()


# ----------- Entrypoint -----------
if __name__ == "__main__":
    # Provide your inputs here
    initial: State = {
        "resume_path": "samples/candidate1.txt",   # or .pdf/.docx (parser supports robust fallbacks)
        "jobs_csv_path": "samples/jobs.csv",
        "skills_cache": {"vectors": {}},           # shared embedding cache for this run
    }

    # Optional environment variables:
    # export OLLAMA_MODEL=llama3.2:3b     # small/fast model for tests (or "mistral")
    # export NEO4J_URI=bolt://localhost:7687
    # export NEO4J_USER=neo4j
    # export NEO4J_PASSWORD=password

    result = app.invoke(initial)

    # simple summary print
    print("DONE:", json.dumps(result.get("results", {}), indent=2))
