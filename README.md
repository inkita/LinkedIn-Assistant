# Agentic Career Assistant

ASU CSE 573 - G7

## Project Overview

The **Agentic Career Assistant** is an intelligent, AI-powered career matching system that revolutionizes how candidates find jobs and recruiters discover talent. Built with cutting-edge agentic AI technologies, the system leverages LangGraph for orchestrated workflows, Neo4j for knowledge graph storage, and Large Language Models (LLMs) for intelligent extraction and matching.

### Key Features

- **Intelligent Resume & Job Parsing**: Automated extraction of skills, experience, and qualifications from resumes and job postings using LLM-powered agents
- **Knowledge Graph Architecture**: Neo4j-based knowledge graph that stores candidates, jobs, skills, and domains with rich relationships for efficient querying
- **Hybrid Matching Algorithm**: Advanced scoring system combining:
  - **Jaccard Similarity**: Exact skill overlap measurement
  - **Semantic Similarity**: Embedding-based similarity using sentence transformers
  - **Guttman Hierarchical Scoring**: Domain-specific skill progression assessment
- **Dual-Agent System**: 
  - **Candidate Agent**: Helps job seekers find personalized job matches with detailed scoring breakdowns
  - **Recruiter Agent**: Enables recruiters to find suitable candidates with explainable matching results
- **Explainable AI**: Transparent matching scores with detailed breakdowns showing why candidates match specific jobs
- **Comprehensive Evaluation**: Built-in evaluation protocols for skill degradation testing and explainability validation

### Technology Stack

- **LangGraph**: Workflow orchestration and agent coordination
- **Neo4j AuraDB**: Graph database for knowledge representation
- **Ollama (LLM)**: Local LLM for text extraction and processing
- **Streamlit**: Interactive web interfaces for both candidates and recruiters
- **Sentence Transformers**: Semantic embeddings for skill matching
- **FastAPI**: RESTful API service for candidate/job processing

### How It Works

1. **Data Ingestion**: Resumes and job postings are parsed using LLM-powered agents that extract structured information (skills, experience, domains)
2. **Knowledge Graph Population**: Extracted entities and relationships are stored in Neo4j, creating a rich graph of candidates, jobs, skills, and domains
3. **Matching Process**: When a candidate uploads a resume or a recruiter posts a job:
   - Skills are extracted and matched against the knowledge graph
   - Hybrid scoring algorithm computes match scores using multiple similarity metrics
   - Results are ranked and presented with detailed explanations
4. **Interactive Experience**: Users interact through Streamlit interfaces that provide real-time matching, chat assistance, and detailed match breakdowns

## Repository Structure

- **Candidate Agent** - Streamlit application for candidates to upload resumes and receive personalized job matches with hybrid scoring (Jaccard, Semantic, Guttman).
- **Recruiter Agent** - Streamlit application for recruiters to find suitable candidates for job postings with explainable matching.
- **Parsers and KG Writer** - LangGraph agents that parse resumes and job postings, extract skills, and populate the Neo4j knowledge graph.
- **algorithmic evaluation** - Evaluation protocols for skill degradation testing and explainability validation of the matching algorithms.
- **Data Preprocessing** - Scripts to preprocess, clean, and augment raw job and candidate datasets for knowledge graph construction.
- **System Level Evaluation** - System-level evaluation scripts for testing candidate-to-job and job-to-candidate search functionality.

