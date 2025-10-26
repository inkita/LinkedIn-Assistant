"""
resume_match_app_ollama.py
A Streamlit web app that:
1. Extracts text from uploaded PDF resume
2. Parses it into structured JSON using Ollama (local LLM)
3. Compares parsed data with a Neo4j Knowledge Graph of jobs
4. Displays ranked job matches and missing skills
5. Provides conversational interface using Ollama
"""

import fitz  # PyMuPDF
import json
import streamlit as st
from typing import List, Dict

# from sentence_transformers import SentenceTransformer, util
# from langchain_community.llms import Ollama
# from langchain_core.tools import Tool
# from langchain.agents import create_react_agent, AgentExecutor
# from langchain_core.prompts import PromptTemplate

from sentence_transformers import SentenceTransformer, util
from langchain_community.llms import Ollama
from langchain_core.tools import Tool
# from langchain_experimental.agents import create_react_agent
from langchain.agents import AgentExecutor, create_react_agent
# from langchain.agents import AgentExecutor
from langchain_core.prompts import PromptTemplate

from neo4j import GraphDatabase
import tempfile
import os


# ========== CONFIGURATION ==========
# NEO4J_URI = "neo4j+s://d0ee583f.databases.neo4j.io"
# NEO4J_USER = "amohan78@asu.edu"
# NEO4J_PASS = "qA4mwmqaJbdqQ8BQwU2xUhMnNjG5_OJc01IcXJMc4sU"
OLLAMA_MODEL = "llama3"  # or "mistral", "phi3", etc.

NEO4J_URI="neo4j+s://d0ee583f.databases.neo4j.io"
NEO4J_USER="neo4j"
NEO4J_PASS="qA4mwmqaJbdqQ8BQwU2xUhMnNjG5_OJc01IcXJMc4sU"
# ===================================


# ---------- PDF → TEXT ----------
def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from PDF."""
    text = ""
    with fitz.open(file_path) as doc:
        for page in doc:
            text += page.get_text()
    return text.strip()


# ---------- RESUME PARSER (Agent 1) ----------
def resume_to_json_ollama(resume_text: str) -> Dict:
    """Use Ollama (local LLM) to extract structured resume info."""
    prompt = (
        'Schema: {"skills": ["..."]}\n'
        "Rules:\n"
        "- Return ONLY valid JSON.\n"
        "- Extract capability skills (languages, frameworks, tools, cloud, ML/DS methods, databases).\n"
        "- Exclude soft skills or generic verbs.\n"
        "- Deduplicate.\n\n"
        f"Resume text (trimmed):\n{resume_text[:4000]}\n"
    )

    llm = Ollama(model=OLLAMA_MODEL)
    response = llm.invoke(prompt)

    try:
        data = json.loads(response)
    except Exception:
        import re
        json_str = re.search(r"\{.*\}", response, re.DOTALL)
        data = json.loads(json_str.group()) if json_str else {"skills": []}
    return data


# ---------- KNOWLEDGE GRAPH AGENT ----------
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
model = SentenceTransformer("all-MiniLM-L6-v2")


def semantic_skill_score(candidate_skills: List[str], job_skills: List[str]) -> float:
    """Compute semantic similarity between candidate and job skills."""
    if not candidate_skills or not job_skills:
        return 0.0
    cand_emb = model.encode(candidate_skills, convert_to_tensor=True)
    job_emb = model.encode(job_skills, convert_to_tensor=True)
    sim = util.cos_sim(cand_emb, job_emb)
    max_sim, _ = sim.max(dim=0)
    return round(float(max_sim.mean()), 3)


def compare_with_kg(resume_json: Dict) -> List[Dict]:
    """Compare parsed resume skills with jobs in Neo4j KG."""
    skills = resume_json.get("skills", [])
    results = []
    with driver.session() as session:
        query = """
        MATCH (j:Job)-[:REQUIRES]->(s:Skill)
        RETURN j.title AS title, j.company AS company, COLLECT(s.name) AS job_skills
        """
        jobs = session.run(query)
        for job in jobs:
            job_skills = job["job_skills"]
            score = semantic_skill_score(skills, job_skills)
            missing = [js for js in job_skills if js not in skills]
            results.append({
                "job": job["title"],
                "company": job["company"],
                "match_score": score,
                "missing_skills": missing
            })
    return sorted(results, key=lambda x: x["match_score"], reverse=True)


# ---------- STREAMLIT UI ----------
def main():
    st.set_page_config(page_title="Ollama Resume Matcher", page_icon="🤖", layout="wide")
    st.title("🤖 AI Resume–Job Matcher (Ollama + Neo4j + LangChain 0.2)")

    st.sidebar.header("📄 Upload Resume")
    uploaded_file = st.sidebar.file_uploader("Upload your PDF resume", type=["pdf"])

    if uploaded_file:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded_file.read())
            pdf_path = tmp.name

        st.success("✅ Resume uploaded successfully!")

        # 1️⃣ Extract text
        with st.spinner("Extracting text from PDF..."):
            resume_text = extract_text_from_pdf(pdf_path)

        # 2️⃣ Parse Resume
        with st.spinner("Parsing resume with Ollama..."):
            resume_json = resume_to_json_ollama(resume_text)

        st.subheader("📋 Extracted Resume Information")
        st.json(resume_json)

        # 3️⃣ Compare with Knowledge Graph
        with st.spinner("Comparing with Knowledge Graph..."):
            matches = compare_with_kg(resume_json)

        st.subheader("🎯 Top Job Matches")
        for m in matches[:5]:
            st.markdown(f"**{m['job']}** — {m['company']}  \n"
                        f"Match Score: `{m['match_score']*100:.1f}%`  \n"
                        f"Missing Skills: {', '.join(m['missing_skills']) if m['missing_skills'] else 'None'}")
            st.divider()

        # 4️⃣ Conversational Section
        st.subheader("💬 Chat with Career Assistant (Powered by Ollama)")
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []

        user_input = st.text_input("Ask me about your job matches, missing skills, or improvements:")

        if user_input:
            # Define tools
            tools = [
                Tool(
                    name="Get Job Matches",
                    func=lambda _: json.dumps(matches[:5], indent=2),
                    description="Shows top job matches and their match scores."
                ),
                Tool(
                    name="Show Missing Skills",
                    func=lambda _: json.dumps({
                        j['job']: j['missing_skills'] for j in matches[:3]
                    }, indent=2),
                    description="Lists missing skills per job."
                )
            ]

            llm = Ollama(model=OLLAMA_MODEL)
            prompt = PromptTemplate(
                input_variables=["input"],
                template="""
                You are a friendly career assistant. The user's resume has been parsed,
                and you have access to job matches and missing skills data.
                Respond conversationally and helpfully.

                {input}
                """
            )

            # Build a ReAct-style agent (LangChain 0.2+)
            agent = create_react_agent(llm, tools, prompt)
            agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=False)

            result = agent_executor.invoke({"input": user_input})
            response = result["output"]

            st.session_state.chat_history.append((user_input, response))

        for user_msg, bot_msg in st.session_state.chat_history:
            st.markdown(f"**👤 You:** {user_msg}")
            st.markdown(f"**🤖 Assistant:** {bot_msg}")
            st.divider()


if __name__ == "__main__":
    main()
