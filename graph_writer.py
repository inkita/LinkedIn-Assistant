from neo4j import GraphDatabase

class GraphWriter:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        # quick connectivity ping
        with self.driver.session() as s:
            s.run("RETURN 1")

    def close(self):
        self.driver.close()

    def merge_candidate(self, name, email, skills):
        with self.driver.session() as session:
            session.run(
                "MERGE (c:Candidate {email:$email}) "
                "ON CREATE SET c.name=$name "
                "ON MATCH SET c.name=coalesce(c.name, $name)",
                name=name, email=email
            )
            for s in skills:
                session.run(
                    "MERGE (sk:Skill {name:$skill}) "
                    "WITH sk "
                    "MATCH (c:Candidate {email:$email}) "
                    "MERGE (c)-[:HAS_SKILL]->(sk)",
                    email=email, skill=s
                )

    def merge_job(self, title, company, skills):
        with self.driver.session() as session:
            session.run(
                "MERGE (j:Job {title:$title, company:$company})",
                title=title, company=company
            )
            for s in skills:
                session.run(
                    "MERGE (sk:Skill {name:$skill}) "
                    "WITH sk "
                    "MATCH (j:Job {title:$title, company:$company}) "
                    "MERGE (j)-[:REQUIRES_SKILL]->(sk)",
                    title=title, company=company, skill=s
                )
