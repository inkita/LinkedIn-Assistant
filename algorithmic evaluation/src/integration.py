"""
Integration adapter to connect your existing LinkedIn Assistant codebase 
with the evaluation framework.
"""

from typing import List, Dict, Optional
from neo4j import GraphDatabase
from .models import Candidate, JobPosting, ScoreBreakdown
from .algorithm import HybridAlgorithm


class Neo4jHybridAlgorithm(HybridAlgorithm):
    """
    Hybrid Algorithm that uses your actual Neo4j database.
    Extends the base HybridAlgorithm with Neo4j queries.
    """
    
    def __init__(self, neo4j_uri: str, neo4j_user: str, neo4j_password: str,
                 jaccard_weight: float = 0.6, guttman_weight: float = 0.4):
        """
        Initialize with Neo4j connection.
        
        Args:
            neo4j_uri: Neo4j connection URI
            neo4j_user: Neo4j username
            neo4j_password: Neo4j password
            jaccard_weight: Weight for Jaccard similarity (default: 0.6)
            guttman_weight: Weight for Guttman scaling (default: 0.4)
        """
        super().__init__(jaccard_weight, guttman_weight)
        # Allow trusting all certs if environment variable is set (helpful in restricted envs)
        import os
        trust_all = os.getenv("NEO4J_TRUST_ALL_CERTS", "false").lower() in ("1", "true", "yes")
        if trust_all:
            self.driver = GraphDatabase.driver(
                neo4j_uri,
                auth=(neo4j_user, neo4j_password),
                trust="TRUST_ALL_CERTIFICATES",
            )
        else:
            self.driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        self.driver.verify_connectivity()
        print("✅ Connected to Neo4j for Hybrid Algorithm")
    
    def close(self):
        """Close Neo4j connection"""
        if self.driver:
            self.driver.close()
    
    def _guttman_scaling_detailed(self, job: JobPosting, candidate: Candidate) -> tuple:
        """
        Calculate Guttman scaling using Neo4j graph structure.
        This version is schema-tolerant: it works if your nodes lack
        candidate_id, years_experience, title, or proficiency properties.
        """
        with self.driver.session() as session:
            # Use any available identifier: candidate_id, id, or name
            query = """
            MATCH (c:Candidate)
            WHERE (c.candidate_id IS NOT NULL AND c.candidate_id = $cid)
               OR (c.id IS NOT NULL AND c.id = $cid)
               OR (c.name IS NOT NULL AND c.name = $cid)
            OPTIONAL MATCH (c)-[:HAS_SKILL]->(s:Skill)
            WITH c,
                 collect(s.name) AS skills,
                 coalesce(c.years_experience, c.experience, 0) AS years_exp,
                 coalesce(c.title, c.current_title, 'Unknown') AS title
            RETURN skills, years_exp, title
            """

            result = session.run(query, cid=candidate.id)
            record = result.single()

            if record:
                years_exp_raw = record["years_exp"] if record["years_exp"] is not None else candidate.years_experience
                title = record["title"] if record["title"] else candidate.current_title
                neo4j_skills = record["skills"] if record["skills"] else candidate.skills
            else:
                years_exp_raw = candidate.years_experience
                title = candidate.current_title
                neo4j_skills = candidate.skills

            # Safely convert years_experience to int with realistic cap
            try:
                if isinstance(years_exp_raw, (int, float)):
                    years_experience = int(years_exp_raw)
                elif isinstance(years_exp_raw, str):
                    import re
                    # Extract all numbers, but prefer smaller numbers (likely years of experience)
                    # Filter out years > 50 (likely dates like 1975, 2020, etc.)
                    numbers = [int(n) for n in re.findall(r'\d+', str(years_exp_raw)) if int(n) <= 50]
                    if numbers:
                        # Use the largest reasonable number (but cap at 50)
                        years_experience = min(max(numbers), 50)
                    else:
                        years_experience = 0
                else:
                    years_experience = 0
                # Cap at 50 years maximum (realistic upper bound)
                years_experience = min(years_experience, 50)
            except (ValueError, TypeError):
                years_experience = 0

            # Calculate Guttman scaling components (proficiency optional)
            experience_score = min(years_experience / 10.0, 1.0)
            title_score = self._title_to_score(title)
            proficiency_score = self._calculate_proficiency_from_neo4j(candidate.id, neo4j_skills)

            guttman_score = (experience_score * 0.4) + (title_score * 0.4) + (proficiency_score * 0.2)
            seniority_level = self._determine_seniority_level(years_experience, title)

            return guttman_score, seniority_level
    
    def _calculate_proficiency_from_neo4j(self, candidate_id: str, skills: List[str]) -> float:
        """
        Calculate average proficiency score from Neo4j skill relationships.
        Falls back to a neutral score if proficiency is absent in your graph.
        """
        if not skills:
            return 0.5

        with self.driver.session() as session:
            query = """
            MATCH (c:Candidate)
            WHERE (c.candidate_id IS NOT NULL AND c.candidate_id = $cid)
               OR (c.id IS NOT NULL AND c.id = $cid)
               OR (c.name IS NOT NULL AND c.name = $cid)
            MATCH (c)-[r:HAS_SKILL]->(s:Skill)
            WHERE s.name IN $skills
            RETURN coalesce(r.proficiency, 'intermediate') AS proficiency
            """

            result = session.run(query, cid=candidate_id, skills=skills)
            proficiencies = [record["proficiency"] for record in result]

        if not proficiencies:
            return 0.5

        proficiency_map = {
            "expert": 1.0,
            "advanced": 0.8,
            "intermediate": 0.5,
            "beginner": 0.3,
            "novice": 0.2,
        }

        scores = []
        for prof in proficiencies:
            prof_lower = str(prof).lower() if prof else "intermediate"
            score = proficiency_map.get(prof_lower, 0.5)
            scores.append(score)

        return sum(scores) / len(scores) if scores else 0.5
    
    def get_missing_skills_from_neo4j(self, job: JobPosting, candidate_id: str) -> List[str]:
        """
        Get missing skills by querying Neo4j.
        """
        with self.driver.session() as session:
            query = """
            MATCH (c:Candidate {candidate_id: $candidate_id})-[:HAS_SKILL]->(s:Skill)
            WITH collect(toLower(s.name)) as candidate_skills
            
            WITH candidate_skills, $required_skills as required
            UNWIND required as req_skill
            WITH candidate_skills, toLower(req_skill) as req_lower
            
            WHERE NOT ANY(c_skill IN candidate_skills WHERE c_skill CONTAINS req_lower)
            RETURN req_skill
            """
            
            result = session.run(query, 
                                candidate_id=candidate_id,
                                required_skills=job.required_skills)
            missing = [record['req_skill'] for record in result]
            return missing


