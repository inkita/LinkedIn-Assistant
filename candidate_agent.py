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
NEO4J_URI = os.getenv("NEO4J_URI", "neo4j+s://ba7d2a6a.databases.neo4j.io")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "9d20zR-GV-LV43mTEOXlrO-nO_aWR3T0RjpCMSHzOYY")
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
        New DB-side scoring implementation (replaces Python in-memory matching).
        - Uses a weighted scoring algorithm (exact, alias, substring, token overlap)
        - Applies a rarity/popularity adjustment
        - Requires at least one matched skill (filters out zero-overlap candidates)
        Returns list of dicts similar to previous output:
          { id, name, location, matchedSkillsCount, skills, raw_score, normalized_score }
        """
        # Normalize input to a list of strings
        if not required_skills:
            return []

        if isinstance(required_skills, str):
            required_skills = _ensure_skill_list(required_skills)

        required_skills = [str(s).strip() for s in required_skills if s and str(s).strip()]
        if not required_skills:
            return []

        # Build and run the portable Cypher (no APOC dependency)
        # Implementation follows the scoring described earlier:
        # base weights: exact(3.0), alias(2.5), substring(1.5), token_overlap(1.0)
        # rarity = 1 / (1 + ln(1 + popularity))
        query = """
        WITH [s IN $skills WHERE s IS NOT NULL | toLower(trim(s))] AS reqs
        UNWIND reqs AS _
        WITH collect(distinct _) AS reqs

        MATCH (c:Candidate)-[:HAS_SKILL]->(sk:Skill)
        WITH c, collect(DISTINCT sk) AS candSkills, reqs

        WITH c, candSkills, reqs,
             [sk IN candSkills |
                { name: sk.name,
                  norm: coalesce(sk.norm_name, toLower(trim(sk.name))),
                  aliases: coalesce(sk.aliases, []),
                  popularity: size((sk)<-[:HAS_SKILL]-())
                }
             ] AS skillObjs

        UNWIND skillObjs AS so
        WITH c, so, reqs,
             CASE
               WHEN any(r IN reqs WHERE so.norm = r) THEN 3.0
               WHEN any(r IN reqs WHERE any(a IN so.aliases WHERE toLower(trim(a)) = r)) THEN 2.5
               WHEN any(r IN reqs WHERE r IN so.norm OR so.norm IN r) THEN 1.5
               WHEN any(r IN reqs WHERE size([t IN split(so.norm,' ') WHERE t IN split(r,' ')]) > 0) THEN 1.0
               ELSE 0.0
             END AS base_weight

        WITH c, so, base_weight,
             CASE WHEN base_weight > 0.0 THEN base_weight * (1.0 / (1.0 + log(1.0 + toFloat(coalesce(so.popularity,0))))) ELSE 0.0 END AS adjusted_weight,
             CASE WHEN base_weight > 0.0 THEN so.name ELSE null END AS matched_skill_name,
             so.name AS all_name

        WITH c, collect(adjusted_weight) AS adj_weights, [x IN collect(matched_skill_name) WHERE x IS NOT NULL] AS matchedSkillNames, collect(all_name) AS allSkillNames
        WHERE size(matchedSkillNames) > 0

        WITH c, reduce(acc = 0.0, w IN adj_weights | acc + w) AS raw_score, size(matchedSkillNames) AS matchedSkillsCount, matchedSkillNames AS matchedSkills, allSkillNames AS allSkills
        RETURN c.candidate_id AS id,
               c.name AS name,
               c.location AS location,
               matchedSkillsCount,
               raw_score,
               raw_score / (CASE WHEN size($skills) > 0 THEN size($skills) ELSE 1 END) AS normalized_score,
               matchedSkills AS matchedSkills,
               allSkills AS allSkills
        ORDER BY raw_score DESC
        LIMIT $limit
        """

        params = {"skills": required_skills, "limit": max_results}

        if debug:
            print("DEBUG: running DB-side scoring query with params:", params)

        with self._driver.session() as session:
            try:
                result = session.run(query, **params)
                rows = [r.data() for r in result]
            except Exception as e:
                # on error, fallback to the original in-memory matching to preserve behavior
                if debug:
                    print(f"DB scoring query failed ({e}), falling back to Python matching.")
                return self._fallback_python_match(required_skills, max_results, debug)

        # Map results to the previous output shape (id, name, location, matchedSkillsCount, skills)
        out = []
        for r in rows:
            out.append({
                "id": r.get("id"),
                "name": r.get("name"),
                "location": r.get("location"),
                "matchedSkillsCount": int(r.get("matchedSkillsCount", 0)),
                # return allSkills as the candidate's skill list (original names)
                "skills": r.get("allSkills", []),
                # extended scoring fields
                "raw_score": float(r.get("raw_score", 0.0)),
                "normalized_score": float(r.get("normalized_score", 0.0)),
                "matchedSkills": r.get("matchedSkills", [])
            })

        return out

    def _fallback_python_match(self, required_skills, max_results: int = 10, debug: bool = False) -> List[Dict[str, Any]]:
        """
        Original in-Python matching logic kept as a fallback in case DB-side query fails.
        """
        # This is the previous implementation (kept here to preserve behavior)
        if isinstance(required_skills, str):
            required_skills = _ensure_skill_list(required_skills)

        required_skills = [str(s).strip() for s in required_skills if s and str(s).strip()]
        if not required_skills:
            return []

        norm_required = [_normalize_text(s) for s in required_skills]
        if debug:
            print("DEBUG: required_skills:", required_skills)
            print("DEBUG: norm_required:", norm_required)

        candidates = self._fetch_all_candidates_with_skills()
        scored = []

        for cand in candidates:
            cand_skills = cand.get('skills') or []
            norm_cand_skills = [ _normalize_text(s) for s in cand_skills ]
            matched_skill_names = set()

            for i, r_raw in enumerate(required_skills):
                r_norm = norm_required[i] if i < len(norm_required) else _normalize_text(r_raw)
                if not r_norm:
                    continue

                for orig_skill, c_norm in zip(cand_skills, norm_cand_skills):
                    if not c_norm:
                        continue
                    matched = False

                    if r_norm == c_norm:
                        matched = True
                    elif r_norm in c_norm or c_norm in r_norm:
                        matched = True
                    else:
                        r_tokens = set(r_norm.split())
                        c_tokens = set(c_norm.split())
                        if r_tokens & c_tokens:
                            matched = True

                    if matched:
                        matched_skill_names.add(orig_skill)
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

        scored_sorted = sorted(scored, key=lambda x: x["matchedSkillsCount"], reverse=True)
        return scored_sorted[:max_results]
