# app_ui.py
import streamlit as st
import pandas as pd
import os
import tempfile

# Import JobAgent + env constants so get_job_agent() can instantiate it
from recruiter_agent import JobAgent, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
from candidate_agent import CandidateAgent
from jd_parser import extract_skills_from_jd


# --- Agent Initialization ---
@st.cache_resource
def get_job_agent():
    try:
        return JobAgent(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    except Exception as e:
        st.error(f"Failed to initialize JobAgent: {e}")
        st.stop()

@st.cache_resource
def get_candidate_agent():
    try:
        return CandidateAgent(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    except Exception as e:
        st.error(f"Failed to initialize CandidateAgent: {e}")
        st.stop()


# --- Main Streamlit App ---
def main():
    st.set_page_config(page_title="Recruiter Agent System", layout="wide")
    st.title("🤖 Recruiter Agent System Interface")

    job_agent = get_job_agent()
    candidate_agent = get_candidate_agent()

    # -------------------------
    # Sidebar - Data Ingestion
    # -------------------------
    st.sidebar.header("Data Ingestion")

    # Upload Job Data
    st.sidebar.subheader("1. Ingest Job Data")
    uploaded_job_file = st.sidebar.file_uploader("Upload jobs_augmented.xlsx", type=["xlsx", "xls"], key="job_upload")
    if uploaded_job_file is not None and st.sidebar.button("Upload Jobs to Neo4j"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_file:
            tmp_file.write(uploaded_job_file.getvalue())
            file_path = tmp_file.name
        with st.spinner(f"Uploading {uploaded_job_file.name} to Neo4j..."):
            result = job_agent.upload_job_descriptions(file_path)
            # upload_job_descriptions may return {"processed": N} or a dict summary when use_api=True
            # or (older implementations) just an int. Normalize to an int.
            if isinstance(result, dict):
                processed_count = result.get("processed") or result.get("sent") or 0
            elif isinstance(result, int):
                processed_count = result
            else:
                processed_count = 0

        if processed_count > 0:
            st.success(f"✅ Uploaded {processed_count} jobs to Neo4j!")
        else:
            st.warning("⚠️ Job upload failed or zero processed.")
        try:
            os.unlink(file_path)
        except Exception:
            pass

    # Upload Candidate Data
    st.sidebar.subheader("2. Ingest Candidate Data")
    uploaded_resume_file = st.sidebar.file_uploader("Upload resumes_augmented.xlsx", type=["xlsx", "xls"], key="resume_upload")
    if uploaded_resume_file is not None and st.sidebar.button("Upload Candidates to Neo4j"):
        COLUMNS_MAP = {
            'ID': 'candidate_id',
            'Full Name': 'name',
            'Skills_List': 'skills',
            'Email_Address': 'email',
            'Location_City': 'location'
        }
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_file:
            tmp_file.write(uploaded_resume_file.getvalue())
            file_path = tmp_file.name
        with st.spinner(f"Uploading {uploaded_resume_file.name} to Neo4j..."):
            processed_count = candidate_agent.upload_candidates(file_path, COLUMNS_MAP)
        if processed_count > 0:
            st.success(f"✅ Uploaded {processed_count} candidates!")
        else:
            st.warning("⚠️ Candidate upload failed or zero processed.")
        try:
            os.unlink(file_path)
        except Exception:
            pass

    # -------------------------
    # Search Section
    # -------------------------
    st.header("Search Agent Test: Find Candidates for a JD")
    st.subheader("Job Context")

    col1, col2 = st.columns([2, 2])
    with col1:
        company_name = st.text_input("Company Name", placeholder="e.g., Microsoft")
        job_title = st.text_input("Job Title", placeholder="e.g., Senior Backend Engineer")
    with col2:
        experience = st.number_input("Experience (years)", min_value=0, max_value=50, value=0, step=1)
        location = st.text_input("Location", placeholder="e.g., Remote / San Francisco")

    user_input = st.text_area(
        "Paste Full Job Description Here:",
        height=300,
        placeholder="Paste the full job description text here..."
    )

    if st.button("Run Candidate Search"):
        if not user_input.strip():
            st.warning("Please paste a job description first.")
            return

        # Combine structured context
        parser_input = (
            f"Company: {company_name or 'N/A'}\n"
            f"Job Title: {job_title or 'N/A'}\n"
            f"Experience (years): {int(experience)}\n"
            f"Location: {location or 'N/A'}\n\n"
            f"Job Description:\n{user_input}"
        )

        # Step 1: Extract skills
        with st.spinner("🤖 Extracting required skills from JD..."):
            try:
                required_skills = extract_skills_from_jd(parser_input)
            except Exception as e:
                st.error(f"Parser error: {e}")
                return

        st.subheader("Extracted Required Skills:")
        st.code(required_skills)

        if not required_skills:
            st.warning("❌ No skills extracted — check parser output.")
            return

        # Step 2: Search for candidates
        with st.spinner("🔍 Searching Neo4j for best candidate matches..."):
            results = candidate_agent.search_candidates_by_skills(required_skills, max_results=10)

        st.subheader("Top Candidate Matches (Ranked by Skill Count):")
        if not results:
            st.warning("No candidates found matching the required skills.")
        else:
            df_results = pd.DataFrame(results)
            # support both naming conventions (some versions returned matchedSkillsCount vs matchedSkillsCount)
            if 'matchedSkillsCount' in df_results.columns:
                df_results['Skill Match Count'] = df_results['matchedSkillsCount'].astype(int)
            elif 'matchedSkillsCount' in df_results.columns:
                df_results['Skill Match Count'] = df_results['matchedSkillsCount'].astype(int)
            else:
                # fallback: try raw_score presence
                df_results['Skill Match Count'] = df_results.get('matchedSkillsCount', df_results.get('matchedSkillsCount', 0)).astype(int)

            total_skills = len(required_skills) if isinstance(required_skills, list) and required_skills else 1
            df_results['Match Score (%)'] = (df_results['Skill Match Count'] / total_skills * 100).round(1)
            df_results = df_results.rename(columns={'skills': 'Candidate Skills'})
            # Select columns that exist
            display_cols = [c for c in ['name', 'location', 'Skill Match Count', 'Match Score (%)', 'Candidate Skills'] if c in df_results.columns]
            st.dataframe(df_results[display_cols])
            st.success(f"✅ Found {len(results)} candidate(s)!")

if __name__ == "__main__":
    main()
