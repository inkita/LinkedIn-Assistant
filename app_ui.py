# app_ui.py
import streamlit as st
import pandas as pd
import os
import tempfile

# Import all necessary components
from recruiter_agent import JobAgent, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
from candidate_agent import CandidateAgent
from jd_parser import extract_skills_from_jd 

# --- Agent Initialization (using Streamlit caching for persistence) ---

@st.cache_resource
def get_job_agent():
    """Initializes and caches the JobAgent connection to Neo4j."""
    try:
        agent = JobAgent(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
        return agent
    except Exception as e:
        st.error(f"Failed to connect JobAgent to Neo4j: {e}")
        st.stop()
        return None

@st.cache_resource
def get_candidate_agent():
    """Initializes and caches the CandidateAgent connection to Neo4j."""
    try:
        agent = CandidateAgent(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
        return agent
    except Exception as e:
        st.error(f"Failed to connect Candidate Agent to Neo4j: {e}")
        return None

# --- Main Streamlit App ---

def main():
    st.set_page_config(page_title="Recruiter Agent System Test UI", layout="wide")
    st.title("🤖 Recruiter Agent System Interface")
    
    job_agent = get_job_agent()
    candidate_agent = get_candidate_agent()

    # -------------------------------------------------------------------
    # Sidebar for Data Ingestion Controls
    # -------------------------------------------------------------------
    st.sidebar.header("Data Ingestion")
    
    # 1. Job Description Upload
    st.sidebar.subheader("1. Ingest Job Data")
    uploaded_job_file = st.sidebar.file_uploader(
        "Upload jobs_augmented.xlsx", type=["xlsx", "xls"], key="job_upload"
    )
    if uploaded_job_file is not None and st.sidebar.button("Upload Jobs to Neo4j"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_file:
            tmp_file.write(uploaded_job_file.getvalue())
            file_path = tmp_file.name
            
        with st.spinner(f"Processing and uploading {uploaded_job_file.name}..."):
            processed_count = job_agent.upload_job_descriptions(file_path)
            
        if processed_count > 0:
            st.success(f"✅ Successfully uploaded {processed_count} jobs to the Knowledge Graph!")
        else:
            st.warning("⚠️ Job upload failed or zero jobs processed. See console.")
        os.unlink(file_path)

    # 2. Candidate Data Upload (Mock)
    st.sidebar.subheader("2. Ingest Candidate Data")
    uploaded_resume_file = st.sidebar.file_uploader(
        "Upload resumes_augmented.xlsx", type=["xlsx", "xls"], key="resume_upload"
    )
    if uploaded_resume_file is not None and st.sidebar.button("Upload Candidates to Neo4j"):
        # --- CRITICAL: Define your Excel column mapping here ---
        COLUMNS_MAP = {
            'ID': 'candidate_id', 
            'Full Name': 'name', 
            'Skills_List': 'skills', 
            'Email_Address': 'email', 
            'Location_City': 'location'
        }
        # -----------------------------------------------------
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_file:
            tmp_file.write(uploaded_resume_file.getvalue())
            file_path = tmp_file.name
            
        with st.spinner(f"Processing and uploading {uploaded_resume_file.name}..."):
            processed_count = candidate_agent.upload_candidates(file_path, COLUMNS_MAP)
            
        if processed_count > 0:
            st.success(f"✅ Successfully uploaded {processed_count} candidates to the Knowledge Graph!")
        else:
            st.warning("⚠️ Candidate upload failed or zero candidates processed.")
        os.unlink(file_path)

    # -------------------------------------------------------------------
    # Main Area for Testing Search
    # -------------------------------------------------------------------
    st.header("Search Agent Test: Find Candidates for a JD")
    
    user_input = st.text_area(
        "Paste Full Job Description Here:", 
        height=300, 
        placeholder="e.g., The Economic Development & Planning Intern will provide..."
    )
    
    if st.button("Run Candidate Search"):
        if not user_input.strip():
            st.warning("Please paste a job description to search.")
            return

        # 1. PARSE JOB DESCRIPTION (LLM Agent)
        with st.spinner("🤖 Step 1: Extracting required skills from JD..."):
            required_skills = extract_skills_from_jd(user_input)
            st.subheader("Extracted Required Skills:")
            st.code(required_skills)
        
        if not required_skills:
            st.error("❌ Failed to extract any skills. Cannot proceed with search.")
            return

        # 2. CANDIDATE SEARCH (Neo4j Agent with Standard Logic)
        with st.spinner("🔍 Step 2: Searching Neo4j Knowledge Graph for matches..."):
            results = candidate_agent.search_candidates_by_skills(required_skills, max_results=10)
        
        # 3. DISPLAY RESULTS (Improved Scoring, simplified columns)
        st.subheader(f"Top Candidate Matches (Ranked by Skill Count):")
        
        if results:
            df_results = pd.DataFrame(results)
            
            # --- UPDATED DISPLAY COLUMNS (Removed Avg Fuzzy Dist) ---
            df_results['Skill Match Count'] = df_results['matchedSkillsCount'].astype(int) 
            df_results['Match Score (%)'] = (df_results['Skill Match Count'] / len(required_skills) * 100).round(1)
            
            df_results = df_results.rename(columns={'skills': 'Candidate Skills'})
            # Display only the relevant columns
            st.dataframe(df_results[['name', 'location', 'Skill Match Count', 'Match Score (%)', 'Candidate Skills']])
            # -------------------------------------------------------------
            
            st.success(f"✅ Found {len(results)} potential candidates!")
        else:
            st.warning("No candidates found matching the required skills.")

if __name__ == "__main__":
    main()