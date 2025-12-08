"""
Data models for candidates and job postings.
"""

from dataclasses import dataclass
from typing import List, Dict, Optional


@dataclass
class Candidate:
    """Represents a job candidate"""
    id: str
    name: str
    current_title: str
    skills: List[str]
    years_experience: int
    skill_proficiencies: Dict[str, str]  # skill_name -> proficiency_level
    email: Optional[str] = None
    location: Optional[str] = None
    
    def __post_init__(self):
        """Validate candidate data"""
        if not self.skills:
            self.skills = []
        if not self.skill_proficiencies:
            self.skill_proficiencies = {}


@dataclass
class JobPosting:
    """Represents a job posting"""
    id: str
    title: str
    required_skills: List[str]
    experience_level: str  # e.g., "Senior", "Mid-level", "Junior"
    description: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    
    def __post_init__(self):
        """Validate job posting data"""
        if not self.required_skills:
            self.required_skills = []


@dataclass
class ScoreBreakdown:
    """Detailed breakdown of a match score"""
    total: float
    jaccard_similarity: float
    guttman_scaling: float
    missing_skills: List[str]
    common_skills: List[str]
    seniority_level: str
    experience_years: int
    jaccard_weight: float = 0.6
    guttman_weight: float = 0.4

