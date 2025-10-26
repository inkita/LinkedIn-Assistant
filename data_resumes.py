import pandas as pd
from neo4j import GraphDatabase

driver = GraphDatabase.driver("neo4j+s://d0ee583f.databases.neo4j.io", auth=("neo4j", "qA4mwmqaJbdqQ8BQwU2xUhMnNjG5_OJc01IcXJMc4sU"))   
resumes_df = pd.read_csv("Resumes.csv")

with driver.session() as session:
    for _, row in resumes_df.iterrows():
        skills = [s.strip() for s in str(row["skills"]).split(",") if s]
        session.run("""
            MERGE (c:Candidate {name: $name})
            SET c.experience = $experience, c.email = $email
            WITH c
            UNWIND $skills AS skill
            MERGE (s:Skill {name: toLower(skill)})
            MERGE (c)-[:HAS_SKILL]->(s)
        """, name=row["name"], email=row["email"], experience=row.get("experience", 0), skills=skills)
