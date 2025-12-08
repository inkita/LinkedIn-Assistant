"""
Hybrid Algorithm implementation with Jaccard similarity and Guttman scaling.
This is an interface that you should adapt to your actual algorithm implementation.
"""

from typing import List, Dict, Tuple
from .models import Candidate, JobPosting, ScoreBreakdown


class HybridAlgorithm:
    """
    Hybrid Algorithm for candidate-job matching.
    Combines Jaccard similarity (skill matching) and Guttman scaling (seniority assessment).
    
    This is a base implementation. You should modify this to match your actual algorithm.
    """
    
    def __init__(self, jaccard_weight: float = 0.6, guttman_weight: float = 0.4):
        """
        Initialize the algorithm with component weights.
        
        Args:
            jaccard_weight: Weight for Jaccard similarity component (default: 0.6)
            guttman_weight: Weight for Guttman scaling component (default: 0.4)
        """
        self.jaccard_weight = jaccard_weight
        self.guttman_weight = guttman_weight
        
        # Ensure weights sum to 1.0
        total_weight = jaccard_weight + guttman_weight
        if abs(total_weight - 1.0) > 0.01:
            raise ValueError(f"Weights must sum to 1.0, got {total_weight}")
    
    def calculate_match_score(self, job: JobPosting, candidate: Candidate) -> float:
        """
        Calculate overall match score between job and candidate.
        
        Args:
            job: Job posting
            candidate: Candidate profile
            
        Returns:
            Match score between 0.0 and 1.0
        """
        breakdown = self.calculate_match_score_detailed(job, candidate)
        return breakdown.total
    
    def calculate_match_score_detailed(self, job: JobPosting, candidate: Candidate) -> ScoreBreakdown:
        """
        Calculate match score with detailed breakdown.
        
        Args:
            job: Job posting
            candidate: Candidate profile
            
        Returns:
            ScoreBreakdown with all components
        """
        # Calculate Jaccard similarity
        jaccard_score, missing_skills, common_skills = self._jaccard_similarity_detailed(
            job.required_skills, candidate.skills
        )
        
        # Calculate Guttman scaling
        guttman_score, seniority_level = self._guttman_scaling_detailed(job, candidate)
        
        # Combine scores
        total_score = (jaccard_score * self.jaccard_weight) + (guttman_score * self.guttman_weight)
        
        return ScoreBreakdown(
            total=total_score,
            jaccard_similarity=jaccard_score,
            guttman_scaling=guttman_score,
            missing_skills=missing_skills,
            common_skills=common_skills,
            seniority_level=seniority_level,
            experience_years=candidate.years_experience,
            jaccard_weight=self.jaccard_weight,
            guttman_weight=self.guttman_weight
        )
    
    def _jaccard_similarity_detailed(self, required: List[str], candidate: List[str]) -> Tuple[float, List[str], List[str]]:
        """
        Calculate Jaccard similarity with detailed breakdown.
        
        Args:
            required: Required skills from job posting
            candidate: Skills possessed by candidate
            
        Returns:
            Tuple of (similarity_score, missing_skills, common_skills)
        """
        set_required = set(skill.lower() for skill in required)
        set_candidate = set(skill.lower() for skill in candidate)
        
        intersection = set_required & set_candidate
        missing = set_required - set_candidate
        union = set_required | set_candidate
        
        score = len(intersection) / len(union) if len(union) > 0 else 0.0
        
        # Map back to original case
        missing_skills = [s for s in required if s.lower() in missing]
        common_skills = [s for s in required if s.lower() in intersection]
        
        return score, missing_skills, common_skills
    
    def _guttman_scaling_detailed(self, job: JobPosting, candidate: Candidate) -> Tuple[float, str]:
        """
        Calculate Guttman scaling score with detailed breakdown.
        
        This is a simplified implementation. You should replace this with your
        actual Guttman scaling algorithm that considers skill hierarchies.
        
        Args:
            job: Job posting
            candidate: Candidate profile
            
        Returns:
            Tuple of (guttman_score, seniority_level)
        """
        # Experience-based scoring
        experience_score = min(candidate.years_experience / 10.0, 1.0)
        
        # Title-based scoring
        title_score = self._title_to_score(candidate.current_title)
        
        # Skill proficiency scoring (if available)
        proficiency_score = self._calculate_proficiency_score(candidate.skill_proficiencies)
        
        # Combine components
        guttman_score = (experience_score * 0.4) + (title_score * 0.4) + (proficiency_score * 0.2)
        
        # Determine seniority level
        seniority_level = self._determine_seniority_level(
            candidate.years_experience, candidate.current_title
        )
        
        return guttman_score, seniority_level
    
    def _title_to_score(self, title: str) -> float:
        """Convert job title to a score based on seniority"""
        title_lower = title.lower()
        
        if any(word in title_lower for word in ['lead', 'principal', 'architect', 'director']):
            return 1.0
        elif 'senior' in title_lower:
            return 0.8
        elif any(word in title_lower for word in ['mid', 'intermediate', 'level']):
            return 0.5
        elif 'junior' in title_lower or 'entry' in title_lower:
            return 0.3
        else:
            return 0.5  # Default for unknown titles
    
    def _calculate_proficiency_score(self, proficiencies: Dict[str, str]) -> float:
        """Calculate average proficiency score"""
        if not proficiencies:
            return 0.5  # Default
        
        proficiency_map = {
            'expert': 1.0,
            'advanced': 0.8,
            'intermediate': 0.5,
            'beginner': 0.3,
            'novice': 0.2
        }
        
        scores = []
        for skill, level in proficiencies.items():
            level_lower = level.lower()
            score = proficiency_map.get(level_lower, 0.5)
            scores.append(score)
        
        return sum(scores) / len(scores) if scores else 0.5
    
    def _determine_seniority_level(self, years_experience: int, title: str) -> str:
        """Determine seniority level based on experience and title"""
        title_lower = title.lower()
        
        # Check title first
        if any(word in title_lower for word in ['lead', 'principal', 'architect', 'director']):
            return "Senior"
        elif 'senior' in title_lower:
            return "Senior"
        elif 'junior' in title_lower or 'entry' in title_lower:
            return "Junior"
        
        # Fall back to experience
        if years_experience >= 7:
            return "Senior"
        elif years_experience >= 3:
            return "Mid-level"
        else:
            return "Junior"

