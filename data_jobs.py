import pandas as pd
from neo4j import GraphDatabase

driver = GraphDatabase.driver("neo4j+s://d0ee583f.databases.neo4j.io", auth=("neo4j", "qA4mwmqaJbdqQ8BQwU2xUhMnNjG5_OJc01IcXJMc4sU"))
jobs_df = pd.read_csv("linkedin_job_postings.csv")

with driver.session() as session:
    for _, row in jobs_df.iterrows():
        skills = [s.strip() for s in str(row.get("skills", "")).split(",") if s]
        session.run("""
            MERGE (j:Job {title: $title, company: $company})
            SET j.description = $description, j.exp_min = $exp_min, j.exp_max = $exp_max
            WITH j
            UNWIND $skills AS skill
            MERGE (s:Skill {name: toLower(skill)})
            MERGE (j)-[:REQUIRES_SKILL]->(s)
        """, title=row["title"], company=row["company"], description=row["description"],
             exp_min=row.get("exp_min", 0), exp_max=row.get("exp_max", 10), skills=skills)
