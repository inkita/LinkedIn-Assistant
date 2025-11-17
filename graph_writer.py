import os
import uuid
from datetime import datetime
from neo4j import GraphDatabase
from dotenv import load_dotenv
from skill_normalizer import get_normalizer

load_dotenv()

class GraphWriter:
    def __init__(self, uri, user, password, normalizer=None):
        uri = uri or os.getenv("NEO4J_URI")
        user = user or os.getenv("NEO4J_USER")
        password = password or os.getenv("NEO4J_PASSWORD")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        with self.driver.session() as s:
            s.run("RETURN 1")
        
        # Use provided normalizer or create one with Neo4j driver
        if normalizer:
            self.normalizer = normalizer
            # Ensure normalizer has the driver
            if self.normalizer.driver is None:
                self.normalizer.driver = self.driver
        else:
            self.normalizer = get_normalizer(self.driver)

    def close(self):
        self.driver.close()

    def merge_candidate(self, name, email, experience_years=None, education=None, skills=None):
        """Merge candidate with all schema fields.
        
        Args:
            name: Candidate name
            email: Candidate email (required, used as unique identifier)
            experience_years: Years of experience as integer (0 if not provided)
            education: Normalized education level: "bachelor's", "master's", "phd", or empty string
            skills: List of canonical skill names
        
        Returns:
            str: Candidate ID (UUID) from the knowledge graph
        """
        if skills is None:
            skills = []
        
        if not email:
            raise ValueError("Email is required for candidate")
        
        if not name:
            name = "Unknown Candidate"
        
        # Clean up values
        email = str(email).strip() if email else None
        name = str(name).strip() if name else "Unknown Candidate"
        
        # Convert experience_years to integer (default to 0)
        if experience_years is None:
            experience_years = 0
        try:
            experience_years = int(experience_years)
        except (ValueError, TypeError):
            experience_years = 0
        
        # Normalize education - only allow: bachelor's, master's, phd, or empty
        if education:
            education_lower = str(education).strip().lower()
            if education_lower not in ["bachelor's", "master's", "phd"]:
                education = ""  # Set to empty if not one of the allowed values
        else:
            education = ""
        
        if not email:
            raise ValueError("Email cannot be empty after cleaning")
        
        print(f"  Merging candidate: name='{name}', email='{email}', experience_years={experience_years}, education='{education}'")
        
        with self.driver.session() as session:
            # Generate ID for new candidates
            candidate_id = str(uuid.uuid4())
            
            # Merge candidate - email is the unique identifier
            try:
                result = session.run(
                    "MERGE (c:Candidate {email: $email}) "
                    "ON CREATE SET c.id = $id, "
                    "            c.name = $name, "
                    "            c.email = $email, "
                    "            c.experience = $experience_years, "
                    "            c.education = $education "
                    "ON MATCH SET c.name = COALESCE(c.name, $name), "
                    "            c.experience = COALESCE(c.experience, $experience_years), "
                    "            c.education = COALESCE(c.education, $education) "
                    "RETURN c.email as email, c.name as name, c.id as id",
                    id=candidate_id,
                    name=name,
                    email=email,
                    experience_years=experience_years,
                    education=education
                )
                record = result.single()
                candidate_id = None
                if record:
                    candidate_id = record['id']
                    print(f"  ✓ Candidate merged/updated: {record['name']} ({record['email']}) [ID: {candidate_id}]")
                else:
                    print(f"  ⚠ Warning: Candidate merge completed but no record returned")
                    # Try to get the ID by querying with email
                    id_result = session.run(
                        "MATCH (c:Candidate {email: $email}) RETURN c.id as id",
                        email=email
                    )
                    id_record = id_result.single()
                    if id_record:
                        candidate_id = id_record['id']
            except Exception as e:
                print(f"  ✗ Error merging candidate: {e}")
                import traceback
                traceback.print_exc()
                raise
            
            # Add skills (these should already be canonical/normalized and exist in DB)
            skills_added = 0
            skills_failed = 0
            for skill in skills:
                if not skill:
                    continue
                
                skill_clean = str(skill).strip()
                if not skill_clean:
                    continue
                
                # Skills should already exist from normalization step, but ensure they exist
                # Use MERGE to create skill if it doesn't exist (fallback safety)
                try:
                    # First ensure skill exists (should already exist, but MERGE is safe)
                    session.run(
                        "MERGE (sk:Skill {norm_name: $skill_norm}) "
                        "ON CREATE SET sk.name = $skill_norm, "
                        "            sk.aliases = [], "
                        "            sk.created_at = datetime()",
                        skill_norm=skill_clean
                    )
                    
                    # Then create relationship
                    result = session.run(
                        "MATCH (sk:Skill {norm_name: $skill_norm}) "
                        "MATCH (c:Candidate {email: $email}) "
                        "MERGE (c)-[:HAS_SKILL]->(sk) "
                        "RETURN sk.norm_name as skill_name",
                        email=email,
                        skill_norm=skill_clean
                    )
                    record = result.single()
                    if record:
                        skills_added += 1
                    else:
                        print(f"  ⚠ Warning: Could not create relationship for skill '{skill_clean}'")
                        skills_failed += 1
                except Exception as e:
                    print(f"  ⚠ Warning: Failed to add skill '{skill_clean}' to candidate: {e}")
                    import traceback
                    traceback.print_exc()
                    skills_failed += 1
            
            if skills_added > 0:
                print(f"  ✓ Added {skills_added} skill(s) to candidate")
            if skills_failed > 0:
                print(f"  ⚠ Failed to add {skills_failed} skill(s) to candidate")
            
            # Final fallback: if candidate_id is still None, query by email
            if not candidate_id:
                id_result = session.run(
                    "MATCH (c:Candidate {email: $email}) RETURN c.id as id",
                    email=email
                )
                id_record = id_result.single()
                if id_record:
                    candidate_id = id_record['id']
            
            return candidate_id

    def merge_job(self, title, company, location=None, experience_years=None, education=None, 
                  posting_date=None, domain=None, skills=None):
        """Merge job with all schema fields.
        
        Args:
            title: Job title
            company: Company name
            location: Job location (optional)
            experience_years: Years of experience required as integer (0 if not provided)
            education: Normalized education level: "bachelor's", "master's", "phd", or empty string
            posting_date: Posting date (optional)
            domain: Domain classification: "sales", "technology", or None
            skills: List of canonical skill names
        
        Returns:
            str: Job ID (UUID) from the knowledge graph
        """
        if skills is None:
            skills = []
        
        # Validate domain - only allow "sales" or "technology"
        if domain:
            domain_lower = domain.lower().strip()
            if domain_lower not in ["sales", "technology"]:
                domain = None  # Don't set domain if it's not one of the allowed values
        
        # Convert experience_years to integer (default to 0)
        if experience_years is None:
            experience_years = 0
        try:
            experience_years = int(experience_years)
        except (ValueError, TypeError):
            experience_years = 0
        
        # Normalize education - only allow: bachelor's, master's, phd, or empty
        if education:
            education_lower = str(education).strip().lower()
            if education_lower not in ["bachelor's", "master's", "phd"]:
                education = ""  # Set to empty if not one of the allowed values
        else:
            education = ""
        
        with self.driver.session() as session:
            # Generate ID if not provided
            job_id = str(uuid.uuid4())
            
            # Handle domain (only if valid)
            if domain:
                domain_normalized = domain.lower().strip()
                session.run(
                    "MERGE (dom:Domain {name: $domain_name}) "
                    "ON CREATE SET dom.id = $dom_id, dom.name = $domain_name",
                    domain_name=domain_normalized,
                    dom_id=str(uuid.uuid4())
                )
            
            # Merge job
            result = session.run(
                "MERGE (j:Job {title: $title, company: $company}) "
                "ON CREATE SET j.id = $id, "
                "            j.title = $title, "
                "            j.company = $company, "
                "            j.location = $location, "
                "            j.experience = $experience_years, "
                "            j.education = $education, "
                "            j.posting_date = $posting_date "
                "ON MATCH SET j.location = COALESCE(j.location, $location), "
                "            j.experience = COALESCE(j.experience, $experience_years), "
                "            j.education = COALESCE(j.education, $education), "
                "            j.posting_date = COALESCE(j.posting_date, $posting_date) "
                "RETURN j.id as id",
                id=job_id,
                title=title,
                company=company,
                location=location or "",
                experience_years=experience_years,
                education=education,
                posting_date=posting_date or ""
            )
            record = result.single()
            returned_job_id = None
            if record:
                returned_job_id = record['id']
            else:
                # Fallback: query by title and company
                id_result = session.run(
                    "MATCH (j:Job {title: $title, company: $company}) RETURN j.id as id",
                    title=title,
                    company=company
                )
                id_record = id_result.single()
                if id_record:
                    returned_job_id = id_record['id']
                else:
                    returned_job_id = job_id  # Use the generated ID
            
            # Link job to domain if provided and valid
            if domain:
                domain_normalized = domain.lower().strip()
                session.run(
                    "MATCH (j:Job {title: $title, company: $company}) "
                    "MATCH (dom:Domain {name: $domain_name}) "
                    "MERGE (dom)-[:HAS_JOB]->(j)",
                    title=title,
                    company=company,
                    domain_name=domain_normalized
                )
            
            # Add skills (these should already be canonical/normalized and exist in DB)
            for skill in skills:
                if not skill:
                    continue
                # Skills should already exist from normalization step
                # Just create the relationship - if skill doesn't exist, this will fail silently
                # but it shouldn't happen if normalization worked correctly
                session.run(
                    "MATCH (sk:Skill {norm_name: $skill_norm}) "
                    "MATCH (j:Job {title: $title, company: $company}) "
                    "MERGE (j)-[:REQUIRES_SKILL]->(sk)",
                    title=title,
                    company=company,
                    skill_norm=skill
                )
            
            return returned_job_id
