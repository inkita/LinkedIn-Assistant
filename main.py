
"""
LangGraph + Streamlit Resume–Job Matcher
========================================
Workflow:
1️⃣ Extract text from uploaded resume (PDF)
2️⃣ Send to FastAPI /candidate service → creates candidate node in Neo4j
3️⃣ Query Neo4j for candidate skills + jobs in same domain
4️⃣ Compute semantic match (SentenceTransformer)
5️⃣ Display job matches and chat assistant
"""

import os
import io
import json
import fitz
import tempfile
import requests
import streamlit as st
from typing import Dict, List, Any, TypedDict

from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer, util
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_community.llms import Ollama
from langchain_core.tools import Tool
from langchain_core.prompts import PromptTemplate


# ============ CONFIGURATION ============
OLLAMA_MODEL = "llama3"
API_URL = "http://localhost:8000/candidate"   # FastAPI service endpoint
NEO4J_URI = "neo4j+s://dc47a5a0.databases.neo4j.io"
NEO4J_USER = "neo4j"
NEO4J_PASS = "KJEHHJM1abMuYdu6WzpR2oBx5ue8P1JJtcbM7A7eWck"
# =======================================

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
llm = Ollama(model=OLLAMA_MODEL)
embed_model = SentenceTransformer("all-MiniLM-L6-v2")

# ============ STATE SCHEMA ============
class ResumeGraphState(TypedDict, total=False):
    pdf_path: str
    resume_text: str
    candidate_email: str
    candidate_name: str
    candidate_skills: List[str]
    candidate_domain: str
    job_matches: List[Dict[str, Any]]
    user_input: str
    agent_reply: str
    candidate_id: str


# ============ NODE 1: Extract PDF ============
def extract_pdf_node(state: Dict) -> Dict:
    """Extract text from PDF resume"""
    text = ""
    with fitz.open(state["pdf_path"]) as doc:
        for page in doc:
            text += page.get_text()
    state["resume_text"] = text.strip()
    return state


# ============ NODE 2: Send to /candidate Service ============
def create_candidate_node(state: Dict) -> Dict:
    """Send resume text to FastAPI service for candidate creation"""
    payload = {
        "email": state["candidate_email"],
        "name": state.get("candidate_name", ""),
        "text": state["resume_text"],
        "category": "technology"
    }
    response = requests.post(API_URL, json=payload)
    if response.status_code != 200:
        raise RuntimeError(f"Candidate creation failed: {response.text}")

    res_json = response.json()
    state["candidate_id"] = res_json.get("candidate_id")
    st.write("🧠 Candidate node created:", res_json)
    return state


# ============ NODE 3: Query Candidate Skills ============
def get_candidate_skills_node(state: Dict) -> Dict:
    """Fetch candidate skills and domain from Neo4j using candidate_id and relationships."""
    candidate_id = state.get("candidate_id")
    if not candidate_id:
        raise RuntimeError("Missing candidate_id in state. Make sure /candidate response stored correctly.")

    # query = """
    #     MATCH (c:Candidate {id: $id})-[:HAS_SKILL]->(s:Skill)
    #     RETURN COLLECT(DISTINCT s.name) AS skills,
    #         COLLECT(DISTINCT s.embedding) AS embeddings
    #     """

    # query = """
    #     MATCH (c:Candidate {id: $id})-[:HAS_SKILL]->(s:Skill)
    #     RETURN 
    #         COLLECT(DISTINCT s.name) AS skills,
    #         COLLECT(DISTINCT s.embedding) AS embeddings,
    #         coalesce(c.experience_years, c.experience, 0) AS experience,
    #         coalesce(c.category, "technology") AS domain
    #     """
    query = """
        MATCH (c:Candidate {id: $id})-[:HAS_SKILL]->(s:Skill)
        RETURN COLLECT(DISTINCT s.name) AS skills,
            COLLECT(DISTINCT s.embedding) AS embeddings
        """


    with driver.session() as session:
        result = session.run(query, id=candidate_id).data()

    if not result:
        raise RuntimeError(f"Candidate with ID {candidate_id} not found in Neo4j.")

    state["candidate_skills"] = result[0].get("skills", [])
    state["candidate_embeddings"] = result[0]["embeddings"]
    st.session_state["candidate_embeddings"] = result[0]["embeddings"]
    state["candidate_domain"] = result[0].get("domain", "technology")
    return state


