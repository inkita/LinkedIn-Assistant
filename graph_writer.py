# graph_writer.py
from typing import List, Optional
from neo4j import GraphDatabase

class GraphWriter:
    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        with self.driver.session() as s:
            s.run("RETURN 1")

    def close(self):
        self.driver.close()

    def merge_candidate(self, name: Optional[str], email: Optional[str], skills: List[str]):
        email = email or "unknown@local"
        skills = [s.strip() for s in (skills or []) if s and s.strip()]
        with self.driver.session() as session:
            session.run(
                """
                MERGE (c:Candidate {email:$email})
                ON CREATE SET c.name = $name
                ON MATCH  SET c.name = coalesce(c.name, $name)
                WITH c, $skills AS skills
                UNWIND skills AS raw
                WITH c, toLower(trim(raw)) AS sname
                MERGE (s:Skill {name:sname})
                MERGE (c)-[:HAS_SKILL]->(s)
                """,
                name=name, email=email, skills=skills
            )

    def merge_job(self, job_id: str, title: str, company: str, location: str, skills: List[str]):
        skills = [s.strip() for s in (skills or []) if s and s.strip()]
        with self.driver.session() as session:
            session.run(
                """
                MERGE (j:Job {job_id: $job_id})
                ON CREATE SET j.title=$title, j.company=$company, j.location=$location
                ON MATCH  SET j.title=$title, j.company=$company, j.location=$location
                WITH j, $skills AS skills
                UNWIND skills AS raw
                WITH j, toLower(trim(raw)) AS sname
                MERGE (sk:Skill {name:sname})
                MERGE (j)-[:REQUIRES]->(sk)
                """,
                job_id=job_id, title=title or "Unknown", company=company or "Unknown",
                location=location or "", skills=skills
            )
