# candidate_agent.py
from neo4j import GraphDatabase
from typing import List, Dict
import pandas as pd
import os

# Assuming parse_jobs.py is available in the same directory 
from parse_jobs import _split_skills 

# --- CONFIGURATION (Ensure these match your recruiter_agent.py) ---
NEO4J_URI = "neo4j+s://d0ee583f.databases.neo4j.io"  
NEO4J_USER = "neo4j"                 
NEO4J_PASSWORD = "qA4mwmqaJbdqQ8BQwU2xUhMnNjG5_OJc01IcXJMc4sU"          
# ------------------------------------------------------------------

class CandidateAgent:
    """
    Handles candidate data ingestion and candidate search queries against 
    the Neo4j Knowledge Graph using standard Cypher.
    """
    def __init__(self, uri, user, password):
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._driver.verify_connectivity()
        print("✅ CandidateAgent: Connected to Neo4j.")

    def close(self):
        self._driver.close()

    def _ingest_candidates_transaction(self, tx, candidate_data: List[Dict]):
        """Cypher query to create Candidate and HAS_SKILL relationships."""
        cypher_query = """
        UNWIND $candidates as cand
        MERGE (c:Candidate {candidate_id: cand.candidate_id})
        ON CREATE SET c.name = cand.name, c.email = cand.email, c.location = cand.location
        
        FOREACH (skill_name IN cand.skills |
            MERGE (s:Skill {name: skill_name})
            MERGE (c)-[:HAS_SKILL]->(s)
        )
        RETURN count(c) AS candidates_processed
        """
        result = tx.run(cypher_query, candidates=candidate_data)
        return result.single()["candidates_processed"]

    def upload_candidates(self, file_path: str, columns_map: Dict[str, str]) -> int:
        """Reads candidate data from an Excel file and ingests into Neo4j."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Candidate file not found: {file_path}")
            
        print(f"CandidateAgent: Parsing candidate data from {file_path}...")
        
        try:
            df = pd.read_excel(file_path)
            df.rename(columns=columns_map, inplace=True)
            
            if 'skills' in df.columns:
                df['skills'] = df['skills'].apply(_split_skills)
            
            df['candidate_id'] = df['candidate_id'].fillna(df.index).astype(str)
            df['name'] = df['name'].fillna("Unknown Candidate")
            df['email'] = df['email'].fillna("")
            df['location'] = df['location'].fillna("")
            
            required_cols = ['candidate_id', 'name', 'skills', 'email', 'location']
            candidate_data = df[[col for col in required_cols if col in df.columns]].to_dict('records')

        except Exception as e:
            print(f"❌ CandidateAgent: Error during file parsing/preparation: {e}")
            return 0
            
        if not candidate_data:
            print("CandidateAgent: No valid candidates parsed. Skipping upload.")
            return 0

        with self._driver.session() as session:
            try:
                processed_count = session.execute_write(
                    self._ingest_candidates_transaction, candidate_data
                )
                print(f"✅ CandidateAgent: Successfully processed and uploaded {processed_count} candidates to Neo4j.")
                return processed_count
            except Exception as e:
                print(f"❌ CandidateAgent: Failed to upload candidates to Neo4j. Error: {e}")
                return 0


    def search_candidates_by_skills(self, required_skills: List[str], max_results: int = 10) -> List[Dict]:
        """
        Finds and ranks candidates based on the number of matching skills 
        using standard Cypher (CONTAINS operator).
        """
        
        if not required_skills:
            return []
            
        lower_skills = [s.lower() for s in required_skills]
        
        # --- STANDARD CYPHER QUERY (NO APOC) ---
        cypher_query = """
        // 1. Get all candidates and their skills in lowercase
        MATCH (c:Candidate)-[:HAS_SKILL]->(s:Skill)
        WITH c, collect(toLower(s.name)) AS candidateSkills, collect(s.name) AS allSkills

        // 2. Count the number of required skills that are CONTAINED within the candidate's skills list
        WITH c, allSkills, candidateSkills, $lowerSkills AS requiredSkills
        
        WITH c, allSkills, 
             // Count how many required skills match a candidate skill (using a simple CONTAINS logic)
             size([
                 r_skill IN requiredSkills
                 // Check if any candidate skill CONTAINS the required skill
                 WHERE size([c_skill IN candidateSkills WHERE c_skill CONTAINS r_skill]) > 0
                 | 1
             ]) AS matchedSkillsCount
        
        // 3. Filter out candidates with zero matches and rank
        WHERE matchedSkillsCount > 0
        
        RETURN 
            c.candidate_id AS id, 
            c.name AS name,
            c.location AS location,
            matchedSkillsCount,
            allSkills AS skills 
        ORDER BY matchedSkillsCount DESC
        LIMIT $maxResults
        """
        # ----------------------------------------
        
        with self._driver.session() as session:
            result = session.run(cypher_query, 
                                 lowerSkills=lower_skills, 
                                 maxResults=max_results)
            return [record.data() for record in result]