"""
Example implementation of evaluation protocols for LinkedIn Assistant.
This file provides a concrete example of how to structure the evaluation tests.
"""

from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
from copy import deepcopy
import json


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class Candidate:
    id: str
    name: str
    current_title: str
    skills: List[str]
    years_experience: int
    skill_proficiencies: Dict[str, str]  # skill_name -> proficiency_level


@dataclass
class JobPosting:
    id: str
    title: str
    required_skills: List[str]
    experience_level: str  # e.g., "Senior", "Mid-level", "Junior"


# ============================================================================
# Mock Hybrid Algorithm (Replace with your actual implementation)
# ============================================================================

class HybridAlgorithm:
    """
    Mock implementation - Replace with your actual Hybrid Algorithm
    that uses Jaccard similarity and Guttman scaling.
    """
    
    def calculate_match_score(self, job: JobPosting, candidate: Candidate) -> float:
        """Calculate match score (simplified version)"""
        # Mock implementation - replace with actual algorithm
        jaccard_score = self._jaccard_similarity(job.required_skills, candidate.skills)
        guttman_score = self._guttman_scaling(job, candidate)
        return (jaccard_score * 0.6) + (guttman_score * 0.4)
    
    def calculate_match_score_detailed(self, job: JobPosting, candidate: Candidate) -> Dict[str, Any]:
        """Calculate match score with detailed breakdown"""
        jaccard_score, missing_skills, common_skills = self._jaccard_similarity_detailed(
            job.required_skills, candidate.skills
        )
        guttman_score, seniority_level = self._guttman_scaling_detailed(job, candidate)
        
        total_score = (jaccard_score * 0.6) + (guttman_score * 0.4)
        
        return {
            'total': total_score,
            'jaccard_similarity': jaccard_score,
            'guttman_scaling': guttman_score,
            'missing_skills': missing_skills,
            'common_skills': common_skills,
            'seniority_level': seniority_level,
            'experience_years': candidate.years_experience
        }
    
    def _jaccard_similarity(self, required: List[str], candidate: List[str]) -> float:
        """Calculate Jaccard similarity"""
        set_required = set(required)
        set_candidate = set(candidate)
        intersection = len(set_required & set_candidate)
        union = len(set_required | set_candidate)
        return intersection / union if union > 0 else 0.0
    
    def _jaccard_similarity_detailed(self, required: List[str], candidate: List[str]) -> Tuple[float, List[str], List[str]]:
        """Calculate Jaccard similarity with details"""
        set_required = set(required)
        set_candidate = set(candidate)
        intersection = set_required & set_candidate
        missing = set_required - set_candidate
        
        union = len(set_required | set_candidate)
        score = len(intersection) / union if union > 0 else 0.0
        
        return score, list(missing), list(intersection)
    
    def _guttman_scaling(self, job: JobPosting, candidate: Candidate) -> float:
        """Calculate Guttman scaling score (simplified)"""
        # Mock implementation - replace with actual Guttman scaling
        experience_score = min(candidate.years_experience / 10.0, 1.0)
        title_score = self._title_to_score(candidate.current_title)
        return (experience_score + title_score) / 2.0
    
    def _guttman_scaling_detailed(self, job: JobPosting, candidate: Candidate) -> Tuple[float, str]:
        """Calculate Guttman scaling with details"""
        experience_score = min(candidate.years_experience / 10.0, 1.0)
        title_score = self._title_to_score(candidate.current_title)
        score = (experience_score + title_score) / 2.0
        
        # Determine seniority level
        if candidate.years_experience >= 7:
            seniority = "Senior"
        elif candidate.years_experience >= 3:
            seniority = "Mid-level"
        else:
            seniority = "Junior"
        
        return score, seniority
    
    def _title_to_score(self, title: str) -> float:
        """Convert job title to score"""
        title_lower = title.lower()
        if 'lead' in title_lower or 'principal' in title_lower:
            return 1.0
        elif 'senior' in title_lower:
            return 0.8
        elif 'mid' in title_lower or 'intermediate' in title_lower:
            return 0.5
        else:
            return 0.3


# ============================================================================
# Skill Degradation Test Components
# ============================================================================

