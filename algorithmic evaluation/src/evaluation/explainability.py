"""
Explainability Test - Validates Recruiter Agent explanations against scoring breakdown.
"""

from typing import List, Dict, Tuple, Optional
from ..models import Candidate, JobPosting
from ..algorithm import HybridAlgorithm


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
                'name': candidate_a.name,
                'score': score_a.total,
                'jaccard': score_a.jaccard_similarity,
                'guttman': score_a.guttman_scaling,
                'missing_skills': score_a.missing_skills,
                'common_skills': score_a.common_skills,  # Added for skill coverage validation
                'seniority_level': score_a.seniority_level,
                'experience_years': score_a.experience_years
            },
            'candidate_b': {
                'id': candidate_b.id,
                'name': candidate_b.name,
                'score': score_b.total,
                'jaccard': score_b.jaccard_similarity,
                'guttman': score_b.guttman_scaling,
                'missing_skills': score_b.missing_skills,
                'common_skills': score_b.common_skills,  # Added for skill coverage validation
                'seniority_level': score_b.seniority_level,
                'experience_years': score_b.experience_years
            }
        }


class RecruiterAgent:
    """Recruiter Agent that generates natural language explanations"""
    
    def __init__(self, use_llm: bool = False, llm_client=None, model: str = "gpt-4"):
        """
        Initialize Recruiter Agent.
        
        Args:
            use_llm: Whether to use actual LLM (requires API key)
            llm_client: LLM client instance (OpenAI, Anthropic, etc.)
            model: Model name to use
        """
        self.use_llm = use_llm
        self.llm_client = llm_client
        self.model = model
    
    def generate_explanation(self, job: JobPosting, candidate_a: Candidate, 
                           candidate_b: Candidate, score_a: float, score_b: float) -> str:
        """Generate natural language explanation"""
        if self.use_llm and self.llm_client:
            return self._generate_llm_explanation(job, candidate_a, candidate_b, score_a, score_b)
        else:
            return self._generate_mock_explanation(job, candidate_a, candidate_b, score_a, score_b)
    
    def _generate_llm_explanation(self, job: JobPosting, candidate_a: Candidate,
                                 candidate_b: Candidate, score_a: float, score_b: float) -> str:
        """Generate explanation using LLM"""
        prompt = self._build_prompt(job, candidate_a, candidate_b, score_a, score_b)
        
        # Try OpenAI format first
        if hasattr(self.llm_client, 'chat'):
            response = self.llm_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a professional recruiter evaluating candidates."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )
            return response.choices[0].message.content
        # Try Anthropic format
        elif hasattr(self.llm_client, 'messages'):
            message = self.llm_client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}]
            )
            return message.content[0].text
        else:
            raise ValueError("Unsupported LLM client format")
    
    def _generate_mock_explanation(self, job: JobPosting, candidate_a: Candidate,
                                  candidate_b: Candidate, score_a: float, score_b: float) -> str:
        """Generate mock explanation for testing"""
        missing_skills_b = set(skill.lower() for skill in job.required_skills) - set(skill.lower() for skill in candidate_b.skills)
        missing_skills_a = set(skill.lower() for skill in job.required_skills) - set(skill.lower() for skill in candidate_a.skills)
        
        explanation_parts = []
        
        # Always mention missing skills if they exist (more consistent)
        if missing_skills_b:
            # Map back to original case
            missing_b_original = [s for s in job.required_skills if s.lower() in missing_skills_b]
            explanation_parts.append(
                f"Candidate B is missing key skills: {', '.join(missing_b_original[:5])}"
                + (f" and {len(missing_b_original) - 5} more" if len(missing_b_original) > 5 else "")
            )
        
        if missing_skills_a:
            missing_a_original = [s for s in job.required_skills if s.lower() in missing_skills_a]
            explanation_parts.append(
                f"Candidate A is missing key skills: {', '.join(missing_a_original[:5])}"
                + (f" and {len(missing_a_original) - 5} more" if len(missing_a_original) > 5 else "")
            )
        
        # Compare skill coverage/completeness (replaced seniority)
        skills_a = set(skill.lower() for skill in candidate_a.skills)
        skills_b = set(skill.lower() for skill in candidate_b.skills)
        required_skills_set = set(skill.lower() for skill in job.required_skills)
        
        matching_a = len(skills_a & required_skills_set)
        matching_b = len(skills_b & required_skills_set)
        
        if matching_a > matching_b:
            explanation_parts.append(
                f"Candidate A has more matching skills ({matching_a} vs {matching_b}) and better skill coverage"
            )
        elif matching_b > matching_a:
            explanation_parts.append(
                f"Candidate B has more matching skills ({matching_b} vs {matching_a}) and better skill coverage"
            )
        
        # Compare total skill count if significantly different
        total_skills_diff = abs(len(candidate_a.skills) - len(candidate_b.skills))
        if total_skills_diff > 3:
            if len(candidate_a.skills) > len(candidate_b.skills):
                explanation_parts.append(
                    f"Candidate A has a broader skill set ({len(candidate_a.skills)} skills vs "
                    f"{len(candidate_b.skills)} skills)"
                )
            else:
                explanation_parts.append(
                    f"Candidate B has a broader skill set ({len(candidate_b.skills)} skills vs "
                    f"{len(candidate_a.skills)} skills)"
                )
        
        # Score difference context
        score_diff = abs(score_a - score_b)
        if score_diff > 0.05:
            explanation_parts.append(
                f"The match score difference ({score_diff:.2f}) reflects these factors."
            )
        
        return ". ".join(explanation_parts) if explanation_parts else "Both candidates have similar qualifications."
    
    def _build_prompt(self, job: JobPosting, candidate_a: Candidate, 
                     candidate_b: Candidate, score_a: float, score_b: float) -> str:
        """Build prompt for LLM"""
        return f"""You are a professional recruiter evaluating candidates for a job posting.

Job Posting:
Title: {job.title}
Required Skills: {', '.join(job.required_skills)}
Experience Level: {job.experience_level}
{f'Description: {job.description[:200]}...' if job.description else ''}

Candidate A:
Name: {candidate_a.name}
Title: {candidate_a.current_title}
Skills: {', '.join(candidate_a.skills)}
Experience: {candidate_a.years_experience} years
Match Score: {score_a:.3f}

Candidate B:
Name: {candidate_b.name}
Title: {candidate_b.current_title}
Skills: {', '.join(candidate_b.skills)}
Experience: {candidate_b.years_experience} years
Match Score: {score_b:.3f}

Question: Why did you rank Candidate A higher than Candidate B?

Please provide a detailed explanation that mentions:
- Missing skills (if any)
- Seniority/experience differences
- Any other relevant factors that influenced the ranking

Be specific and reference the actual skills and qualifications mentioned above."""


