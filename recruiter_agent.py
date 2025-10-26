import json
from neo4j import GraphDatabase
from parser import parse_job_description
import os
from dotenv import load_dotenv

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "neo4j+s://d0ee583f.databases.neo4j.io")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASS", "qA4mwmqaJbdqQ8BQwU2xUhMnNjG5_OJc01IcXJMc4sU")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))


def insert_job(job_json):
    """Insert parsed JD into Neo4j"""
    with driver.session() as session:
        session.run("""
            MERGE (j:Job {title: $title, company: $company})
            SET j.exp_min = $exp_min, j.exp_max = $exp_max,
                j.degree_level = $degree_level, j.field = $preferred_field,
                j.description = $description
            WITH j
            UNWIND $skills_required AS skill
            MERGE (s:Skill {name: toLower(skill)})
            MERGE (j)-[:REQUIRES_SKILL]->(s);
        """, **job_json)


def match_candidates(job_title):
    """Find candidates that best fit a given job title"""
    with driver.session() as session:
        result = session.run("""
            MATCH (j:Job {title: $title})
            MATCH (c:Candidate)-[:HAS_SKILL]->(s:Skill)<-[:REQUIRES_SKILL]-(j)
            WHERE c.experience >= j.exp_min AND c.experience <= j.exp_max
            OPTIONAL MATCH (c)-[:STUDIED_AT]->(i:Institution)
            RETURN c.name AS Candidate, c.email AS Email,
                   count(DISTINCT s) AS skillMatches,
                   c.experience AS Years,
                   i.name AS Institution,
                   i.degree_level AS Degree
            ORDER BY skillMatches DESC, Years ASC
            LIMIT 10;
        """, title=job_title)
        return result.data()


def missing_skills(job_title, candidate_email):
    """Return skills missing in a candidate for a given job"""
    with driver.session() as session:
        result = session.run("""
            MATCH (j:Job {title: $title})-[:REQUIRES_SKILL]->(s:Skill)
            WHERE NOT EXISTS(
                ( :Candidate {email: $email})-[:HAS_SKILL]->(s)
            )
            RETURN collect(s.name) AS missingSkills
        """, title=job_title, email=candidate_email)
        data = result.single()
        return data["missingSkills"] if data else []