class SkillDegradationEngine:
    """Engine for degrading candidate skills systematically"""
    
    def __init__(self):
        self.title_downgrade_map = {
            "Lead Architect": "Junior Developer",
            "Senior Engineer": "Junior Developer",
            "Principal Engineer": "Mid-level Engineer",
            "Senior Software Engineer": "Junior Developer",
            "Lead Developer": "Junior Developer",
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
    
    def find_critical_point(self, decay_metrics: List[Dict], threshold: float = 0.5) -> int:
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
    
    def run_test(self, job: JobPosting, candidates: List[Candidate], degradation_steps: List[Dict] = None) -> Dict:
        """Run skill degradation test"""
        # Step 1: Find perfect match
        perfect_matches = self.find_perfect_match_candidates(job, candidates, top_n=1)
        if not perfect_matches:
            return {'error': 'No candidates found'}
        
        candidate, original_score = perfect_matches[0]
        
        # Step 2: Define default degradation sequence if not provided
        if degradation_steps is None:
            degradation_steps = [
                {'type': 'title', 'value': 'Junior Developer'},
                {'type': 'remove_skill', 'value': job.required_skills[0] if job.required_skills else 'Python'},
                {'type': 'remove_skill', 'value': job.required_skills[1] if len(job.required_skills) > 1 else 'Java'},
                {'type': 'reduce_experience', 'years': 3},
            ]
        
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
                'skills': candidate.skills
            },
            'degradation_steps': degradation_steps,
            'decay_metrics': decay_metrics,
            'critical_point': critical_point,
            'final_score': degraded_scores[-1] if degraded_scores else None
        }


# ============================================================================
# Explainability Test Components
# ============================================================================

class ScoringBreakdownExtractor:
    """Extract detailed breakdown from scoring algorithm"""
    
    def __init__(self, hybrid_algorithm: HybridAlgorithm):
        self.algorithm = hybrid_algorithm
    
    def extract_breakdown(self, job: JobPosting, candidate_a: Candidate, candidate_b: Candidate) -> Dict:
        """Extract detailed scoring breakdown for comparison"""
        score_a = self.algorithm.calculate_match_score_detailed(job, candidate_a)
        score_b = self.algorithm.calculate_match_score_detailed(job, candidate_b)
        
        return {
            'candidate_a': {
                'id': candidate_a.id,
                'score': score_a['total'],
                'jaccard': score_a['jaccard_similarity'],
                'guttman': score_a['guttman_scaling'],
                'missing_skills': score_a['missing_skills'],
                'seniority_level': score_a['seniority_level']
            },
            'candidate_b': {
                'id': candidate_b.id,
                'score': score_b['total'],
                'jaccard': score_b['jaccard_similarity'],
                'guttman': score_b['guttman_scaling'],
                'missing_skills': score_b['missing_skills'],
                'seniority_level': score_b['seniority_level']
            }
        }


class RecruiterAgent:
    """Mock Recruiter Agent - Replace with actual LLM integration"""
    
    def __init__(self, use_llm: bool = False):
        self.use_llm = use_llm
        # In real implementation, initialize LLM client here
        # self.llm_client = OpenAI() or Anthropic() etc.
    
    def generate_explanation(self, job: JobPosting, candidate_a: Candidate, 
                           candidate_b: Candidate, score_a: float, score_b: float) -> str:
        """Generate natural language explanation"""
        if self.use_llm:
            # Real implementation would call LLM here
            prompt = self._build_prompt(job, candidate_a, candidate_b, score_a, score_b)
            # explanation = self.llm_client.generate(prompt)
            # return explanation
            pass
        
        # Mock explanation for testing
        missing_skills_b = set(job.required_skills) - set(candidate_b.skills)
        missing_skills_a = set(job.required_skills) - set(candidate_a.skills)
        
        explanation_parts = []
        
        if len(missing_skills_b) > len(missing_skills_a):
            explanation_parts.append(
                f"Candidate B is missing key skills: {', '.join(missing_skills_b)}"
            )
        
        if candidate_a.years_experience > candidate_b.years_experience:
            explanation_parts.append(
                f"Candidate A has more experience ({candidate_a.years_experience} years vs "
                f"{candidate_b.years_experience} years)"
            )
        
        if 'Senior' in candidate_a.current_title and 'Junior' in candidate_b.current_title:
            explanation_parts.append(
                f"Candidate A has a more senior title ({candidate_a.current_title}) compared to "
                f"Candidate B ({candidate_b.current_title})"
            )
        
        return ". ".join(explanation_parts) if explanation_parts else "Both candidates are similar."
    
    def _build_prompt(self, job: JobPosting, candidate_a: Candidate, 
                     candidate_b: Candidate, score_a: float, score_b: float) -> str:
        """Build prompt for LLM"""
        return f"""
You are a professional recruiter evaluating candidates for a job posting.

Job Posting:
Title: {job.title}
Required Skills: {', '.join(job.required_skills)}
Experience Level: {job.experience_level}

Candidate A:
Name: {candidate_a.name}
Title: {candidate_a.current_title}
Skills: {', '.join(candidate_a.skills)}
Experience: {candidate_a.years_experience} years
Match Score: {score_a}

Candidate B:
Name: {candidate_b.name}
Title: {candidate_b.current_title}
Skills: {', '.join(candidate_b.skills)}
Experience: {candidate_b.years_experience} years
Match Score: {score_b}

Question: Why did you rank Candidate A higher than Candidate B?

Please provide a detailed explanation that mentions:
- Missing skills (if any)
- Seniority/experience differences
- Any other relevant factors
"""