# ============ NODE 4: Query Jobs by Domain ============
def get_jobs_by_domain_node(state: Dict) -> Dict:
    """Fetch jobs for the candidate's domain"""
    # q = """
    #     MATCH (d:Domain {name: $domain})-[:HAS_JOB]->(j:Job)-[:REQUIRES_SKILL]->(s:Skill)
    #     RETURN j.title AS title,
    #         j.company AS company,
    #         COLLECT(DISTINCT s.name) AS job_skills
    #     ORDER BY j.title
    #     """

    # q = """
    #     MATCH (d:Domain {name: $domain})-[:HAS_JOB]->(j:Job)-[:REQUIRES_SKILL]->(s:Skill)
    #     RETURN 
    #         j.title AS title,
    #         j.company AS company,
    #         COLLECT(DISTINCT s.name) AS job_skills,
    #         COLLECT(DISTINCT s.embedding) AS job_skill_embeddings
    #     ORDER BY j.title
    #     """
    
    q = """
        MATCH (d:Domain {name: $domain})-[:HAS_JOB]->(j:Job)-[:REQUIRES_SKILL]->(s:Skill)
        RETURN 
            j.title AS title,
            j.company AS company,
            COLLECT(DISTINCT s.name) AS job_skills,
            COLLECT(DISTINCT s.embedding) AS job_skill_embeddings
        ORDER BY j.title
        """
    # q = """
    #     MATCH (d:Domain {name: $domain})-[:HAS_JOB]->(j:Job)-[:REQUIRES_SKILL]->(s:Skill)
    #     RETURN 
    #         j.title AS title,
    #         j.company AS company,
    #         COLLECT(DISTINCT s.name) AS job_skills,
    #         COLLECT(DISTINCT s.embedding) AS job_skill_embeddings
    #     ORDER BY j.title
    #     LIMIT 50
    #     """


    with driver.session() as s:
        jobs = s.run(
            q,
            domain=state["candidate_domain"],
            candidate_skills=state["candidate_skills"]
        ).data()

    state["jobs_raw"] = jobs
    st.session_state["jobs_raw"] = jobs
    return state


# ============ NODE 5: Compute Skill Match ============
def compute_similarity_node(state: Dict) -> Dict:
#     """Compute semantic similarity between candidate and job skills using pre-stored embeddings."""
#     candidate_skills = state.get("candidate_skills", [])
#     candidate_embeddings = state.get("candidate_embeddings") or st.session_state.get("candidate_embeddings", [])
#     results = []

#     # Helper function for cosine similarity
#     def cosine_similarity(v1, v2):
#         dot = sum(a * b for a, b in zip(v1, v2))
#         norm1 = sum(a * a for a in v1) ** 0.5
#         norm2 = sum(b * b for b in v2) ** 0.5
#         return dot / (norm1 * norm2) if norm1 and norm2 else 0.0

#     # Iterate through jobs
#     jobs = state.get("jobs_raw") or st.session_state.get("jobs_raw", [])
#     for job in jobs:
#         job_skills = job.get("job_skills", [])
#         job_embeddings = job.get("job_skill_embeddings", [])

#         if not candidate_embeddings or not job_embeddings:
#             score = 0.0
#         else:
#             # Compute max similarity per job skill vs. all candidate skills
#             sim_scores = []
#             for je in job_embeddings:
#                 best_sim = max(cosine_similarity(je, ce) for ce in candidate_embeddings)
#                 sim_scores.append(best_sim)
#             score = sum(sim_scores) / len(sim_scores) if sim_scores else 0.0

