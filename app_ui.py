import streamlit as st
import fitz
import json
from neo4j import GraphDatabase
from langchain_community.llms import Ollama
import os

# --- CONFIG ---
NEO4J_URI = os.getenv("NEO4J_URI", "neo4j+s://d0ee583f.databases.neo4j.io")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASS", "qA4mwmqaJbdqQ8BQwU2xUhMnNjG5_OJc01IcXJMc4sU")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))

st.set_page_config(page_title="Recruiter Assistant", layout="wide")
st.title("💼 Recruiter Assistant — Match Candidates from JD")

# --- HELPER FUNCTIONS ---
def extract_text(file):
    text = ""
    if file.name.endswith(".pdf"):
        pdf = fitz.open(stream=file.read(), filetype="pdf")
        for page in pdf:
            text += page.get_text("text")
    else:
        text = file.read().decode("utf-8", errors="ignore")
    return text.strip()


def parse_with_ollama(text):
    st.info("🧠 Parsing JD using Ollama... This may take 10–15 seconds.")
    llm = Ollama(model="llama3")
    prompt = f"""
    Extract structured JSON for this job description with keys:
    title, company, description, skills_required (list), exp_min, exp_max, degree_level, preferred_field.
    ---
    {text}
    """
    try:
        response = llm.invoke(prompt)
        jd_json = json.loads(response)
        return jd_json
    except Exception as e:
        st.warning(f"Ollama parsing failed: {e}")
        # fallback
        return {
            "title": "Unknown",
            "company": "Unknown",
            "description": text[:300],
            "skills_required": [],
            "exp_min": 0,
            "exp_max": 10,
            "degree_level": "Bachelor",
            "preferred_field": "Computer Science"
        }


def insert_job(job):
    with driver.session() as session:
        session.run("""
            MERGE (j:Job {title: $title, company: $company})
            SET j.exp_min=$exp_min, j.exp_max=$exp_max, j.degree_level=$degree_level,
                j.field=$preferred_field, j.description=$description
            WITH j
            UNWIND $skills_required AS skill
            MERGE (s:Skill {name: toLower(skill)})
            MERGE (j)-[:REQUIRES_SKILL]->(s);
        """, **job)


def match_candidates(title):
    with driver.session() as session:
        data = session.run("""
            MATCH (j:Job {title: $title})
            MATCH (c:Candidate)-[:HAS_SKILL]->(s:Skill)<-[:REQUIRES_SKILL]-(j)
            WHERE c.experience >= j.exp_min AND c.experience <= j.exp_max
            OPTIONAL MATCH (c)-[:STUDIED_AT]->(i:Institution)
            RETURN c.name AS Candidate, c.email AS Email,
                   count(DISTINCT s) AS skillMatches,
                   c.experience AS Years,
                   i.name AS Institution, i.degree_level AS Degree
            ORDER BY skillMatches DESC
            LIMIT 10;
        """, title=title)
        rows = data.data()
        return rows


# --- UI LOGIC ---
uploaded = st.file_uploader("📎 Upload Job Description (PDF or TXT)", type=["pdf", "txt"])
if uploaded:
    text = extract_text(uploaded)
    if len(text) < 100:
        st.error("⚠️ The uploaded document seems empty or unreadable.")
        st.stop()

    jd_json = parse_with_ollama(text)
    st.subheader("🧩 Parsed Job Description")
    st.json(jd_json)

    if st.button("🔍 Find Top Candidates"):
        st.info("⏳ Running queries in Neo4j...")
        insert_job(jd_json)
        matches = match_candidates(jd_json["title"])

        if matches:
            st.success("✅ Found matching candidates:")
            st.table(matches)
        else:
            st.warning("No matching candidates found in Neo4j.")
            st.caption("Tip: Make sure you’ve loaded candidates from the Resume Dataset first.")