class ExplanationValidator:
    """Validate Recruiter Agent explanations against scoring breakdown"""
    
    def validate_explanation(self, explanation: str, scoring_breakdown: Dict) -> Dict:
        """Validate that explanation mentions key factors"""
        validation_results = {
            'mentions_missing_skills': False,
            'mentions_seniority': False,
            'missing_skills_coverage': [],
            'seniority_mentions': [],
            'alignment_score': 0.0
        }
        
        explanation_lower = explanation.lower()
        
        # Extract missing skills from breakdown
        missing_skills_a = scoring_breakdown['candidate_a']['missing_skills']
        missing_skills_b = scoring_breakdown['candidate_b']['missing_skills']
        
        # Check if explanation mentions missing skills
        for skill in missing_skills_a + missing_skills_b:
            if skill.lower() in explanation_lower:
                validation_results['mentions_missing_skills'] = True
                validation_results['missing_skills_coverage'].append(skill)
        
        # Check for seniority-related keywords
        seniority_keywords = [
            'senior', 'junior', 'experience', 'years', 'level',
            'seniority', 'expertise', 'proficiency', 'advanced'
        ]
        for keyword in seniority_keywords:
            if keyword in explanation_lower:
                validation_results['mentions_seniority'] = True
                validation_results['seniority_mentions'].append(keyword)
        
        # Calculate alignment score
        alignment_score = self._calculate_alignment(explanation, scoring_breakdown)
        validation_results['alignment_score'] = alignment_score
        
        return validation_results
    
    def _calculate_alignment(self, explanation: str, scoring_breakdown: Dict) -> float:
        """Calculate how well explanation aligns with scoring breakdown"""
        key_factors = []
        explanation_lower = explanation.lower()
        
        # Missing skills factor
        if scoring_breakdown['candidate_a']['missing_skills']:
            key_factors.append('missing_skills_a')
        if scoring_breakdown['candidate_b']['missing_skills']:
            key_factors.append('missing_skills_b')
        
        # Seniority factor
        seniority_a = scoring_breakdown['candidate_a']['seniority_level']
        seniority_b = scoring_breakdown['candidate_b']['seniority_level']
        if seniority_a != seniority_b:
            key_factors.append('seniority_difference')
        
        if len(key_factors) == 0:
            return 1.0
        
        mentioned_factors = 0
        
        if 'missing_skills_a' in key_factors or 'missing_skills_b' in key_factors:
            if any(keyword in explanation_lower for keyword in ['skill', 'missing', 'lack', "doesn't have", 'does not have']):
                mentioned_factors += 1
        
        if 'seniority_difference' in key_factors:
            if any(keyword in explanation_lower for keyword in ['senior', 'junior', 'experience', 'level', 'years']):
                mentioned_factors += 1
        
        return mentioned_factors / len(key_factors) if len(key_factors) > 0 else 1.0