#         # Simple overlap analysis (by skill name)
#         overlap = [s for s in job_skills if s in candidate_skills]
#         missing = [s for s in job_skills if s not in candidate_skills]

#         results.append({
#             "title": job["title"],
#             "company": job["company"],
#             "match_score": round(score, 3),
#             "overlap_skills": overlap,
#             "missing_skills": missing
#         })

#     # Sort by descending match score
#     state["job_matches"] = sorted(results, key=lambda x: x["match_score"], reverse=True)
#     print("------------------")
#     print(state["job_matches"])
#     return state
    """Compute hybrid (semantic + Guttman-weighted) similarity between candidate and job skills."""
    candidate_skills = state.get("candidate_skills", [])
    candidate_embeddings = state.get("candidate_embeddings") or st.session_state.get("candidate_embeddings", [])
    domain = state.get("candidate_domain", "technology")
    results = []

    # ------------------ Helper functions ------------------
    def cosine_similarity(v1, v2):
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = sum(a * a for a in v1) ** 0.5
        norm2 = sum(b * b for b in v2) ** 0.5
        return dot / (norm1 * norm2) if norm1 and norm2 else 0.0


    # 🧩 Simple Guttman-style hierarchy (expand as needed)
    skill_levels = {
        "technology": {
            "Level_1": ["C", "SQL", "HTML", "CSS"],
            "Level_2": ["Python", "JavaScript", "React", "NodeJS"],
            "Level_3": ["Django", "Flask", "PostgreSQL", "NoSQL"],
            "Level_4": ["Microservices", "Kafka", "AWS", "Docker"],
            "Level_5": ["Kubernetes", "Distributed Systems", "Cloud Architecture"]
        },
        "sales": {
            "Level_1": ["Communication", "CRM", "Lead Generation"],
            "Level_2": ["Negotiation", "Salesforce", "Customer Outreach"],
            "Level_3": ["Forecasting", "Territory Management"],
            "Level_4": ["Pipeline Strategy", "Account Management"],
            "Level_5": ["Enterprise Sales", "Business Strategy"]
        }
    }

    def guttman_weighted_score(candidate_skills, job_skills, domain):
        """Weighted mastery progression — higher-level skills imply lower-level."""
        levels = skill_levels.get(domain, {})
        total_weight, achieved_weight = 0, 0
        level_weights = {f"Level_{i}": i for i in range(1, len(levels)+1)}

        for level, skills in levels.items():
            weight = level_weights[level]
            total_weight += weight * len(skills)
            matched = len(set(candidate_skills) & set(skills))
            achieved_weight += weight * matched

        return round(achieved_weight / total_weight, 3) if total_weight else 0.0


    # ------------------ Iterate through jobs ------------------
    jobs = state.get("jobs_raw") or st.session_state.get("jobs_raw", [])
    for job in jobs:
        job_skills = job.get("job_skills", [])
        job_embeddings = job.get("job_skill_embeddings", [])

        # --- Compute semantic similarity using stored embeddings ---
        if not candidate_embeddings or not job_embeddings:
            semantic_score = 0.0
        else:
            sim_scores = []
            for je in job_embeddings:
                best_sim = max(cosine_similarity(je, ce) for ce in candidate_embeddings)
                sim_scores.append(best_sim)
            semantic_score = sum(sim_scores) / len(sim_scores) if sim_scores else 0.0

        # --- Compute Guttman mastery score ---
        guttman_score = guttman_weighted_score(candidate_skills, job_skills, domain)

        # --- Combine both (70–30 weighting) ---
        final_score = round(0.7 * semantic_score + 0.3 * guttman_score, 3)

        # --- Skill overlap and missing analysis ---
        overlap = [s for s in job_skills if s in candidate_skills]
        missing = [s for s in job_skills if s not in candidate_skills]

        results.append({
            "title": job["title"],
            "company": job["company"],
            "match_score": final_score,
            "semantic_score": round(semantic_score, 3),
            "guttman_score": guttman_score,
            "overlap_skills": overlap,
            "missing_skills": missing
        })

    # ------------------ Finalize ------------------
    state["job_matches"] = sorted(results, key=lambda x: x["match_score"], reverse=True)
    print("------------------")
    print(state["job_matches"])
    return state



