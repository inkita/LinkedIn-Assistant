"""
Skill Degradation Test - Measures score decay rate as candidate skills are degraded.
"""

from typing import List, Dict, Tuple, Optional
from copy import deepcopy
from ..models import Candidate, JobPosting
from ..algorithm import HybridAlgorithm


class SkillDegradationEngine:
    """Engine for degrading candidate skills systematically"""
    
    def __init__(self):
        self.title_downgrade_map = {
            "Lead Architect": "Junior Developer",
            "Senior Engineer": "Junior Developer",
            "Principal Engineer": "Mid-level Engineer",
            "Senior Software Engineer": "Junior Developer",
            "Lead Developer": "Junior Developer",
            "Principal Software Engineer": "Mid-level Engineer",
        }
    
    def degrade_title(self, candidate: Candidate, target_title: str) -> Candidate:
        """Downgrade candidate's job title"""
        degraded = deepcopy(candidate)
        degraded.current_title = target_title
        return degraded
    
    def remove_skill(self, candidate: Candidate, skill_name: str) -> Candidate:
        """Remove a skill from candidate"""
        degraded = deepcopy(candidate)
        if skill_name in degraded.skills:
            degraded.skills.remove(skill_name)
        if skill_name in degraded.skill_proficiencies:
            del degraded.skill_proficiencies[skill_name]
        return degraded
    
    def reduce_skill_level(self, candidate: Candidate, skill_name: str, new_level: str) -> Candidate:
        """Reduce skill proficiency level"""
        degraded = deepcopy(candidate)
        if skill_name in degraded.skill_proficiencies:
            degraded.skill_proficiencies[skill_name] = new_level
        return degraded
    
    def reduce_experience(self, candidate: Candidate, years: int) -> Candidate:
        """Reduce years of experience"""
        degraded = deepcopy(candidate)
        degraded.years_experience = max(0, degraded.years_experience - years)
        return degraded
    
    def apply_degradation_sequence(self, candidate: Candidate, degradation_steps: List[Dict]) -> List[Candidate]:
        """Apply multiple degradations in sequence"""
        degraded_candidates = []
        current_candidate = candidate
        
        for step in degradation_steps:
            if step['type'] == 'title':
                current_candidate = self.degrade_title(current_candidate, step['value'])
            elif step['type'] == 'remove_skill':
                current_candidate = self.remove_skill(current_candidate, step['value'])
            elif step['type'] == 'reduce_skill_level':
                current_candidate = self.reduce_skill_level(
                    current_candidate, step['skill'], step['level']
                )
            elif step['type'] == 'reduce_experience':
                current_candidate = self.reduce_experience(current_candidate, step['years'])
            else:
                raise ValueError(f"Unknown degradation type: {step['type']}")
            
            degraded_candidates.append(deepcopy(current_candidate))
        
        return degraded_candidates


class ScoreDecayAnalyzer:
    """Analyze score decay rate during degradation"""
    
    def calculate_decay_rate(self, original_score: float, degraded_scores: List[float]) -> List[Dict]:
        """Calculate decay metrics for each degradation step"""
        decay_metrics = []
        
        for i, score in enumerate(degraded_scores):
            if i == 0:
                absolute_decay = original_score - score
                percentage_decay = (absolute_decay / original_score) * 100 if original_score > 0 else 0
            else:
                absolute_decay = degraded_scores[i-1] - score
                percentage_decay = (absolute_decay / degraded_scores[i-1]) * 100 if degraded_scores[i-1] > 0 else 0
            
            cumulative_decay = ((original_score - score) / original_score) * 100 if original_score > 0 else 0
            
            decay_metrics.append({
                'step': i + 1,
                'score': score,
                'absolute_decay': absolute_decay,
                'percentage_decay': percentage_decay,
                'cumulative_decay': cumulative_decay
            })
        
        return decay_metrics
    
    def find_critical_point(self, decay_metrics: List[Dict], threshold: float = 0.5) -> Optional[int]:
        """Find when score drops below threshold (e.g., 50% of original)"""
        for metric in decay_metrics:
            if metric['cumulative_decay'] >= (threshold * 100):
                return metric['step']
        return None


class SkillDegradationTest:
    """Orchestrator for skill degradation test"""
    
    def __init__(self, hybrid_algorithm: HybridAlgorithm):
        self.algorithm = hybrid_algorithm
        self.degradation_engine = SkillDegradationEngine()
        self.analyzer = ScoreDecayAnalyzer()
    
    def find_perfect_match_candidates(self, job: JobPosting, candidates: List[Candidate], top_n: int = 5) -> List[Tuple[Candidate, float]]:
        """Find candidates with highest match scores"""
        scores = []
        for candidate in candidates:
            score = self.algorithm.calculate_match_score(job, candidate)
            scores.append((candidate, score))
        return sorted(scores, key=lambda x: x[1], reverse=True)[:top_n]
    
    def run_test(self, job: JobPosting, candidates: List[Candidate], 
                 degradation_steps: Optional[List[Dict]] = None) -> Dict:
        """
        Run skill degradation test.
        
        Args:
            job: Job posting to match against
            candidates: List of candidates
            degradation_steps: Optional custom degradation sequence
            
        Returns:
            Dictionary with test results including decay metrics
        """
        # Step 1: Find perfect match
        perfect_matches = self.find_perfect_match_candidates(job, candidates, top_n=1)
        if not perfect_matches:
            return {'error': 'No candidates found'}
        
        candidate, original_score = perfect_matches[0]
        
        # Step 2: Define default degradation sequence if not provided
        if degradation_steps is None:
            degradation_steps = self._get_default_degradation_steps(job)
        
        # Step 3: Apply degradations and measure scores
        degraded_candidates = self.degradation_engine.apply_degradation_sequence(candidate, degradation_steps)
        
        degraded_scores = []
        for degraded_candidate in degraded_candidates:
            score = self.algorithm.calculate_match_score(job, degraded_candidate)
            degraded_scores.append(score)
        
        # Step 4: Analyze decay
        decay_metrics = self.analyzer.calculate_decay_rate(original_score, degraded_scores)
        critical_point = self.analyzer.find_critical_point(decay_metrics)
        
        # Step 5: Generate report
        return {
            'original_score': original_score,
            'original_candidate': {
                'id': candidate.id,
                'name': candidate.name,
                'title': candidate.current_title,
                'skills': candidate.skills,
                'years_experience': candidate.years_experience
            },
            'degradation_steps': degradation_steps,
            'decay_metrics': decay_metrics,
            'critical_point': critical_point,
            'final_score': degraded_scores[-1] if degraded_scores else None,
            'total_degradation': original_score - (degraded_scores[-1] if degraded_scores else original_score),
            'total_degradation_percentage': ((original_score - (degraded_scores[-1] if degraded_scores else original_score)) / original_score * 100) if original_score > 0 else 0
        }
    
    def _get_default_degradation_steps(self, job: JobPosting) -> List[Dict]:
        """Generate default degradation steps based on job requirements"""
        steps = []
        
        # Degrade title
        steps.append({'type': 'title', 'value': 'Junior Developer'})
        
        # Remove skills progressively
        if job.required_skills:
            # Remove first required skill
            steps.append({'type': 'remove_skill', 'value': job.required_skills[0]})
            
            # Remove second skill if available
            if len(job.required_skills) > 1:
                steps.append({'type': 'remove_skill', 'value': job.required_skills[1]})
        
        # Reduce experience
        steps.append({'type': 'reduce_experience', 'years': 3})
        
        return steps

