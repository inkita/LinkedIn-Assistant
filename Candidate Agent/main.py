
"""
LangGraph + Streamlit Resume–Job Matcher
========================================
Workflow:
1️⃣ Extract text from uploaded resume (PDF)
2️⃣ Send to FastAPI /candidate service → creates candidate node in Neo4j
3️⃣ Query Neo4j for candidate skills + jobs in same domain (with pre-filtering)
4️⃣ Compute hybrid match score (Jaccard + Semantic + Guttman)
5️⃣ Display job matches and chat assistant

"""

import os
import io
import json
import fitz
import tempfile
import requests
import streamlit as st
import ssl
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
NEO4J_URI = "neo4j+s://ba7d2a6a.databases.neo4j.io"
NEO4J_USER = "neo4j"
NEO4J_PASS = "9d20zR-GV-LV43mTEOXlrO-nO_aWR3T0RjpCMSHzOYY"
# =======================================

# Create SSL context that doesn't verify certificates (for Aura instances with cert issues)
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# Initialize Neo4j driver with custom SSL context
# Use bolt:// scheme (not bolt+s://) when providing ssl_context
driver = GraphDatabase.driver(
    NEO4J_URI.replace("neo4j+s://", "bolt://"),
    auth=(NEO4J_USER, NEO4J_PASS),
    encrypted=True,
    ssl_context=ssl_context
)
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
        "category": state.get("candidate_domain", "technology")  # Use selected domain
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

    query = """
        MATCH (c:Candidate {id: $id})-[:HAS_SKILL]->(s:Skill)
        RETURN 
            COLLECT(DISTINCT s.name) AS skills,
            COLLECT(DISTINCT s.embedding) AS embeddings,
            COLLECT(DISTINCT s) AS skill_nodes,
            COALESCE(c.experience, 0) AS experience,
            COALESCE(c.category, "technology") AS domain
        """

    with driver.session() as session:
        result = session.run(query, id=candidate_id).data()

    if not result:
        raise RuntimeError(f"Candidate with ID {candidate_id} not found in Neo4j.")

    state["candidate_skills"] = result[0].get("skills", [])
    state["candidate_embeddings"] = result[0]["embeddings"]
    state["candidate_skill_nodes"] = result[0]["skill_nodes"]
    state["candidate_experience"] = result[0].get("experience", 0)
    state["candidate_domain"] = result[0].get("domain", "technology")
    
    # Store in session state for reuse
    st.session_state["candidate_embeddings"] = result[0]["embeddings"]
    st.session_state["candidate_skills"] = result[0].get("skills", [])
    
    return state


