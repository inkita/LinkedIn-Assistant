# recruiter_agent.py
"""
Recruiter Agent (job ingestion + API sender)

Fixes:
- Preserve jobs that have no skills (so they are counted as processed)
  by replacing UNWIND COALESCE(job.skills, []) with a FOREACH pattern
  that conditionally creates Skill nodes only when non-empty.
- Keep Excel fallback parsing and debug prints.
- Preserve original behavior and APIs.
"""

from typing import List, Dict, Any, Optional
from neo4j import GraphDatabase
import os
import requests
from requests.exceptions import RequestException
import pandas as pd
import re

# import parse_jobs from your existing code; expected to return List[Dict]
from parse_jobs import parse_jobs

# --- Neo4j Configuration (use environment variables in production) ---
NEO4J_URI = os.getenv("NEO4J_URI", "neo4j+s://ba7d2a6a.databases.neo4j.io")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "9d20zR-GV-LV43mTEOXlrO-nO_aWR3T0RjpCMSHzOYY")
# -------------------------------------------------------------------


class JobAgent:
    def __init__(self, uri: str = None, user: str = None, password: str = None):
        uri = uri or os.getenv("NEO4J_URI", NEO4J_URI)
        user = user or os.getenv("NEO4J_USER", NEO4J_USER)
        password = password or os.getenv("NEO4J_PASSWORD", NEO4J_PASSWORD)

        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._driver.verify_connectivity()
        print("✅ JobAgent: Connected to Neo4j.")

    def close(self):
        try:
            self._driver.close()
        except Exception as e:
            print(f"Warning closing driver: {e}")

    def _create_job_constraints(self):
        create_constraints = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (s:Skill) REQUIRE s.norm_name IS UNIQUE",
            "CREATE INDEX IF NOT EXISTS FOR (j:Job) ON (j.internal_uid)"
        ]
        with self._driver.session() as session:
            for c in create_constraints:
                try:
                    session.execute_write(lambda tx, q=c: tx.run(q))
                except Exception as e:
                    print(f"⚠️ Constraint/index creation warning: {e}")

    def _ingest_jobs_transaction(self, tx, job_data: List[Dict[str, Any]]):
        """
        Ingest job_data, MERGE Job nodes by internal_uid, and attach Skill nodes.
        Uses FOREACH to ensure jobs with empty/no skills are still counted.
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
        // keep job in scope and use FOREACH to conditionally create skill nodes
        WITH j, job
        // iterate skill_name_raw over either job.skills or a single NULL item if no skills
        FOREACH (skill_name_raw IN CASE WHEN job.skills IS NULL OR size(job.skills)=0 THEN [NULL] ELSE job.skills END |
           // nested FOREACH runs only when skill_name_raw is not NULL/empty (guard)
           FOREACH (_ IN CASE WHEN skill_name_raw IS NULL OR trim(skill_name_raw) = '' THEN [] ELSE [1] END |
               MERGE (s:Skill {norm_name: toLower(trim(skill_name_raw))})
               ON CREATE SET s.name = skill_name_raw, s.created_at = date(), s.aliases = coalesce(job.skill_aliases, [])
               ON MATCH SET s.name = coalesce(s.name, skill_name_raw)
               MERGE (j)-[:REQUIRES_SKILL]->(s)
           )
        )
        RETURN count(DISTINCT j) AS processed_count
        """

        try:
            result = tx.run(cypher, job_data=job_data)
            rec = result.single()
            return rec["processed_count"] if rec else 0
        except Exception as e:
            print("❌ Ingest transaction failed:", e)
            raise

    def upload_job_descriptions(self,
                                file_path: str,
                                use_api: bool = False,
                                api_url: Optional[str] = None,
                                continue_on_error: bool = True) -> Dict[str, Any]:
        if not os.path.exists(file_path):
            print(f"❌ File not found: {file_path}")
            return {"processed": 0}

        print(f"JobAgent: Parsing job descriptions from {file_path}...")
        job_data = None
        try:
            job_data = parse_jobs(file_path)
        except Exception as e:
            print(f"⚠️ parse_jobs threw an exception: {e}")

        if not job_data or not isinstance(job_data, list) or len(job_data) == 0:
            print("JobAgent: parse_jobs returned empty or invalid. Attempting to read Excel directly and infer columns...")
            try:
                df = pd.read_excel(file_path)
                df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
                df.rename(columns={
                    "company_name": "company",
                    "posted_date": "posting_date",
                }, inplace=True)

                if "skills" not in df.columns:
                    df["skills"] = [""] * len(df)
                df.fillna("", inplace=True)

                jobs_out = []
                for _, row in df.iterrows():
                    title = str(row.get("title", "")).strip()
                    if not title:
                        continue
                    j = {
                        "title": title,
                        "company": str(row.get("company", "")).strip(),
                        "description": str(row.get("description", "")).strip(),
                        "location": str(row.get("location", "")).strip(),
                        "posting_date": str(row.get("posting_date", "")).strip(),
                    }
                    exp_val = row.get("experience", "")
                    exp_years = None
                    try:
                        if pd.notna(exp_val) and str(exp_val).strip() != "":
                            s = str(exp_val).strip()
                            m = re.search(r"(\d+)", s)
                            if m:
                                exp_years = int(m.group(1))
                    except Exception:
                        exp_years = None
                    j["experience_years"] = exp_years
                    j["experience"] = str(row.get("experience", "")).strip() or None

                    raw_skills = row.get("skills", "")
                    skills_val = []
                    if isinstance(raw_skills, str) and raw_skills.strip():
                        parts = [p.strip() for p in re.split(r"[,;]", raw_skills) if p.strip()]
                        skills_val = parts
                    elif isinstance(raw_skills, (list, tuple)):
                        skills_val = [str(x).strip() for x in raw_skills if x and str(x).strip()]
                    elif raw_skills:
                        skills_val = [str(raw_skills).strip()]

                    j["skills"] = skills_val
                    jobs_out.append(j)

                job_data = jobs_out
                print(f"JobAgent: Inferred {len(job_data)} jobs from Excel. Sample:", job_data[:2])
            except Exception as e:
                print(f"❌ Failed to read/parse Excel fallback: {e}")
                job_data = []

        if not job_data or not isinstance(job_data, list):
            print("JobAgent: No valid jobs parsed or parse_jobs did not return a list.")
            return {"processed": 0}

        if use_api:
            summary = self.send_jobs_to_api(job_data, api_url=api_url, continue_on_error=continue_on_error)
            print(f"JobAgent: Sent {summary.get('sent',0)} jobs, failed {summary.get('failed',0)}")
            return summary

        try:
            self._create_job_constraints()
        except Exception as e:
            print("⚠️ Warning creating constraints:", e)

        print(f"JobAgent: Found {len(job_data)} jobs to ingest. Starting transaction...")

        with self._driver.session() as session:
            try:
                processed_count = session.execute_write(self._ingest_jobs_transaction, job_data)
                print(f"✅ JobAgent: Successfully processed and uploaded {processed_count} jobs to Neo4j.")
                return {"processed": processed_count}
            except Exception as e:
                print(f"❌ JobAgent: Failed to upload jobs to Neo4j. Error: {e}")
                return {"processed": 0}

    def send_job_to_api(self,
                        job_dict: Dict[str, Any],
                        api_url: Optional[str] = None,
                        timeout: int = 10) -> Optional[Dict[str, Any]]:
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


def main():
    JOB_DATA_PATH = os.getenv("JOB_DATA_PATH", "jobs_augmented.xlsx")
    job_agent = None
    try:
        print("\n--- Recruiter Agent CLI (Job Ingestion) ---")
        job_agent = JobAgent()
        print(f"Action: upload from {JOB_DATA_PATH}")
        res = job_agent.upload_job_descriptions(JOB_DATA_PATH, use_api=False)
        print("Result:", res)
    except Exception as e:
        print(f"❌ Error in main: {e}")
    finally:
        if job_agent:
            job_agent.close()


if __name__ == "__main__":
    main()
