# skill_normalizer.py
import os
import re
import threading
from typing import Dict, Any, Tuple, Optional
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer, util
from neo4j import GraphDatabase

load_dotenv()

SIM_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.85"))

# Load once per process
model = SentenceTransformer("all-MiniLM-L6-v2")

def _clean(s: str) -> str:
    """Clean and normalize skill name to lowercase."""
    s = (s or "").strip().lower()
    return re.sub(r"[\s\-_\/]+", " ", s)

class SkillNormalizer:
    """Normalizes skills using embeddings and Neo4j for persistence."""
    
    def __init__(self, neo4j_driver=None):
        self.driver = neo4j_driver
        self.local_cache = {}  # {raw_skill: (canonical_name, embedding)}
        self.lock = threading.Lock()
        
    def normalize_skill(self, raw_skill: str, threshold: float = SIM_THRESHOLD) -> Tuple[str, str]:
        """
        Normalize a skill and return (canonical_name, raw_skill_cleaned).
        Updates Neo4j with aliases if driver is available.
        
        Returns:
            Tuple[canonical_name, cleaned_raw_skill]
        """
        cleaned = _clean(raw_skill)
        if not cleaned:
            return "", ""
        
        # Check local cache first (fast path)
        if cleaned in self.local_cache:
            cached_canon, _ = self.local_cache[cleaned]
            # Even if in cache, verify with database if driver available
            # This ensures we catch any skills added by other processes
            if self.driver:
                db_check = self._check_skill_exists_in_db(cached_canon)
                if db_check and db_check != cached_canon:
                    # Database has a different canonical name, use it
                    self.local_cache[cleaned] = (db_check, None)
                    return db_check, cleaned
            return cached_canon, cleaned
        
        # Encode the skill
        vec = model.encode(cleaned, convert_to_tensor=True)
        embedding_list = vec.cpu().tolist()
        
        with self.lock:
            # STEP 1: Check database FIRST (most authoritative)
            # This ensures we don't create duplicates
            best_canon = None
            best_embedding = None
            if self.driver:
                db_match, db_match_embedding = self._find_similar_skill_in_db(cleaned, vec, embedding_list, threshold)
                if db_match:
                    best_canon = db_match
                    best_embedding = db_match_embedding
                    # Cache the database match
                    if db_match_embedding:
                        import torch
                        db_vec_tensor = torch.tensor(db_match_embedding)
                        self.local_cache[db_match] = (db_match, db_vec_tensor)
            
            # STEP 2: If no DB match, check local cache for similar skills
            if best_canon is None:
                best_sim = threshold
                for cached_cleaned, (cached_canon, cached_vec) in self.local_cache.items():
                    if cached_vec is not None:
                        sim = util.cos_sim(vec, cached_vec).item()
                        if sim > best_sim:
                            best_sim = sim
                            best_canon = cached_canon
            
            # STEP 3: If no match found anywhere, create new skill
            if best_canon is None:
                best_canon = cleaned
                # Store in local cache
                self.local_cache[cleaned] = (best_canon, vec)
                # Store in Neo4j if driver available (uses MERGE, so safe)
                if self.driver:
                    self._store_skill_in_db(best_canon, embedding_list)
            else:
                # Store mapping from cleaned to canonical in local cache
                self.local_cache[cleaned] = (best_canon, vec)
                # If this is a new alias (different from canonical), add it to the skill
                if self.driver and cleaned != best_canon:
                    self._add_alias_to_skill(best_canon, cleaned)
            
            return best_canon, cleaned
    
    def _check_skill_exists_in_db(self, norm_name: str) -> Optional[str]:
        """Check if a skill with this norm_name exists in DB (case-insensitive)."""
        try:
            with self.driver.session() as session:
                # Use CASE to handle missing properties gracefully
                result = session.run(
                    "MATCH (s:Skill) "
                    "WHERE s.norm_name IS NOT NULL AND toLower(s.norm_name) = toLower($norm_name) "
                    "RETURN s.norm_name as norm_name "
                    "LIMIT 1",
                    norm_name=norm_name
                )
                record = result.single()
                if record and record["norm_name"]:
                    return record["norm_name"]
                return None
        except Exception as e:
            # Silently return None if no skills exist yet (expected on first run)
            return None
    
    def _find_similar_skill_in_db(self, cleaned_skill: str, vec, embedding_list: list, threshold: float) -> Tuple[Optional[str], Optional[list]]:
        """Find similar skill in Neo4j database.
        
        Returns:
            Tuple of (canonical_name, embedding) or (None, None) if no match
        """
        try:
            with self.driver.session() as session:
                # First check if any Skill nodes exist at all
                count_result = session.run("MATCH (s:Skill) RETURN count(s) as count")
                count_record = count_result.single()
                if not count_record or count_record["count"] == 0:
                    # No skills exist yet, return None
                    return None, None
                
                # Check for exact match by norm_name (case-insensitive comparison)
                # Also check if cleaned_skill is in aliases (case-insensitive)
                # Use COALESCE to handle missing properties
                exact_match = session.run(
                    "MATCH (s:Skill) "
                    "WHERE s.norm_name IS NOT NULL AND ("
                    "  toLower(s.norm_name) = toLower($skill) "
                    "  OR ($skill IN COALESCE(s.aliases, [])) "
                    "  OR (s.aliases IS NOT NULL AND any(alias IN s.aliases WHERE toLower(alias) = toLower($skill)))"
                    ") "
                    "RETURN s.norm_name as norm_name, "
                    "       COALESCE(s.embedding, null) as embedding, "
                    "       COALESCE(s.aliases, []) as aliases "
                    "LIMIT 1",
                    skill=cleaned_skill
                )
                record = exact_match.single()
                if record and record["norm_name"]:
                    return record["norm_name"], record["embedding"]
                
                # If no exact match, check by embedding similarity
                # Get ALL skills with embeddings for similarity checking
                all_skills = session.run(
                    "MATCH (s:Skill) "
                    "WHERE s.norm_name IS NOT NULL "
                    "RETURN s.norm_name as norm_name, "
                    "       COALESCE(s.embedding, null) as embedding, "
                    "       COALESCE(s.aliases, []) as aliases"
                )
                
                best_canon = None
                best_embedding = None
                best_sim = threshold
                
                for record in all_skills:
                    if not record or not record["norm_name"]:
                        continue
                        
                    db_norm_name = record["norm_name"]
                    db_embedding = record["embedding"]
                    db_aliases = record.get("aliases") or []
                    
                    # Check if cleaned_skill matches norm_name (case-insensitive) or any alias
                    if db_norm_name and cleaned_skill.lower() == db_norm_name.lower():
                        return db_norm_name, db_embedding
                    
                    # Check aliases (case-insensitive)
                    if db_aliases:
                        for alias in db_aliases:
                            if alias and cleaned_skill.lower() == str(alias).lower():
                                return db_norm_name, db_embedding
                    
                    # Compare embeddings (only if embedding exists and is valid)
                    if db_embedding and isinstance(db_embedding, list) and len(db_embedding) > 0:
                        try:
                            import torch
                            db_vec = torch.tensor(db_embedding)
                            sim = util.cos_sim(vec, db_vec).item()
                            if sim > best_sim:
                                best_sim = sim
                                best_canon = db_norm_name
                                best_embedding = db_embedding
                        except Exception as e:
                            # Skip this skill if embedding comparison fails
                            continue
                
                if best_canon:
                    return best_canon, best_embedding
                return None, None
        except Exception as e:
            print(f"Warning: Error querying Neo4j for skills: {e}")
            import traceback
            traceback.print_exc()
            return None, None
    
    def _store_skill_in_db(self, norm_name: str, embedding_list: list):
        """Store a skill in Neo4j using MERGE to avoid duplicates."""
        try:
            with self.driver.session() as session:
                # Use MERGE to ensure skill exists - this is safe and won't create duplicates
                # MERGE will only create if it doesn't exist, and won't overwrite existing properties
                session.run(
                    "MERGE (s:Skill {norm_name: $norm_name}) "
                    "ON CREATE SET s.name = $norm_name, "
                    "            s.norm_name = $norm_name, "
                    "            s.aliases = [], "
                    "            s.embedding = $embedding, "
                    "            s.created_at = datetime() "
                    "ON MATCH SET s.embedding = COALESCE(s.embedding, $embedding)",
                    norm_name=norm_name,
                    embedding=embedding_list
                )
        except Exception as e:
            print(f"Warning: Error storing skill in Neo4j: {e}")
            import traceback
            traceback.print_exc()
    
    def _add_alias_to_skill(self, norm_name: str, alias: str):
        """Add an alias to an existing skill in Neo4j."""
        try:
            with self.driver.session() as session:
                # Get current aliases, add new one if not present
                # Neo4j handles list operations, but we need to be careful with nulls
                result = session.run(
                    "MATCH (s:Skill {norm_name: $norm_name}) "
                    "RETURN s.aliases as aliases",
                    norm_name=norm_name
                )
                record = result.single()
                if record:
                    current_aliases = record["aliases"] or []
                    if alias not in current_aliases and alias != norm_name:
                        new_aliases = current_aliases + [alias]
                        session.run(
                            "MATCH (s:Skill {norm_name: $norm_name}) "
                            "SET s.aliases = $aliases",
                            norm_name=norm_name,
                            aliases=new_aliases
                        )
        except Exception as e:
            print(f"Warning: Error adding alias to skill in Neo4j: {e}")

# Global normalizer instance (will be initialized with driver in graph_writer)
_global_normalizer = None
_normalizer_lock = threading.Lock()

def get_normalizer(neo4j_driver=None) -> SkillNormalizer:
    """Get or create the global skill normalizer."""
    global _global_normalizer
    with _normalizer_lock:
        if _global_normalizer is None:
            _global_normalizer = SkillNormalizer(neo4j_driver)
        elif neo4j_driver and _global_normalizer.driver is None:
            _global_normalizer.driver = neo4j_driver
        return _global_normalizer

def normalize_skill_shared(raw_skill: str, state: Dict[str, Any], threshold: float = SIM_THRESHOLD) -> str:
    """
    Backward-compatible function for existing code.
    Uses state to get normalizer instance.
    Returns canonical skill name.
    """
    normalizer = state.get("skill_normalizer")
    if normalizer is None:
        # Fallback to simple cleaning if no normalizer
        return _clean(raw_skill)
    
    canonical, _ = normalizer.normalize_skill(raw_skill, threshold)
    return canonical
