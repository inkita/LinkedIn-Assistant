# recruiter_agent.py (updated to set job_id = 0, ingested_date = today, experience as integer)
from neo4j import GraphDatabase
from typing import List, Dict, Any
from parse_jobs import parse_jobs
import os

# --- Neo4j Configuration ---
NEO4J_URI = os.getenv("NEO4J_URI", "neo4j+s://dc47a5a0.databases.neo4j.io")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "KJEHHJM1abMuYdu6WzpR2oBx5ue8P1JJtcbM7A7eWck")
# ---------------------------


class JobAgent:
    def __init__(self, uri: str, user: str, password: str):
        """Initialize Neo4j driver and verify connectivity."""
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._driver.verify_connectivity()
        print("✅ JobAgent: Connected to Neo4j.")

    def close(self):
        """Close the driver connection."""
        self._driver.close()

    def _create_job_constraints(self):
        """
        Create indexes/constraints. NOTE: we do NOT create a unique constraint on Job.job_id
        because job_id will be forced to 0 for all jobs per your requirement.
        """
        create_constraints_cypher = [
            # DO NOT make job_id unique because you want job_id = 0 for all ingested jobs.
            # "CREATE CONSTRAINT IF NOT EXISTS FOR (j:Job) REQUIRE j.job_id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (s:Skill) REQUIRE s.name IS UNIQUE"
        ]
        with self._driver.session() as session:
            for cypher in create_constraints_cypher:
                try:
                    session.execute_write(lambda tx, q=cypher: tx.run(q))
                except Exception as e:
                    print(f"⚠️ Warning: constraint/index creation failed: {e}")

    def _ingest_jobs_transaction(self, tx, job_data: List[Dict[str, Any]]):
        """
        Ingest jobs and skills.
        The ingestion will:
         - MERGE on an internal uid (title + source fallback) to avoid duplicate nodes for same job content
         - Set j.job_id = 0 (as requested)
         - Set j.ingested_date = date() (today)
         - Store experience as integer in j.min_experience (from job.experience or job.min_experience)
         - Create Skill nodes and REQUIRES_SKILL relationships
        """
        cypher = """
        UNWIND $job_data AS job
        CALL {
          WITH job
          // Build an internal uid for merging (not the 'job_id' property)
          WITH job,
               CASE WHEN job.job_id IS NOT NULL THEN job.job_id ELSE (coalesce(job.title,'') + '|' + coalesce(job.source,'unknown')) END AS raw_uid
          // Use raw_uid as MERGE key (this is internal and prevents duplication)
          MERGE (j:Job {internal_uid: raw_uid})
          SET
            j.title = coalesce(job.title, j.title),
            j.location = coalesce(job.location, j.location),
            // store the requested job_id value (force to 0)
            j.job_id = 0,
            // store ingested date as today's date in Neo4j
            j.ingested_date = date(),
            // ensure min_experience stored as integer (job.experience preferred)
            j.min_experience = CASE
                                WHEN job.experience IS NOT NULL THEN toInteger(job.experience)
                                WHEN job.min_experience IS NOT NULL THEN toInteger(job.min_experience)
                                ELSE coalesce(j.min_experience, 0)
                              END,
            j.description = coalesce(job.description, j.description),
            j.source = coalesce(job.source, j.source)
          RETURN j
        }
        WITH j, job
        // Attach skills (if any)
        UNWIND COALESCE(job.skills, []) AS skill_name
          WITH j, trim(skill_name) AS skill_name WHERE skill_name <> ""
          MERGE (s:Skill {name: skill_name})
          MERGE (j)-[:REQUIRES_SKILL]->(s)
        RETURN count(DISTINCT j) AS processed_count
        """
        result = tx.run(cypher, job_data=job_data)
        record = result.single()
        return record["processed_count"] if record else 0

    def upload_job_descriptions(self, file_path: str) -> int:
        """
        Parse file and ingest list[dict] of jobs returned by parse_jobs.
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

        if not isinstance(job_data, list):
            print("JobAgent: parse_jobs did not return a list. Aborting.")
            return 0

        self._create_job_constraints()
        print(f"JobAgent: Found {len(job_data)} jobs to ingest. Starting transaction...")

        with self._driver.session() as session:
            try:
                processed_count = session.execute_write(self._ingest_jobs_transaction, job_data)
                print(f"✅ JobAgent: Successfully processed and uploaded {processed_count} jobs to Neo4j.")
                return processed_count
            except Exception as e:
                print(f"❌ JobAgent: Failed to upload jobs to Neo4j. Error: {e}")
                return 0


# CLI entrypoint
def main():
    JOB_DATA_PATH = os.getenv("JOB_DATA_PATH", "jobs_augmented.xlsx")
    job_agent = None
    try:
        print("\n--- Recruiter Agent CLI (Job Ingestion) ---")
        job_agent = JobAgent(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
        print(f"\nAction: Upload Job Descriptions from: {JOB_DATA_PATH}")
        uploaded = job_agent.upload_job_descriptions(JOB_DATA_PATH)
        print("\n--- Summary ---")
        print(f"Job ingestion complete. {uploaded} jobs processed. Check your Neo4j database for nodes.")
    except Exception as e:
        print(f"\n❌ An error occurred during connection or execution: {e}")
    finally:
        if job_agent:
            job_agent.close()


if __name__ == "__main__":
    main()