class ExplanationValidator:
    """Validate Recruiter Agent explanations against scoring breakdown"""
    
    def validate_explanation(self, explanation: str, scoring_breakdown: Dict) -> Dict:
        """Validate that explanation mentions key factors"""
        validation_results = {
            'mentions_missing_skills': False,
            'mentions_skill_coverage': False,  # Replaced seniority with skill coverage
            'missing_skills_coverage': [],
            'skill_coverage_mentions': [],
            'alignment_score': 0.0
        }
        
        explanation_lower = explanation.lower()
        
        # Extract missing skills from breakdown
        missing_skills_a = scoring_breakdown['candidate_a']['missing_skills']
        missing_skills_b = scoring_breakdown['candidate_b']['missing_skills']
        
        # Check if explanation mentions missing skills (more lenient matching)
        for skill in missing_skills_a + missing_skills_b:
            skill_lower = skill.lower()
            # Check for exact match or partial match (e.g., "python" matches "python programming")
            if (skill_lower in explanation_lower or 
                any(skill_lower in word or word in skill_lower for word in explanation_lower.split() if len(word) > 3)):
                validation_results['mentions_missing_skills'] = True
                validation_results['missing_skills_coverage'].append(skill)
        
        # Also check for generic mentions of missing skills
        if any(keyword in explanation_lower for keyword in ['missing', 'lack', "doesn't have", 'does not have', 'without', 'missing key']):
            if missing_skills_a or missing_skills_b:
                validation_results['mentions_missing_skills'] = True
        
        # Check for skill coverage/completeness mentions (replaced seniority)
        skill_coverage_keywords = [
            'more skills', 'fewer skills', 'skill count', 'skill coverage',
            'more matching', 'better match', 'more qualified', 'better qualified',
            'has more', 'has fewer', 'skill set', 'qualifications',
            'proficiency', 'expertise', 'competency', 'capability', 'broader skill'
        ]
        for keyword in skill_coverage_keywords:
            if keyword in explanation_lower:
                validation_results['mentions_skill_coverage'] = True
                validation_results['skill_coverage_mentions'].append(keyword)
        
        # Also check for skill count differences
        common_skills_a = len(scoring_breakdown['candidate_a'].get('common_skills', []))
        common_skills_b = len(scoring_breakdown['candidate_b'].get('common_skills', []))
        if abs(common_skills_a - common_skills_b) > 0:
            # Check if explanation mentions skill count differences
            if any(phrase in explanation_lower for phrase in [
                'more skills', 'fewer skills', 'skill count', 
                f'{common_skills_a} vs {common_skills_b}', f'{common_skills_b} vs {common_skills_a}',
                'more matching', 'better skill coverage'
            ]):
                validation_results['mentions_skill_coverage'] = True
        
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
        
        # Skill coverage factor (replaced seniority)
        common_skills_a = len(scoring_breakdown['candidate_a'].get('common_skills', []))
        common_skills_b = len(scoring_breakdown['candidate_b'].get('common_skills', []))
        if abs(common_skills_a - common_skills_b) > 1:  # Significant difference
            key_factors.append('skill_coverage_difference')
        
        if len(key_factors) == 0:
            return 1.0  # No factors to mention
        
        mentioned_factors = 0
        
        if 'missing_skills_a' in key_factors or 'missing_skills_b' in key_factors:
            if any(keyword in explanation_lower for keyword in ['skill', 'missing', 'lack', "doesn't have", 'does not have', 'without']):
                mentioned_factors += 1
        
        if 'skill_coverage_difference' in key_factors:
            if any(keyword in explanation_lower for keyword in [
                'more skills', 'fewer skills', 'skill count', 'skill coverage',
                'more matching', 'better match', 'more qualified', 'qualifications'
            ]):
                mentioned_factors += 1
        
        return mentioned_factors / len(key_factors) if len(key_factors) > 0 else 1.0


class ExplainabilityTest:
    """Orchestrator for explainability test"""
    
    def __init__(self, hybrid_algorithm: HybridAlgorithm, recruiter_agent: Optional[RecruiterAgent] = None):
        self.algorithm = hybrid_algorithm
        self.recruiter_agent = recruiter_agent or RecruiterAgent(use_llm=False)
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
                'candidate_a_name': candidate_a.name,
                'candidate_b_name': candidate_b.name,
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
        mentions_skill_coverage = sum(1 for r in results if r['validation']['mentions_skill_coverage'])
        avg_alignment = sum(r['validation']['alignment_score'] for r in results) / total_tests
        
        return {
            'total_tests': total_tests,
            'mentions_missing_skills_rate': mentions_missing_skills / total_tests,
            'mentions_skill_coverage_rate': mentions_skill_coverage / total_tests,  # Replaced seniority
            'average_alignment_score': avg_alignment,
            'detailed_results': results
        }

