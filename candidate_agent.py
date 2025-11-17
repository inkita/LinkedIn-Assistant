# candidate_agent.py
from neo4j import GraphDatabase
from typing import List, Dict, Any
import pandas as pd
import os
import re
import ast

# Assuming parse_jobs.py exports _split_skills used for ingestion
from parse_jobs import _split_skills

# --- CONFIGURATION (Ensure these match your recruiter_agent.py) ---
NEO4J_URI = os.getenv("NEO4J_URI", "neo4j+s://d0ee583f.databases.neo4j.io")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "qA4mwmqaJbdqQ8BQwU2xUhMnNjG5_OJc01IcXJMc4sU")
# ------------------------------------------------------------------


def _normalize_text(s: str) -> str:
    """Lowercase, remove punctuation (keep alphanumerics and spaces), collapse whitespace."""
    if s is None:
        return ""
    s = str(s).lower()
    # remove non-alphanumeric characters except spaces
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    # collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _ensure_skill_list(skills_input) -> List[str]:
    """
    Accepts:
      - a Python list of strings
      - a string that looks like a Python list "['a','b']"
      - a comma-separated string "a, b"
    Returns normalized list of non-empty skill strings (original form).
    """
    if skills_input is None:
        return []
    if isinstance(skills_input, list):
        return [s for s in skills_input if s and str(s).strip()]
    if isinstance(skills_input, str):
        # try literal_eval for "['a','b']" style
        try:
            parsed = ast.literal_eval(skills_input)
            if isinstance(parsed, list):
                return [str(s) for s in parsed if s and str(s).strip()]
        except Exception:
            # fallback: comma-split
            parts = [p.strip() for p in skills_input.split(",") if p.strip()]
            return parts
    # fallback
    return [str(skills_input).strip()]


class CandidateAgent:
    """
    Handles candidate data ingestion and candidate search queries against 
    the Neo4j Knowledge Graph using standard Cypher.
    """
    def __init__(self, uri: str, user: str, password: str):
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._driver.verify_connectivity()
        print("✅ CandidateAgent: Connected to Neo4j.")

    def close(self):
        self._driver.close()

    def _ingest_candidates_transaction(self, tx, candidate_data: List[Dict[str, Any]]):
        """Cypher query to create Candidate and HAS_SKILL relationships."""
        cypher_query = """
        UNWIND $candidates as cand
        MERGE (c:Candidate {candidate_id: cand.candidate_id})
        ON CREATE SET c.name = cand.name, c.email = cand.email, c.location = cand.location
        // For update cases, set name/location/email as well (optional)
        ON MATCH SET c.name = coalesce(cand.name, c.name), c.location = coalesce(cand.location, c.location), c.email = coalesce(cand.email, c.email)
        
        FOREACH (skill_name IN cand.skills |
            MERGE (s:Skill {name: skill_name})
            MERGE (c)-[:HAS_SKILL]->(s)
        )
        RETURN count(DISTINCT c) AS candidates_processed
        """
        result = tx.run(cypher_query, candidates=candidate_data)
        rec = result.single()
        return rec["candidates_processed"] if rec else 0

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

            df['candidate_id'] = df.get('candidate_id', df.index).fillna(df.index).astype(str)
            df['name'] = df.get('name', pd.Series(["Unknown Candidate"] * len(df))).fillna("Unknown Candidate")
            df['email'] = df.get('email', pd.Series([""] * len(df))).fillna("")
            df['location'] = df.get('location', pd.Series([""] * len(df))).fillna("")

            required_cols = ['candidate_id', 'name', 'skills', 'email', 'location']
            # ensure skills column exists
            if 'skills' not in df.columns:
                df['skills'] = [[] for _ in range(len(df))]

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

    def _fetch_all_candidates_with_skills(self) -> List[Dict[str, Any]]:
        """Fetch all candidates and their skill names from Neo4j."""
        cypher = """
        MATCH (c:Candidate)
        OPTIONAL MATCH (c)-[:HAS_SKILL]->(s:Skill)
        WITH c, collect(DISTINCT s.name) AS skills
        RETURN c.candidate_id AS candidate_id, c.name AS name, c.location AS location, skills
        """
        with self._driver.session() as session:
            result = session.run(cypher)
            return [r.data() for r in result]

    def search_candidates_by_skills(self, required_skills, max_results: int = 10, debug: bool = False) -> List[Dict[str, Any]]:
        """
        Finds and ranks candidates based on the number of matching skills.

        Matching logic (for each required skill vs each candidate skill):
          - normalize both (lowercase, strip punctuation)
          - consider a match if:
              * norm(required) == norm(candidate_skill)
              * norm(required) in norm(candidate_skill) OR norm(candidate_skill) in norm(required)
              * at least one token overlaps (token intersection)
        Returns list of dicts:
          { id, name, location, matchedSkillsCount, skills }
        """
        # Normalize input & ensure list
        if not required_skills:
            return []

        # If a single string is provided, try to parse it into a list
        if isinstance(required_skills, str):
            required_skills = _ensure_skill_list(required_skills)

        # Guarantee list of non-empty strings
        required_skills = [str(s).strip() for s in required_skills if s and str(s).strip()]
        if not required_skills:
            return []

        # Precompute normalized required skills
        norm_required = [ _normalize_text(s) for s in required_skills ]
        if debug:
            print("DEBUG: required_skills:", required_skills)
            print("DEBUG: norm_required:", norm_required)

        # Fetch candidates and their skills (do the matching in Python for flexible heuristics)
        candidates = self._fetch_all_candidates_with_skills()
        scored = []

        for cand in candidates:
            cand_skills = cand.get('skills') or []
            # normalize candidate skills
            norm_cand_skills = [ _normalize_text(s) for s in cand_skills ]
            matched_skill_names = set()

            for i, r_raw in enumerate(required_skills):
                r_norm = norm_required[i]
                if not r_norm:
                    continue

                # check against each candidate skill
                for orig_skill, c_norm in zip(cand_skills, norm_cand_skills):
                    if not c_norm:
                        continue
                    matched = False

                    # exact normalized match
                    if r_norm == c_norm:
                        matched = True

                    # substring containment either way
                    elif r_norm in c_norm or c_norm in r_norm:
                        matched = True

                    else:
                        # token overlap check
                        r_tokens = set(r_norm.split())
                        c_tokens = set(c_norm.split())
                        if r_tokens & c_tokens:
                            matched = True

                    if matched:
                        matched_skill_names.add(orig_skill)
                        # once this required skill matches a candidate skill, stop checking other candidate skills for this required skill
                        break

            matched_count = len(matched_skill_names)
            if matched_count > 0:
                scored.append({
                    "id": cand.get("candidate_id"),
                    "name": cand.get("name"),
                    "location": cand.get("location"),
                    "matchedSkillsCount": matched_count,
                    "skills": cand_skills
                })
                if debug:
                    print(f"DEBUG matched for candidate {cand.get('name')}: {matched_skill_names}")

        # sort by matchedSkillsCount descending and return top N
        scored_sorted = sorted(scored, key=lambda x: x["matchedSkillsCount"], reverse=True)
        return scored_sorted[:max_results]