# ============ NODE 6: Chat Assistant ============
def chat_agent_node(state: Dict) -> Dict:
    """Simple conversational agent powered by Ollama"""
    user_q = state.get("user_input", "")
    if not user_q:
        return state

    tools = [
        Tool(
            name="Top Job Matches",
            func=lambda _: json.dumps(state["job_matches"][:5], indent=2),
            description="Show top job matches and scores."
        ),
        Tool(
            name="Missing Skills",
            func=lambda _: json.dumps({
                j['title']: j['missing_skills'] for j in state['job_matches'][:3]
            }, indent=2),
            description="List missing skills per job."
        )
    ]
    prompt = PromptTemplate(
        input_variables=["input"],
        template=(
            "You are a helpful AI career assistant.\n"
            "Use the job matches and skills data to help the user.\n"
            "{input}"
        )
    )
    reply = llm.invoke(prompt.format(input=user_q))
    state["agent_reply"] = reply
    return state


# ============ BUILD LANGGRAPH ============
builder = StateGraph(state_schema=ResumeGraphState)
builder.add_node("extract_pdf", extract_pdf_node)
builder.add_node("create_candidate", create_candidate_node)
builder.add_node("get_candidate_skills", get_candidate_skills_node)
builder.add_node("get_jobs_by_domain", get_jobs_by_domain_node)
builder.add_node("compute_similarity", compute_similarity_node)
builder.add_node("chat_agent", chat_agent_node)

builder.add_edge(START, "extract_pdf")
builder.add_edge("extract_pdf", "create_candidate")
builder.add_edge("create_candidate", "get_candidate_skills")
builder.add_edge("get_candidate_skills", "get_jobs_by_domain")
builder.add_edge("get_jobs_by_domain", "compute_similarity")
builder.add_edge("compute_similarity", "chat_agent")
builder.add_edge("chat_agent", END)

graph = builder.compile(checkpointer=MemorySaver())


# ============ STREAMLIT FRONTEND ============
def main():
    st.set_page_config(page_title="LangGraph Resume Matcher", page_icon="🤖", layout="wide")
    st.title("🤖 LangGraph-Powered Resume–Job Matcher")

    uploaded_file = st.sidebar.file_uploader("📄 Upload Resume (PDF)", type=["pdf"])
    email = st.sidebar.text_input("📧 Candidate Email")
    name = st.sidebar.text_input("👤 Candidate Name")

    if uploaded_file and email:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded_file.read())
            pdf_path = tmp.name

        user_query = st.text_input("💬 Ask about your matches (optional):")

        init_state = {
            "pdf_path": pdf_path,
            "candidate_email": email,
            "candidate_name": name,
            "user_input": user_query
        }

        with st.spinner("Running full LangGraph pipeline..."):
            final_state = graph.invoke(init_state, config={"thread_id": "streamlit_session"})

        st.subheader("📋 Candidate Skills")
        st.write(final_state.get("candidate_skills", []))

        st.subheader("🎯 Job Matches")
        for m in final_state.get("job_matches", [])[:5]:
            st.markdown(
                f"**{m['title']}** — {m['company']}  \n"
                f"Match Score: `{m['match_score']*100:.1f}%`  \n"
                f"Overlap: {', '.join(m['overlap_skills']) or 'None'}  \n"
                f"Missing: {', '.join(m['missing_skills']) or 'None'}"
            )
            st.divider()

        if user_query:
            st.subheader("💬 Assistant Response")
            st.markdown(final_state.get("agent_reply", "(no response)"))


if __name__ == "__main__":
    main()
