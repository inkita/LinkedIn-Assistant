# recruiter_agent.py
"""
Recruiter Agent (job ingestion + API sender)

Minimal schema-aware improvements:
- Ensure Skill.norm_name is created and unique (used by candidate scoring)
- Preserve original name, set aliases if provided, set created_at when created
- Optionally compute Skill.popularity during ingestion (lightweight)
All other behaviors (internal_uid merge, j.job_id = 0, API helpers) are unchanged.
"""

from typing import List, Dict, Any, Optional
from neo4j import GraphDatabase
import os
import requests
from requests.exceptions import RequestException
from datetime import datetime

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
        uri = uri or os.getenv("NEO4J_URI", NEO4J_URI)
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
        Create constraints and indexes.
        - Ensure Skill.norm_name uniqueness (canonical skill identifier).
        - Index on Job.internal_uid for faster MERGE.
        """
        create_statements = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (s:Skill) REQUIRE s.norm_name IS UNIQUE",
            "CREATE INDEX IF NOT EXISTS FOR (j:Job) ON (j.internal_uid)"
        ]
        with self._driver.session() as session:
            for stmt in create_statements:
                try:
                    session.execute_write(lambda tx, q=stmt: tx.run(q))
                except Exception as e:
                    # non-fatal: print warning and continue
                    print(f"⚠️ Constraint/index creation warning: {e}")

    # ----------------------
    # Ingestion transaction
    # ----------------------
    def _ingest_jobs_transaction(self, tx, job_data: List[Dict[str, Any]]):
        """
        Ingest job_data into the graph. Each job dict may include:
        title, company, description, location, min_experience or experience, skills (list), skill_aliases (list or dict), source, posting_date
        Skill nodes are created/merged by norm_name and store:
          - name (original)
          - norm_name (lower(trim(name)))
          - aliases (list) if provided
          - created_at (date) when node created
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
                                WHEN job.experience IS NOT NULL THEN toInteger(coalesce(job.experience_years, 0))
                                ELSE coalesce(j.min_experience, 0)
                              END,
            j.description = coalesce(job.description, j.description),
            j.source = coalesce(job.source, j.source),
            j.posting_date = coalesce(job.posting_date, j.posting_date)
          RETURN j
        }
        WITH j, job
        UNWIND COALESCE(job.skills, []) AS skill_name_raw
          WITH j, trim(skill_name_raw) AS skill_name, job WHERE skill_name <> ""
          // canonical norm (lower + trim)
          MERGE (s:Skill {norm_name: toLower(trim(skill_name))})
          ON CREATE SET s.name = skill_name,
                        s.aliases = coalesce(job.skill_aliases, []),
                        s.created_at = date()
          ON MATCH SET s.name = coalesce(s.name, skill_name)
          MERGE (j)-[:REQUIRES_SKILL]->(s)
        RETURN count(DISTINCT j) AS processed_count
        """

        # fallback (same logic but simpler) kept for safety
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
        UNWIND COALESCE(job.skills, []) AS skill_name_raw
          WITH j, trim(skill_name_raw) AS skill_name, job WHERE skill_name <> ""
          MERGE (s:Skill {norm_name: toLower(trim(skill_name))})
          ON CREATE SET s.name = skill_name,
                        s.aliases = coalesce(job.skill_aliases, []),
                        s.created_at = date()
          ON MATCH SET s.name = coalesce(s.name, skill_name)
          MERGE (j)-[:REQUIRES_SKILL]->(s)
        RETURN count(DISTINCT j) AS processed_count
        """

        try:
            res = tx.run(cypher, job_data=job_data)
            rec = res.single()
            return rec["processed_count"] if rec else 0
        except Exception:
            # fallback when advanced query fails for any reason
            res = tx.run(fallback_cypher, job_data=job_data)
            rec = res.single()
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
                # Optionally: update popularity for skills (lightweight) - commented by default
                # session.execute_write(self._update_skill_popularity)
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
        Returns parsed JSON on success, or None on failure.
        """
        if api_url is None:
            api_url = os.getenv("JOB_API_URL", "http://localhost:8000/job")

        payload: Dict[str, Any] = {
            "title": job_dict.get("title") or job_dict.get("job_title") or "",
            "company_name": job_dict.get("company") or job_dict.get("company_name") or "",
            "description": job_dict.get("description") or job_dict.get("job_description") or "",
            "location": job_dict.get("location") or ""
        }

        if "experience_years" in job_dict and job_dict.get("experience_years") is not None:
            try:
                payload["experience_years"] = int(job_dict.get("experience_years"))
            except Exception:
                payload["experience_years"] = 0
        else:
            if job_dict.get("experience") is not None:
                payload["experience"] = str(job_dict.get("experience"))

        optional = ["education", "category", "domain", "posted_date", "posting_date", "source", "skills", "skill_aliases"]
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