class Neo4jDataLoader:
    """
    Load candidates and jobs from your Neo4j database.
    """
    
    def __init__(self, neo4j_uri: str, neo4j_user: str, neo4j_password: str):
        """Initialize Neo4j connection"""
        # Use same driver configuration as working candidate_agent.py
        self.driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        self.driver.verify_connectivity()
        print("✅ Connected to Neo4j for Data Loading")
    
    def close(self):
        """Close Neo4j connection"""
        if self.driver:
            self.driver.close()
    
    def load_candidates(self, limit: Optional[int] = None) -> List[Candidate]:
        """
        Load all candidates from Neo4j.
        
        Args:
            limit: Optional limit on number of candidates to load
            
        Returns:
            List of Candidate objects
        """
        query = """
        MATCH (c:Candidate)
        OPTIONAL MATCH (c)-[:HAS_SKILL]->(s:Skill)
        WITH c,
             collect(s.name) as skills
        RETURN
            coalesce(c.candidate_id, c.id, c.name, toString(id(c))) AS id,
            coalesce(c.name, 'Unknown') AS name,
            coalesce(c.title, c.current_title, 'Unknown') AS title,
            coalesce(c.years_experience, c.experience, 0) AS years_experience,
            skills
        ORDER BY id
        """
        
        if limit:
            query += f" LIMIT {limit}"
        
        with self.driver.session() as session:
            result = session.run(query)
            candidates = []
            
            for record in result:
                # Safely convert years_experience to int, handling non-numeric values
                years_exp = record.get('years_experience', 0)
                try:
                    if isinstance(years_exp, (int, float)):
                        years_exp = int(years_exp)
                    elif isinstance(years_exp, str):
                        # Try to extract number from string, or default to 0
                        import re
                        numbers = re.findall(r'\d+', years_exp)
                        years_exp = int(numbers[0]) if numbers else 0
                    else:
                        years_exp = 0
                except (ValueError, TypeError):
                    years_exp = 0
                
                candidate = Candidate(
                    id=str(record['id']),
                    name=record['name'],
                    current_title=record['title'],
                    skills=record['skills'] if record['skills'] else [],
                    years_experience=years_exp,
                    skill_proficiencies={}  # Can be enhanced to load from Neo4j
                )
                candidates.append(candidate)
            
            return candidates
    
    def load_job_postings(self, limit: Optional[int] = None) -> List[JobPosting]:
        """
        Load job postings from Neo4j.
        
        Args:
            limit: Optional limit on number of jobs to load
            
        Returns:
            List of JobPosting objects
        """
        query = """
        MATCH (j:Job)
        OPTIONAL MATCH (j)-[:REQUIRES_SKILL]->(s:Skill)
        WITH j, collect(s.name) as required_skills
        RETURN
            coalesce(j.job_id, j.id, j.title, toString(id(j))) AS id,
            coalesce(j.title, 'Unknown') AS title,
            coalesce(j.experience_level, 'Mid-level') AS experience_level,
            coalesce(j.description, '') AS description,
            required_skills
        ORDER BY id
        """
        
        if limit:
            query += f" LIMIT {limit}"
        
        with self.driver.session() as session:
            result = session.run(query)
            jobs = []
            
            for record in result:
                job = JobPosting(
                    id=str(record['id']),
                    title=record['title'],
                    required_skills=record['required_skills'] if record['required_skills'] else [],
                    experience_level=record['experience_level'],
                    description=record['description']
                )
                jobs.append(job)
            
            return jobs
    
    def load_job_by_id(self, job_id: str) -> Optional[JobPosting]:
        """Load a specific job posting by ID"""
        query = """
        MATCH (j:Job)
        WHERE (j.job_id IS NOT NULL AND j.job_id = $job_id)
           OR (j.id IS NOT NULL AND j.id = $job_id)
           OR (j.title IS NOT NULL AND j.title = $job_id)
        OPTIONAL MATCH (j)-[:REQUIRES_SKILL]->(s:Skill)
        WITH j, collect(s.name) as required_skills
        RETURN
            coalesce(j.job_id, j.id, j.title, toString(id(j))) AS id,
            coalesce(j.title, 'Unknown') AS title,
            coalesce(j.experience_level, 'Mid-level') AS experience_level,
            coalesce(j.description, '') AS description,
            required_skills
        """
        
        with self.driver.session() as session:
            result = session.run(query, job_id=job_id)
            record = result.single()
            
            if record:
                return JobPosting(
                    id=str(record['id']),
                    title=record['title'],
                    required_skills=record['required_skills'] if record['required_skills'] else [],
                    experience_level=record['experience_level'],
                    description=record['description']
                )
            return None

