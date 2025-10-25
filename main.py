# main.py
import os, time, sys, json
from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, START, END

from parse_resume import parse_resume
from parse_jobs import parse_jobs
from hf_extractor import extract_skills_from_resume, extract_skills_from_job
from skill_normalizer import normalize_list
from graph_writer import GraphWriter

def log(msg: str):
    print(time.strftime("%H:%M:%S"), msg); sys.stdout.flush()

class State(TypedDict, total=False):
    resume_path: str
    jobs_csv_path: str
    resume_text: str
    jobs: List[Dict[str, Any]]
    resume_skills_raw: List[str]
    jobs_skills_raw: List[List[str]]
    resume_skills: List[str]
    jobs_skills: List[List[str]]
    results: Dict[str, Any]

SAVE_JSON = os.getenv("SAVE_JSON", "0") == "1"
OUT_DIR = os.getenv("OUT_DIR", "./outputs/json")

# ---- nodes -------------------------------------------------------------
def n_parse_resume(state: State) -> State:
    log("LG: parse_resume")
    text = parse_resume(state["resume_path"])
    return {"resume_text": text}

def n_extract_resume_skills(state: State) -> State:
    log("LG: extract_resume_skills (LLM)")
    data = extract_skills_from_resume(state.get("resume_text", ""))
    skills = data.get("skills", []) or []
    if SAVE_JSON:
        os.makedirs(OUT_DIR, exist_ok=True)
        with open(os.path.join(OUT_DIR, "resume_skills_raw.json"), "w", encoding="utf-8") as f:
            json.dump({"skills": skills}, f, ensure_ascii=False, indent=2)
    return {"resume_skills_raw": skills}

def n_normalize_resume(state: State) -> State:
    log("LG: normalize_resume")
    return {"resume_skills": normalize_list(state.get("resume_skills_raw", []) or [], threshold=0.85)}

def n_parse_jobs(state: State) -> State:
    log("LG: parse_jobs")
    return {"jobs": parse_jobs(state["jobs_csv_path"])}

def n_extract_jobs_skills(state: State) -> State:
    log("LG: extract_jobs_skills (LLM)")
    jobs = state.get("jobs", []) or []
    all_skills = []
    for i, job in enumerate(jobs, 1):
        if job.get("skills") is not None:
            skills = job["skills"]
        else:
            data = extract_skills_from_job(job.get("title"), job.get("company"), job.get("description"))
            skills = data.get("skills", []) or []
        all_skills.append(skills)
        if i % 10 == 0 or i == len(jobs):
            log(f"  [progress] extracted {i}/{len(jobs)} jobs")
    if SAVE_JSON:
        os.makedirs(OUT_DIR, exist_ok=True)
        with open(os.path.join(OUT_DIR, "jobs_skills_raw.json"), "w", encoding="utf-8") as f:
            json.dump({"jobs_skills": all_skills}, f, ensure_ascii=False, indent=2)
    return {"jobs_skills_raw": all_skills}

def n_normalize_jobs(state: State) -> State:
    log("LG: normalize_jobs")
    out = [normalize_list(s or [], threshold=0.85) for s in (state.get("jobs_skills_raw") or [])]
    return {"jobs_skills": out}

def n_write_graph(state: State) -> State:
    log("LG: write_graph")
    writer = GraphWriter(
        uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        user=os.getenv("NEO4J_USER", "neo4j"),
        password=os.getenv("NEO4J_PASSWORD", "password"),
    )

    # candidate
    cand_name = os.getenv("CANDIDATE_NAME")
    cand_email = os.getenv("CANDIDATE_EMAIL")
    rskills = state.get("resume_skills", []) or []
    if cand_name or cand_email or rskills:
        if not cand_email and cand_name:
            cand_email = f"{cand_name.replace(' ', '').lower()}@local"
        writer.merge_candidate(cand_name, cand_email or "unknown@local", rskills)

    # jobs
    jobs = state.get("jobs", []) or []
    jskills = state.get("jobs_skills", []) or []
    for job, skills in zip(jobs, jskills):
        writer.merge_job(
            job_id=job.get("job_id"),
            title=job.get("title"),
            company=job.get("company"),
            location=job.get("location"),
            skills=skills,
        )

    writer.close()
    return {"results": {"candidate_skills": rskills, "jobs_written": len(jobs)}}

# ---- graph --------------------------------------------------------------
graph = StateGraph(State)
graph.add_node("parse_resume", n_parse_resume)
graph.add_node("extract_resume_skills", n_extract_resume_skills)
graph.add_node("normalize_resume", n_normalize_resume)
graph.add_node("parse_jobs", n_parse_jobs)
graph.add_node("extract_jobs_skills", n_extract_jobs_skills)
graph.add_node("normalize_jobs", n_normalize_jobs)
graph.add_node("write_graph", n_write_graph)

graph.add_edge(START, "parse_resume")
graph.add_edge("parse_resume", "extract_resume_skills")
graph.add_edge("extract_resume_skills", "normalize_resume")

graph.add_edge(START, "parse_jobs")
graph.add_edge("parse_jobs", "extract_jobs_skills")
graph.add_edge("extract_jobs_skills", "normalize_jobs")

graph.add_edge("normalize_resume", "write_graph")
graph.add_edge("normalize_jobs", "write_graph")
graph.add_edge("write_graph", END)

app = graph.compile()

if __name__ == "__main__":
    resume_path = os.environ.get("RESUME_PATH", os.path.join(os.getcwd(), "samples/candidate1.txt"))
    jobs_csv_path = os.environ.get("JOBS_CSV_PATH", os.path.join(os.getcwd(), "Datasets/samples/postings.sample.csv"))
    initial: State = {"resume_path": resume_path, "jobs_csv_path": jobs_csv_path}
    result = app.invoke(initial)
    print("DONE:", json.dumps(result.get("results", {}), indent=2))
