# recruiter_agent.py
"""
Recruiter Agent (job ingestion + API sender)

Features:
- Upload job descriptions from a file into Neo4j (ingest_job_descriptions)
- Optionally send parsed jobs to an HTTP /job endpoint instead of writing directly to Neo4j
- Helper methods: send_job_to_api, send_jobs_to_api
"""

from typing import List, Dict, Any, Optional
from neo4j import GraphDatabase
import os
import requests
from requests.exceptions import RequestException

# import parse_jobs from your existing code; expected to return List[Dict]
from parse_jobs import parse_jobs

# --- Neo4j Configuration (use environment variables in production) ---
NEO4J_URI = os.getenv("NEO4J_URI", "neo4j+s://ba7d2a6a.databases.neo4j.io")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "9d20zR-GV-LV43mTEOXlrO-nO_aWR3T0RjpCMSHzOYY")
# -------------------------------------------------------------------


class JobAgent:
    def __init__(self, uri: str = None, user: str = None, password: str = None):
        """
        Initialize the JobAgent with a Neo4j driver connection.
        Uses environment variables by default unless explicit values are provided.
        """
        # allow explicit overrides, else environment/defaults
        uri = uri or os.getenv("NEO4J_URI", NEO4J_URI)  # fallback to env
        user = user or os.getenv("NEO4J_USER", NEO4J_USER)
        password = password or os.getenv("NEO4J_PASSWORD", NEO4J_PASSWORD)

        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        # verify connectivity early
        self._driver.verify_connectivity()
        print("✅ JobAgent: Connected to Neo4j.")

    def close(self):
        """Close the Neo4j connection."""
        try:
            self._driver.close()
        except Exception as e:
            print(f"Warning closing driver: {e}")

    # ----------------------
    # Constraints / Indexes
    # ----------------------
    def _create_job_constraints(self):
        """
        Create constraints and indexes. Note:
        - We DO NOT create a unique constraint on job_id because job_id is forced to 0 per design.
        - We ensure Skill.name uniqueness.
        """
        create_constraints = [
            # Do NOT enforce uniqueness on Job.job_id (we are forcing job_id=0)
            "CREATE CONSTRAINT IF NOT EXISTS FOR (s:Skill) REQUIRE s.name IS UNIQUE"
        ]
        with self._driver.session() as session:
            for c in create_constraints:
                try:
                    session.execute_write(lambda tx, q=c: tx.run(q))
                except Exception as e:
                    print(f"⚠️ Constraint creation warning: {e}")

    # ----------------------
    # Ingestion transaction
    # ----------------------
    def _ingest_jobs_transaction(self, tx, job_data: List[Dict[str, Any]]):
        """
        Accepts job_data: list of dicts. Each dict can include:
          - title, company, description, location, min_experience or experience (text), skills (list), source, posted_date
        Behavior:
          - MERGE on an internal_uid to avoid duplicates (internal_uid = company|title|posting_date)
          - Set j.job_id = 0
          - Set j.ingested_date = date()
          - Store min_experience as integer (toInteger where possible)
          - Create Skill nodes and REQUIRES_SKILL relationships
        Returns: number of processed job nodes
        """
        cypher = """
        UNWIND $job_data AS job
        WITH job WHERE job.title IS NOT NULL AND job.title <> ""
        CALL {
          WITH job
          WITH job,
               (coalesce(job.company,'') + '|' + coalesce(job.title,'') + '|' + coalesce(job.posting_date,'')) AS internal_uid
          MERGE (j:Job {internal_uid: internal_uid})
          SET
            j.title = coalesce(job.title, j.title),
            j.company = coalesce(job.company, j.company),
            j.location = coalesce(job.location, j.location),
            j.job_id = 0,
            j.ingested_date = date(),
            j.min_experience = CASE
                                WHEN job.experience_years IS NOT NULL THEN toInteger(job.experience_years)
                                WHEN job.min_experience IS NOT NULL THEN toInteger(job.min_experience)
                                WHEN job.experience IS NOT NULL THEN 
                                    // attempt to capture numeric prefix if present
                                    toInteger(coalesce(job.experience_years, apoc.text.regexGroups(job.experience,'(\\d+)')[0][0], '0'))
                                ELSE coalesce(j.min_experience, 0)
                              END,
            j.description = coalesce(job.description, j.description),
            j.source = coalesce(job.source, j.source),
            j.posting_date = coalesce(job.posting_date, j.posting_date)
          RETURN j
        }
        WITH j, job
        UNWIND COALESCE(job.skills, []) AS skill_name
          WITH j, trim(skill_name) AS skill_name WHERE skill_name <> ""
          MERGE (s:Skill {name: skill_name})
          MERGE (j)-[:REQUIRES_SKILL]->(s)
        RETURN count(DISTINCT j) AS processed_count
        """
        # Note: we used apoc.text.regexGroups in the cypher above; if your DB doesn't have APOC installed,
        # you'd need to avoid the apoc call. To be safe, we'll fallback to a simpler version that avoids APOC.
        # Use a fallback cypher without APOC if APOC isn't present.
        fallback_cypher = """
        UNWIND $job_data AS job
        WITH job WHERE job.title IS NOT NULL AND job.title <> ""
        CALL {
          WITH job
          WITH job,
               (coalesce(job.company,'') + '|' + coalesce(job.title,'') + '|' + coalesce(job.posting_date,'')) AS internal_uid
          MERGE (j:Job {internal_uid: internal_uid})
          SET
            j.title = coalesce(job.title, j.title),
            j.company = coalesce(job.company, j.company),
            j.location = coalesce(job.location, j.location),
            j.job_id = 0,
            j.ingested_date = date(),
            j.min_experience = CASE
                                WHEN job.experience_years IS NOT NULL THEN toInteger(job.experience_years)
                                WHEN job.min_experience IS NOT NULL THEN toInteger(job.min_experience)
                                WHEN job.experience IS NOT NULL THEN toInteger(coalesce(job.experience_years, 0))
                                ELSE coalesce(j.min_experience, 0)
                              END,
            j.description = coalesce(job.description, j.description),
            j.source = coalesce(job.source, j.source),
            j.posting_date = coalesce(job.posting_date, j.posting_date)
          RETURN j
        }
        WITH j, job
        UNWIND COALESCE(job.skills, []) AS skill_name
          WITH j, trim(skill_name) AS skill_name WHERE skill_name <> ""
          MERGE (s:Skill {name: skill_name})
          MERGE (j)-[:REQUIRES_SKILL]->(s)
        RETURN count(DISTINCT j) AS processed_count
        """

        # Try the more featureful query first (it may fail if APOC not present)
        try:
            result = tx.run(cypher, job_data=job_data)
            rec = result.single()
            return rec["processed_count"] if rec else 0
        except Exception:
            # fallback to safer query without apoc usage
            result = tx.run(fallback_cypher, job_data=job_data)
            rec = result.single()
            return rec["processed_count"] if rec else 0

    # ----------------------
    # Public ingestion method
    # ----------------------
    def upload_job_descriptions(self,
                                file_path: str,
                                use_api: bool = False,
                                api_url: Optional[str] = None,
                                continue_on_error: bool = True) -> Dict[str, Any]:
        """
        Parse the input file and either:
          - Ingest directly into Neo4j (default), or
          - Send each parsed job to a remote /job API endpoint (use_api=True)

        Returns:
          If use_api=False: {"processed": N}
          If use_api=True: {"sent": n_sent, "failed": n_failed, "failures":[...]}
        """
        if not os.path.exists(file_path):
            print(f"❌ File not found: {file_path}")
            return {"processed": 0}

        print(f"JobAgent: Parsing job descriptions from {file_path}...")
        try:
            job_data = parse_jobs(file_path)
        except Exception as e:
            print(f"❌ Error parsing file: {e}")
            return {"processed": 0}

        if not job_data or not isinstance(job_data, list):
            print("JobAgent: No valid jobs parsed or parse_jobs did not return a list.")
            return {"processed": 0}

        # Optionally send to API instead of direct ingestion
        if use_api:
            summary = self.send_jobs_to_api(job_data, api_url=api_url, continue_on_error=continue_on_error)
            print(f"JobAgent: Sent {summary.get('sent',0)} jobs, failed {summary.get('failed',0)}")
            return summary

        # Direct Neo4j ingestion
        self._create_job_constraints()
        print(f"JobAgent: Found {len(job_data)} jobs to ingest. Starting transaction...")

        with self._driver.session() as session:
            try:
                processed_count = session.execute_write(self._ingest_jobs_transaction, job_data)
                print(f"✅ JobAgent: Successfully processed and uploaded {processed_count} jobs to Neo4j.")
                return {"processed": processed_count}
            except Exception as e:
                print(f"❌ JobAgent: Failed to upload jobs to Neo4j. Error: {e}")
                return {"processed": 0}

    # ----------------------
    # HTTP helpers (send to external /job API)
    # ----------------------
    def send_job_to_api(self,
                        job_dict: Dict[str, Any],
                        api_url: Optional[str] = None,
                        timeout: int = 10) -> Optional[Dict[str, Any]]:
        """
        Send one job dict to the /job endpoint (HTTP).
        - job_dict: expected keys: title, company/company_name, description, location, experience_years (int) or experience (str), etc.
        - api_url: full URL to POST to (defaults to env JOB_API_URL or http://localhost:8000/job)
        Returns parsed JSON on success, or None on failure.
        """
        if api_url is None:
            api_url = os.getenv("JOB_API_URL", "http://localhost:8000/job")

        # Build payload with sensible keys for the API
        payload: Dict[str, Any] = {
            "title": job_dict.get("title") or job_dict.get("job_title") or "",
            "company_name": job_dict.get("company") or job_dict.get("company_name") or "",
            "description": job_dict.get("description") or job_dict.get("job_description") or "",
            "location": job_dict.get("location") or ""
        }

        # Experience: prefer explicit integer "experience_years"
        if "experience_years" in job_dict and job_dict.get("experience_years") is not None:
            try:
                payload["experience_years"] = int(job_dict.get("experience_years"))
            except Exception:
                payload["experience_years"] = 0
        else:
            # pass textual experience if available (API will parse)
            if job_dict.get("experience") is not None:
                payload["experience"] = str(job_dict.get("experience"))

        # include optional fields if present
        optional = ["education", "category", "domain", "posted_date", "posting_date", "source", "skills"]
        for k in optional:
            if k in job_dict and job_dict.get(k) is not None:
                payload[k] = job_dict.get(k)

        headers = {"Content-Type": "application/json"}

        try:
            resp = requests.post(api_url, json=payload, headers=headers, timeout=timeout)
            resp.raise_for_status()
            try:
                return resp.json()
            except ValueError:
                return {"raw_response": resp.text}
        except RequestException as e:
            print(f"❌ send_job_to_api: failed to POST to {api_url}: {e}")
            if hasattr(e, "response") and e.response is not None:
                try:
                    print("Response status:", e.response.status_code, "text:", e.response.text)
                except Exception:
                    pass
            return None

    def send_jobs_to_api(self,
                         job_list: List[Dict[str, Any]],
                         api_url: Optional[str] = None,
                         continue_on_error: bool = True) -> Dict[str, Any]:
        """
        Send multiple jobs to the API one-by-one.
        Returns summary: {"sent": n_sent, "failed": n_failed, "failures": [...]}
        """
        summary = {"sent": 0, "failed": 0, "failures": []}
        for idx, job in enumerate(job_list):
            res = self.send_job_to_api(job, api_url=api_url)
            if res is None:
                summary["failed"] += 1
                summary["failures"].append({"index": idx, "job": job})
                print(f"⚠️ send_jobs_to_api: job at index {idx} failed to send.")
                if not continue_on_error:
                    raise RuntimeError(f"Failed to send job at index {idx} to API")
            else:
                summary["sent"] += 1
        return summary


# ----------------------
# CLI / script entry
# ----------------------
def main():
    JOB_DATA_PATH = os.getenv("JOB_DATA_PATH", "jobs_augmented.xlsx")
    job_agent = None
    try:
        print("\n--- Recruiter Agent CLI (Job Ingestion) ---")
        job_agent = JobAgent()
        print(f"Action: upload from {JOB_DATA_PATH}")
        result = job_agent.upload_job_descriptions(JOB_DATA_PATH, use_api=False)
        print("Result:", result)
    except Exception as e:
        print(f"❌ Error in main: {e}")
    finally:
        if job_agent:
            job_agent.close()


if __name__ == "__main__":
    main()