class ExplainabilityTest:
    """Orchestrator for explainability test"""
    
    def __init__(self, hybrid_algorithm: HybridAlgorithm):
        self.algorithm = hybrid_algorithm
        self.recruiter_agent = RecruiterAgent(use_llm=False)  # Set to True when LLM is integrated
        self.breakdown_extractor = ScoringBreakdownExtractor(hybrid_algorithm)
        self.validator = ExplanationValidator()
    
    def _get_ranked_pairs(self, job: JobPosting, candidates: List[Candidate]) -> List[Tuple[Candidate, Candidate]]:
        """Get all pairs where first candidate ranks higher"""
        scores = []
        for candidate in candidates:
            score = self.algorithm.calculate_match_score(job, candidate)
            scores.append((candidate, score))
        
        scores.sort(key=lambda x: x[1], reverse=True)
        
        pairs = []
        for i in range(len(scores)):
            for j in range(i + 1, len(scores)):
                pairs.append((scores[i][0], scores[j][0]))
        
        return pairs
    
    def run_test(self, job: JobPosting, candidates: List[Candidate]) -> Dict:
        """Run explainability test for all candidate pairs"""
        results = []
        
        candidate_pairs = self._get_ranked_pairs(job, candidates)
        
        for candidate_a, candidate_b in candidate_pairs:
            # Calculate scores
            score_a = self.algorithm.calculate_match_score(job, candidate_a)
            score_b = self.algorithm.calculate_match_score(job, candidate_b)
            
            # Generate explanation
            explanation = self.recruiter_agent.generate_explanation(
                job, candidate_a, candidate_b, score_a, score_b
            )
            
            # Extract breakdown
            breakdown = self.breakdown_extractor.extract_breakdown(job, candidate_a, candidate_b)
            
            # Validate explanation
            validation = self.validator.validate_explanation(explanation, breakdown)
            
            results.append({
                'candidate_a': candidate_a.id,
                'candidate_b': candidate_b.id,
                'score_a': score_a,
                'score_b': score_b,
                'explanation': explanation,
                'breakdown': breakdown,
                'validation': validation
            })
        
        return self._generate_report(results)
    
    def _generate_report(self, results: List[Dict]) -> Dict:
        """Generate evaluation report"""
        if not results:
            return {'error': 'No test results'}
        
        total_tests = len(results)
        mentions_missing_skills = sum(1 for r in results if r['validation']['mentions_missing_skills'])
        mentions_seniority = sum(1 for r in results if r['validation']['mentions_seniority'])
        avg_alignment = sum(r['validation']['alignment_score'] for r in results) / total_tests
        
        return {
            'total_tests': total_tests,
            'mentions_missing_skills_rate': mentions_missing_skills / total_tests,
            'mentions_seniority_rate': mentions_seniority / total_tests,
            'average_alignment_score': avg_alignment,
            'detailed_results': results
        }


# ============================================================================
# Example Usage
# ============================================================================

def example_usage():
    """Example of how to use the evaluation tests"""
    
    # Create sample data
    job = JobPosting(
        id="job1",
        title="Senior Software Engineer",
        required_skills=["Python", "Java", "System Design", "AWS"],
        experience_level="Senior"
    )
    
    candidates = [
        Candidate(
            id="cand1",
            name="Alice",
            current_title="Lead Architect",
            skills=["Python", "Java", "System Design", "AWS", "Docker"],
            years_experience=8,
            skill_proficiencies={"Python": "Expert", "Java": "Advanced"}
        ),
        Candidate(
            id="cand2",
            name="Bob",
            current_title="Junior Developer",
            skills=["Python", "JavaScript"],
            years_experience=2,
            skill_proficiencies={"Python": "Intermediate"}
        ),
        Candidate(
            id="cand3",
            name="Charlie",
            current_title="Senior Engineer",
            skills=["Python", "Java", "AWS"],
            years_experience=6,
            skill_proficiencies={"Python": "Advanced", "Java": "Advanced"}
        ),
    ]
    
    # Initialize algorithm
    algorithm = HybridAlgorithm()
    
    # Run Skill Degradation Test
    print("=" * 60)
    print("SKILL DEGRADATION TEST")
    print("=" * 60)
    degradation_test = SkillDegradationTest(algorithm)
    degradation_results = degradation_test.run_test(job, candidates)
    print(json.dumps(degradation_results, indent=2))
    
    # Run Explainability Test
    print("\n" + "=" * 60)
    print("EXPLAINABILITY TEST")
    print("=" * 60)
    explainability_test = ExplainabilityTest(algorithm)
    explainability_results = explainability_test.run_test(job, candidates)
    print(f"Total Tests: {explainability_results['total_tests']}")
    print(f"Missing Skills Mention Rate: {explainability_results['mentions_missing_skills_rate']:.2%}")
    print(f"Seniority Mention Rate: {explainability_results['mentions_seniority_rate']:.2%}")
    print(f"Average Alignment Score: {explainability_results['average_alignment_score']:.2f}")


if __name__ == "__main__":
    example_usage()

