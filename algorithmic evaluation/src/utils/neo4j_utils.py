"""
Neo4j utilities for skill degradation test.
"""

from typing import Optional
from neo4j import GraphDatabase
from ..models import Candidate


class Neo4jSkillDegradationEngine:
    """
    Neo4j-based skill degradation engine.
    Use this if your candidate skills are stored in Neo4j graph database.
    """
    
    def __init__(self, uri: str, user: str, password: str):
        """
        Initialize Neo4j connection.
        
        Args:
            uri: Neo4j connection URI (e.g., "bolt://localhost:7687")
            user: Neo4j username
            password: Neo4j password
        """
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self._backup_data = {}  # Store original state for restoration
    
    def close(self):
        """Close Neo4j connection"""
        self.driver.close()
    
    def remove_skill_node(self, candidate_id: str, skill_name: str) -> bool:
        """
        Remove a skill relationship from Neo4j graph.
        
        Args:
            candidate_id: Candidate ID
            skill_name: Skill name to remove
            
        Returns:
            True if skill was removed, False if it didn't exist
        """
        # Backup original relationship if not already backed up
        if candidate_id not in self._backup_data:
            self._backup_data[candidate_id] = []
        
        # Check if relationship exists and backup
        with self.driver.session() as session:
            query = """
            MATCH (c:Candidate {id: $candidate_id})-[r:HAS_SKILL]->(s:Skill {name: $skill_name})
            RETURN r.proficiency as proficiency
            """
            result = session.run(query, candidate_id=candidate_id, skill_name=skill_name)
            record = result.single()
            
            if record:
                # Backup the relationship
                proficiency = record['proficiency']
                if (candidate_id, skill_name) not in [(b['candidate_id'], b['skill']) for b in self._backup_data[candidate_id]]:
                    self._backup_data[candidate_id].append({
                        'skill': skill_name,
                        'proficiency': proficiency
                    })
                
                # Delete the relationship
                delete_query = """
                MATCH (c:Candidate {id: $candidate_id})-[r:HAS_SKILL]->(s:Skill {name: $skill_name})
                DELETE r
                RETURN count(r) as deleted
                """
                delete_result = session.run(delete_query, candidate_id=candidate_id, skill_name=skill_name)
                return delete_result.single()['deleted'] > 0
        
        return False
    
    def restore_skill_node(self, candidate_id: str, skill_name: str, proficiency: Optional[str] = None) -> bool:
        """
        Restore a skill relationship (for test cleanup).
        
        Args:
            candidate_id: Candidate ID
            skill_name: Skill name to restore
            proficiency: Optional proficiency level
            
        Returns:
            True if skill was restored
        """
        # Find backup data
        backup_entry = None
        if candidate_id in self._backup_data:
            for entry in self._backup_data[candidate_id]:
                if entry['skill'] == skill_name:
                    backup_entry = entry
                    break
        
        # Use backup proficiency if available
        if backup_entry and proficiency is None:
            proficiency = backup_entry.get('proficiency')
        
        with self.driver.session() as session:
            query = """
            MATCH (c:Candidate {id: $candidate_id}), (s:Skill {name: $skill_name})
            MERGE (c)-[r:HAS_SKILL]->(s)
            """
            if proficiency:
                query += " SET r.proficiency = $proficiency"
            query += " RETURN r"
            
            result = session.run(query, candidate_id=candidate_id, skill_name=skill_name, proficiency=proficiency)
            return result.single() is not None
    
    def restore_all_skills(self, candidate_id: str) -> int:
        """
        Restore all backed up skills for a candidate.
        
        Args:
            candidate_id: Candidate ID
            
        Returns:
            Number of skills restored
        """
        if candidate_id not in self._backup_data:
            return 0
        
        restored_count = 0
        for backup_entry in self._backup_data[candidate_id]:
            if self.restore_skill_node(candidate_id, backup_entry['skill'], backup_entry.get('proficiency')):
                restored_count += 1
        
        # Clear backup after restoration
        del self._backup_data[candidate_id]
        return restored_count
    
    def degrade_skill_level(self, candidate_id: str, skill_name: str, new_level: str) -> bool:
        """
        Reduce skill proficiency level in Neo4j.
        
        Args:
            candidate_id: Candidate ID
            skill_name: Skill name
            new_level: New proficiency level (e.g., "Beginner")
            
        Returns:
            True if skill level was updated
        """
        # Backup original level if not already backed up
        if candidate_id not in self._backup_data:
            self._backup_data[candidate_id] = []
        
        with self.driver.session() as session:
            # Get current proficiency
            query = """
            MATCH (c:Candidate {id: $candidate_id})-[r:HAS_SKILL]->(s:Skill {name: $skill_name})
            RETURN r.proficiency as proficiency
            """
            result = session.run(query, candidate_id=candidate_id, skill_name=skill_name)
            record = result.single()
            
            if record:
                current_proficiency = record['proficiency']
                # Backup if not already backed up
                if (candidate_id, skill_name) not in [(b['candidate_id'], b['skill']) for b in self._backup_data.get(candidate_id, [])]:
                    self._backup_data[candidate_id].append({
                        'skill': skill_name,
                        'proficiency': current_proficiency
                    })
                
                # Update proficiency
                update_query = """
                MATCH (c:Candidate {id: $candidate_id})-[r:HAS_SKILL]->(s:Skill {name: $skill_name})
                SET r.proficiency = $new_level
                RETURN r
                """
                update_result = session.run(update_query, candidate_id=candidate_id, skill_name=skill_name, new_level=new_level)
                return update_result.single() is not None
        
        return False

