# recruiter_agent.py (formerly job_agent.py)
from neo4j import GraphDatabase
from typing import List, Dict
from parse_jobs import parse_jobs
import os
import pandas as pd # Still needed if you use it elsewhere, but not for file creation here

# --- Neo4j Configuration ---
NEO4J_URI="neo4j+s://dc47a5a0.databases.neo4j.io"
NEO4J_USER="neo4j"    
NEO4J_PASSWORD="KJEHHJM1abMuYdu6WzpR2oBx5ue8P1JJtcbM7A7eWck"         # CHANGE THIS
# ---------------------------

# Class definition for JobAgent remains identical (no changes needed inside the class)
class JobAgent:
    # ... (All methods: __init__, close, _create_job_constraints, 
    # _ingest_jobs_transaction, upload_job_descriptions are identical)
    # Ensure you copy them from the previous complete response!
    
    def __init__(self, uri, user, password):
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._driver.verify_connectivity()
        print("✅ JobAgent: Connected to Neo4j.")
    
    def close(self):
        self._driver.close()
        
    def _create_job_constraints(self):
        # ... (Constraint creation logic)
        pass 
    
    def _ingest_jobs_transaction(self, tx, job_data: List[Dict]):
        # ... (Cypher query logic)
        pass 

    def upload_job_descriptions(self, file_path: str) -> int:
        """
        Parses the file (.csv or .xlsx) and loads the data into the Neo4j Knowledge Graph.
        """
        if not os.path.exists(file_path):
            print(f"❌ File not found: {file_path}")
            return 0

        print(f"JobAgent: Parsing job descriptions from {file_path}...")
        try:
            job_data = parse_jobs(file_path)
        except Exception as e:
            print(f"❌ JobAgent: Error parsing file: {e}")
            return 0
        
        if not job_data:
            print("JobAgent: No valid jobs parsed. Skipping upload.")
            return 0
        
        self._create_job_constraints()
        print(f"JobAgent: Found {len(job_data)} jobs to ingest. Starting transaction...")

        with self._driver.session() as session:
            try:
                # ------------------------------------------------------------------
                # 🔄 CRITICAL CHANGE: Use execute_write instead of write_transaction
                # ------------------------------------------------------------------
                processed_count = session.execute_write(
                    self._ingest_jobs_transaction, job_data
                )
                print(f"✅ JobAgent: Successfully processed and uploaded {processed_count} jobs to Neo4j.")
                return processed_count
            except Exception as e:
                print(f"❌ JobAgent: Failed to upload jobs to Neo4j. Error: {e}")
                return 0
        
        # ... (rest of ingestion logic, calling session.write_transaction, etc.)
        self._create_job_constraints()
        print(f"JobAgent: Found {len(job_data)} jobs to ingest. Starting transaction...")

        with self._driver.session() as session:
            try:
                processed_count = session.write_transaction(
                    self._ingest_jobs_transaction, job_data
                )
                print(f"✅ JobAgent: Successfully processed and uploaded {processed_count} jobs to Neo4j.")
                return processed_count
            except Exception as e:
                print(f"❌ JobAgent: Failed to upload jobs to Neo4j. Error: {e}")
                return 0

# --- Router/UI/Entry Point (Main function) ---
def main():
    # --- UPDATE THIS FILE PATH ---
    JOB_DATA_PATH = "jobs_augmented.xlsx" 
    # -----------------------------
    
    job_agent = None

    try:
        print("\n--- Recruiter Agent CLI (Job Ingestion) ---")
        job_agent = JobAgent(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
        
        print(f"\nAction: Upload Job Descriptions from: {JOB_DATA_PATH}")
        job_agent.upload_job_descriptions(JOB_DATA_PATH)
        
        print("\n--- Summary ---")
        print(f"Job ingestion complete. Check your Neo4j database for nodes.")

    except Exception as e:
        print(f"\n❌ An error occurred during connection or execution: {e}")
        print("Please ensure your Neo4j server is running and configuration details are correct.")
    finally:
        if job_agent:
            job_agent.close()

if __name__ == "__main__":
    main()