# ============ NODE 4: Query Jobs by Domain ============
def get_jobs_by_domain_node(state: Dict) -> Dict:
    """
    Fetch jobs for the candidate's domain with pre-computed overlaps.
    Uses graph structure to filter and compute matches in Neo4j.
    
    Note: All skill names in Neo4j are stored in lowercase for consistency.
    """
    q = """
        // Get candidate skills (all lowercase in DB)
        MATCH (c:Candidate {id: $candidate_id})-[:HAS_SKILL]->(cs:Skill)
        WITH COLLECT(DISTINCT cs) AS candidateSkills, 
             COLLECT(DISTINCT cs.name) AS candidateSkillNames,
             COLLECT(DISTINCT cs.embedding) AS candidateEmbeddings
        
        // Get jobs in the domain
        MATCH (d:Domain {name: $domain})-[:HAS_JOB]->(j:Job)
        MATCH (j)-[:REQUIRES_SKILL]->(js:Skill)
        
        WITH candidateSkills, candidateSkillNames, candidateEmbeddings,
             j,
             COLLECT(DISTINCT js) AS jobSkills,
             COLLECT(DISTINCT js.name) AS jobSkillNames,
             COLLECT(DISTINCT js.embedding) AS jobEmbeddings
        
        // Compute overlaps and missing skills (case-sensitive, but all lowercase)
        WITH j, candidateSkillNames, candidateEmbeddings, 
             jobSkillNames, jobEmbeddings,
             [skill IN jobSkillNames WHERE skill IN candidateSkillNames] AS overlap_skills,
             [skill IN jobSkillNames WHERE NOT skill IN candidateSkillNames] AS missing_skills,
             SIZE([skill IN jobSkillNames WHERE skill IN candidateSkillNames]) AS overlap_count,
             SIZE(jobSkillNames) AS total_required
        
        // Pre-filter: Only return jobs with at least 1 matching skill
        WHERE overlap_count > 0
        
        RETURN 
            j.title AS title,
            j.company AS company,
            j.location AS location,
            j.experience AS required_experience,
            jobSkillNames AS job_skills,
            jobEmbeddings AS job_skill_embeddings,
            overlap_skills,
            missing_skills,
            overlap_count,
            total_required,
            candidateEmbeddings
        ORDER BY overlap_count DESC, total_required ASC
        LIMIT 100
        """

    with driver.session() as s:
        jobs = s.run(
            q,
            domain=state["candidate_domain"],
            candidate_id=state["candidate_id"]
        ).data()

    st.write(f"🔍 Found {len(jobs)} jobs with skill overlap in {state['candidate_domain']} domain")
    
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
    """
    Compute hybrid matching score using:
    1. Jaccard similarity (exact skill matches)
    2. Semantic similarity (embedding-based)
    3. Guttman hierarchical score (job-specific weighted progression)
    """
    candidate_skills = state.get("candidate_skills", [])
    candidate_embeddings = state.get("candidate_embeddings") or st.session_state.get("candidate_embeddings", [])
    domain = state.get("candidate_domain", "technology")
    results = []

    # ------------------ Helper functions ------------------
    def cosine_similarity(v1, v2):
        """Compute cosine similarity between two vectors"""
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = sum(a * a for a in v1) ** 0.5
        norm2 = sum(b * b for b in v2) ** 0.5
        return dot / (norm1 * norm2) if norm1 and norm2 else 0.0

    # 🧩 Guttman-style skill hierarchy (domain-specific)
    # Note: All skills in lowercase to match Neo4j database format
    skill_levels = {
        "technology": {
            "Level_1": ["c", "sql", "html", "css", "git", "bash"],
            "Level_2": ["python", "javascript", "react", "nodejs", "java", "typescript"],
            "Level_3": ["django", "flask", "postgresql", "nosql", "mongodb", "mysql"],
            "Level_4": ["microservices", "kafka", "aws", "docker", "redis", "elasticsearch"],
            "Level_5": ["kubernetes", "distributed systems", "cloud architecture", "system design"]
        },
        "sales": {
            "Level_1": ["communication", "crm", "lead generation", "email marketing"],
            "Level_2": ["negotiation", "salesforce", "customer outreach", "cold calling"],
            "Level_3": ["forecasting", "territory management", "pipeline management"],
            "Level_4": ["pipeline strategy", "account management", "deal closing"],
            "Level_5": ["enterprise sales", "business strategy", "strategic partnerships"]
        }
    }

    def compute_jaccard_similarity(overlap_skills, missing_skills, candidate_skills):
        """
        Jaccard similarity: intersection / union
        Measures exact skill overlap
        Note: All skills from Neo4j are already lowercase
        """
        overlap_count = len(overlap_skills)
        total_job_skills = overlap_count + len(missing_skills)
        
        # Union = overlap + missing (from job) + extra (from candidate)
        # Defensive: convert to lowercase and use sets for efficiency
        overlap_set = set(s.lower() if isinstance(s, str) else s for s in overlap_skills)
        missing_set = set(s.lower() if isinstance(s, str) else s for s in missing_skills)
        candidate_set = set(s.lower() if isinstance(s, str) else s for s in candidate_skills)
        
        extra_candidate_skills = len(candidate_set - overlap_set - missing_set)
        union_size = total_job_skills + extra_candidate_skills
        
        return overlap_count / union_size if union_size > 0 else 0.0

    def guttman_weighted_score(candidate_skills, job_skills, domain):
        """
        Job-specific Guttman score: weighted mastery of skills required by THIS job.
        Higher-level skills get more weight.
        
        FIXED: Now evaluates against job_skills instead of entire hierarchy.
        Note: All skills from Neo4j are already lowercase, hierarchy is also lowercase.
        """
        levels = skill_levels.get(domain, {})
        if not levels:
            return 0.0
        
        # Defensive: convert to lowercase sets for consistent comparison
        candidate_set = set(s.lower() if isinstance(s, str) else s for s in candidate_skills)
        job_set = set(s.lower() if isinstance(s, str) else s for s in job_skills)
        
        total_weight, achieved_weight = 0, 0
        level_weights = {f"Level_{i}": i for i in range(1, len(levels) + 1)}
        
        # Only consider job-required skills that exist in the hierarchy
        for level, level_skills in levels.items():
            weight = level_weights[level]
            level_skills_set = set(level_skills)  # Already lowercase
            
            # Job skills at this level
            job_skills_at_level = job_set & level_skills_set
            
            if job_skills_at_level:
                # Count how many the candidate has
                matched = len(job_skills_at_level & candidate_set)
                total_weight += weight * len(job_skills_at_level)
                achieved_weight += weight * matched
        
        return round(achieved_weight / total_weight, 3) if total_weight > 0 else 0.0

    # ------------------ Iterate through jobs ------------------
    jobs = state.get("jobs_raw") or st.session_state.get("jobs_raw", [])
    
    if not jobs:
        st.warning("⚠️ No jobs found with matching skills.")
        state["job_matches"] = []
        return state

    for job in jobs:
        # Pre-computed fields from Neo4j query
        job_skills = job.get("job_skills", [])
        job_embeddings = job.get("job_skill_embeddings", [])
        overlap_skills = job.get("overlap_skills", [])
        missing_skills = job.get("missing_skills", [])
        overlap_count = job.get("overlap_count", 0)
        total_required = job.get("total_required", 1)

        # --- 1. Jaccard Similarity (Exact Matches) ---
        jaccard_score = compute_jaccard_similarity(overlap_skills, missing_skills, candidate_skills)

        # --- 2. Semantic Similarity (Embedding-based) ---
        # Only compute for jobs with some overlap (optimization)
        if jaccard_score > 0.05 and candidate_embeddings and job_embeddings:
            sim_scores = []
            for je in job_embeddings:
                best_sim = max(cosine_similarity(je, ce) for ce in candidate_embeddings)
                sim_scores.append(best_sim)
            semantic_score = sum(sim_scores) / len(sim_scores) if sim_scores else 0.0
        else:
            semantic_score = 0.0

        # --- 3. Guttman Hierarchical Score (Job-specific) ---
        guttman_score = guttman_weighted_score(candidate_skills, job_skills, domain)

        # --- 4. Combined Final Score ---
        # Weighting: 30% Jaccard + 40% Semantic + 30% Guttman
        final_score = round(
            0.30 * jaccard_score + 
            0.40 * semantic_score + 
            0.30 * guttman_score,
            3
        )

        results.append({
            "title": job["title"],
            "company": job["company"],
            "location": job.get("location", "N/A"),
            "required_experience": job.get("required_experience", "N/A"),
            "match_score": final_score,
            "breakdown": {
                "jaccard": round(jaccard_score, 3),
                "semantic": round(semantic_score, 3),
                "guttman": guttman_score
            },
            "overlap_skills": overlap_skills,
            "missing_skills": missing_skills,
            "overlap_count": overlap_count,
            "total_required": total_required
        })

    # ------------------ Sort and finalize ------------------
    state["job_matches"] = sorted(results, key=lambda x: x["match_score"], reverse=True)
    
    st.write(f"✅ Scored {len(results)} job matches")
    print("------------------")
    print(f"Candidate: {state.get('candidate_name', 'N/A')}")
    print(f"Skills: {', '.join(candidate_skills)}")
    print(f"Domain: {domain}")
    print("------------------")
    print(f"Top 5 matches:")
    for match in state["job_matches"][:5]:
        job_skills_str = ', '.join(match.get('overlap_skills', [])[:5])  # Show first 5 for brevity
        if len(match.get('overlap_skills', [])) > 5:
            job_skills_str += '...'
        print(f"  {match['title']} @ {match['company']}: {match['match_score']} "
              f"(J={match['breakdown']['jaccard']}, S={match['breakdown']['semantic']}, "
              f"G={match['breakdown']['guttman']}) | Skills: [{job_skills_str}]")
    
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
    domain = st.sidebar.selectbox("🏢 Domain", options=["technology", "sales"], index=0)

    if uploaded_file and email:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded_file.read())
            pdf_path = tmp.name

        user_query = st.text_input("💬 Ask about your matches (optional):")

        init_state = {
            "pdf_path": pdf_path,
            "candidate_email": email,
            "candidate_name": name,
            "candidate_domain": domain,
            "user_input": user_query
        }

        with st.spinner("Running full LangGraph pipeline..."):
            final_state = graph.invoke(init_state, config={"thread_id": "streamlit_session"})

        st.subheader("📋 Candidate Skills")
        st.write(final_state.get("candidate_skills", []))
        
        candidate_domain = final_state.get("candidate_domain", "N/A")
        st.info(f"**Domain:** {candidate_domain}")

        st.subheader("🎯 Job Matches (Top 10)")
        job_matches = final_state.get("job_matches", [])
        
        if not job_matches:
            st.warning("No job matches found. Try a different resume or check your skills.")
        
        for idx, m in enumerate(job_matches[:10], 1):
            # Extract breakdown
            breakdown = m.get("breakdown", {})
            jaccard = breakdown.get("jaccard", 0)
            semantic = breakdown.get("semantic", 0)
            guttman = breakdown.get("guttman", 0)
            
            # Display with expanded details
            with st.expander(f"**#{idx} - {m['title']}** @ {m['company']} — Match: `{m['match_score']*100:.1f}%`", expanded=(idx<=3)):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric("Jaccard Score", f"{jaccard*100:.1f}%", help="Exact skill overlap")
                
                with col2:
                    st.metric("Semantic Score", f"{semantic*100:.1f}%", help="Embedding similarity")
                
                with col3:
                    st.metric("Guttman Score", f"{guttman*100:.1f}%", help="Hierarchical progression")
                
                st.markdown(f"**Location:** {m.get('location', 'N/A')}")
                st.markdown(f"**Required Experience:** {m.get('required_experience', 'N/A')} years")
                st.markdown(f"**Skills Match:** {m.get('overlap_count', 0)}/{m.get('total_required', 0)} skills")
                
                st.markdown("**✅ Matching Skills:**")
                st.write(', '.join(m['overlap_skills']) if m['overlap_skills'] else '_(None)_')
                
                st.markdown("**❌ Missing Skills:**")
                st.write(', '.join(m['missing_skills']) if m['missing_skills'] else '_(None)_')
            
            if idx < 10 and idx < len(job_matches):
                st.divider()

        if user_query:
            st.subheader("💬 Assistant Response")
            st.markdown(final_state.get("agent_reply", "(no response)"))


if __name__ == "__main__":
    main()
