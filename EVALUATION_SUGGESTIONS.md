# Evaluation Protocol Implementation Suggestions

## Overview
This document outlines implementation suggestions for two evaluation protocols:
1. **Skill Degradation Test** - Measuring score decay rate
2. **Explainability Test** - Validating Recruiter Agent explanations

---

## 1. Skill Degradation Test

### Architecture Components Needed:

#### A. Perfect Match Candidate Selector
- **Function**: Identify candidates with highest initial match scores
- **Implementation**:
  ```python
  def find_perfect_match_candidates(job_posting, candidates, top_n=5):
      """
      Find candidates with highest match scores for a given job posting.
      Returns candidates sorted by match score (descending).
      """
      scores = []
      for candidate in candidates:
          score = hybrid_algorithm.calculate_match_score(job_posting, candidate)
          scores.append((candidate, score))
      return sorted(scores, key=lambda x: x[1], reverse=True)[:top_n]
  ```

#### B. Skill Degradation Engine
- **Function**: Systematically degrade candidate skills
- **Degradation Strategies**:
  1. **Title Downgrade**: Map senior titles to junior equivalents
     - Lead Architect → Junior Developer
     - Senior Engineer → Junior Developer
     - Principal → Mid-level
  2. **Skill Node Removal**: Remove prerequisite skills from Neo4j graph
  3. **Skill Level Reduction**: Downgrade skill proficiency levels
  4. **Experience Reduction**: Reduce years of experience

- **Implementation Structure**:
  ```python
  class SkillDegradationEngine:
      def __init__(self, neo4j_driver):
          self.driver = neo4j_driver
          self.title_downgrade_map = {
              "Lead Architect": "Junior Developer",
              "Senior Engineer": "Junior Developer",
              "Principal Engineer": "Mid-level Engineer",
              # ... more mappings
          }
      
      def degrade_title(self, candidate, target_title):
          """Downgrade candidate's job title"""
          candidate.current_title = target_title
          return candidate
      
      def remove_skill_node(self, candidate_id, skill_name):
          """Remove a skill node from Neo4j graph for this candidate"""
          query = """
          MATCH (c:Candidate {id: $candidate_id})-[r:HAS_SKILL]->(s:Skill {name: $skill_name})
          DELETE r
          RETURN c
          """
          # Execute query
      
      def degrade_skill_level(self, candidate_id, skill_name, new_level):
          """Reduce skill proficiency level"""
          query = """
          MATCH (c:Candidate {id: $candidate_id})-[r:HAS_SKILL]->(s:Skill {name: $skill_name})
          SET r.proficiency = $new_level
          RETURN r
          """
      
      def apply_degradation_sequence(self, candidate, degradation_steps):
          """
          Apply multiple degradations in sequence.
          degradation_steps: List of degradation operations
          """
          degraded_candidates = []
          current_candidate = candidate
          
          for step in degradation_steps:
              if step['type'] == 'title':
                  current_candidate = self.degrade_title(current_candidate, step['value'])
              elif step['type'] == 'remove_skill':
                  self.remove_skill_node(current_candidate.id, step['value'])
              elif step['type'] == 'reduce_skill_level':
                  self.degrade_skill_level(current_candidate.id, step['skill'], step['level'])
              
              degraded_candidates.append(copy.deepcopy(current_candidate))
          
          return degraded_candidates
  ```

#### C. Score Decay Rate Calculator
- **Function**: Measure how quickly scores decline
- **Metrics to Track**:
  - Absolute score drop per degradation step
  - Percentage score drop per degradation step
  - Rate of decay (score change per degradation operation)
  - Critical degradation point (when score drops below threshold)

- **Implementation**:
  ```python
  class ScoreDecayAnalyzer:
      def calculate_decay_rate(self, original_score, degraded_scores):
          """
          Calculate decay metrics:
          - Absolute decay: score[i] - score[i-1]
          - Percentage decay: (score[i] - score[i-1]) / score[i-1] * 100
          - Cumulative decay: (original_score - score[i]) / original_score * 100
          """
          decay_metrics = []
          
          for i, score in enumerate(degraded_scores):
              if i == 0:
                  absolute_decay = original_score - score
                  percentage_decay = (absolute_decay / original_score) * 100
              else:
                  absolute_decay = degraded_scores[i-1] - score
                  percentage_decay = (absolute_decay / degraded_scores[i-1]) * 100
              
              cumulative_decay = ((original_score - score) / original_score) * 100
              
              decay_metrics.append({
                  'step': i + 1,
                  'score': score,
                  'absolute_decay': absolute_decay,
                  'percentage_decay': percentage_decay,
                  'cumulative_decay': cumulative_decay
              })
          
          return decay_metrics
      
      def find_critical_point(self, decay_metrics, threshold=0.5):
          """Find when score drops below threshold (e.g., 50% of original)"""
          for metric in decay_metrics:
              if metric['cumulative_decay'] >= (threshold * 100):
                  return metric['step']
          return None
  ```

#### D. Test Orchestrator
- **Function**: Coordinate the entire degradation test
- **Implementation**:
  ```python
  class SkillDegradationTest:
      def __init__(self, hybrid_algorithm, degradation_engine, score_analyzer):
          self.algorithm = hybrid_algorithm
          self.degradation_engine = degradation_engine
          self.analyzer = score_analyzer
      
      def run_test(self, job_posting, candidates):
          """
          Main test execution:
          1. Find perfect match candidate
          2. Apply degradation sequence
          3. Measure score decay
          4. Generate report
          """
          # Step 1: Find perfect match
          perfect_matches = find_perfect_match_candidates(job_posting, candidates, top_n=1)
          candidate, original_score = perfect_matches[0]
          
          # Step 2: Define degradation sequence
          degradation_steps = [
              {'type': 'title', 'value': 'Junior Developer'},
              {'type': 'remove_skill', 'value': 'Python'},  # Core skill
              {'type': 'remove_skill', 'value': 'System Design'},
              {'type': 'reduce_skill_level', 'skill': 'Java', 'level': 'Beginner'},
              # ... more steps
          ]
          
          # Step 3: Apply degradations and measure scores
          degraded_candidates = self.degradation_engine.apply_degradation_sequence(
              candidate, degradation_steps
          )
          
          degraded_scores = []
          for degraded_candidate in degraded_candidates:
              score = self.algorithm.calculate_match_score(job_posting, degraded_candidate)
              degraded_scores.append(score)
          
          # Step 4: Analyze decay
          decay_metrics = self.analyzer.calculate_decay_rate(original_score, degraded_scores)
          critical_point = self.analyzer.find_critical_point(decay_metrics)
          
          # Step 5: Generate report
          return {
              'original_score': original_score,
              'degradation_steps': degradation_steps,
              'decay_metrics': decay_metrics,
              'critical_point': critical_point,
              'final_score': degraded_scores[-1]
          }
  ```

---

## 2. Explainability Test

### Architecture Components Needed:

#### A. Scoring Algorithm Breakdown Extractor
- **Function**: Extract detailed breakdown from Hybrid Algorithm
- **Components to Extract**:
  - Jaccard similarity score and missing skills
  - Guttman scaling score and seniority differences
  - Other scoring components (if any)

- **Implementation**:
  ```python
  class ScoringBreakdownExtractor:
      def extract_breakdown(self, job_posting, candidate_a, candidate_b):
          """
          Extract detailed scoring breakdown for comparison.
          Returns structured breakdown including:
          - Jaccard similarity components
          - Guttman scaling components
          - Missing skills
          - Seniority differences
          """
          # Calculate scores with detailed breakdown
          score_a = self.algorithm.calculate_match_score_detailed(job_posting, candidate_a)
          score_b = self.algorithm.calculate_match_score_detailed(job_posting, candidate_b)
          
          # Extract Jaccard components
          jaccard_a = self._extract_jaccard_components(score_a)
          jaccard_b = self._extract_jaccard_components(score_b)
          
          # Extract Guttman components
          guttman_a = self._extract_guttman_components(score_a)
          guttman_b = self._extract_guttman_components(score_b)
          
          # Identify differences
          missing_skills_a = self._get_missing_skills(job_posting, candidate_a)
          missing_skills_b = self._get_missing_skills(job_posting, candidate_b)
          
          seniority_diff_a = self._get_seniority_difference(job_posting, candidate_a)
          seniority_diff_b = self._get_seniority_difference(job_posting, candidate_b)
          
          return {
              'candidate_a': {
                  'score': score_a['total'],
                  'jaccard': jaccard_a,
                  'guttman': guttman_a,
                  'missing_skills': missing_skills_a,
                  'seniority_diff': seniority_diff_a
              },
              'candidate_b': {
                  'score': score_b['total'],
                  'jaccard': jaccard_b,
                  'guttman': guttman_b,
                  'missing_skills': missing_skills_b,
                  'seniority_diff': seniority_diff_b
              }
          }
      
      def _extract_jaccard_components(self, score_breakdown):
          """Extract Jaccard similarity score and missing skills"""
          return {
              'score': score_breakdown['jaccard_similarity'],
              'missing_skills': score_breakdown['missing_skills'],
              'common_skills': score_breakdown['common_skills']
          }
      
      def _extract_guttman_components(self, score_breakdown):
          """Extract Guttman scaling score and seniority information"""
          return {
              'score': score_breakdown['guttman_scaling'],
              'seniority_level': score_breakdown['seniority_level'],
              'experience_years': score_breakdown['experience_years']
          }
  ```

#### B. Recruiter Agent Explanation Generator
- **Function**: Generate natural language explanations
- **Implementation**:
  ```python
  class RecruiterAgent:
      def __init__(self, llm_client):  # Could be OpenAI, Anthropic, etc.
          self.llm = llm_client
      
      def generate_explanation(self, job_posting, candidate_a, candidate_b, score_a, score_b):
          """
          Prompt the Recruiter Agent to explain ranking.
          Returns natural language explanation.
          """
          prompt = f"""
          You are a professional recruiter evaluating candidates for a job posting.
          
          Job Posting:
          Title: {job_posting.title}
          Required Skills: {', '.join(job_posting.required_skills)}
          Experience Level: {job_posting.experience_level}
          
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
          
          response = self.llm.generate(prompt)
          return response
  ```

#### C. Explanation Validator
- **Function**: Compare Recruiter Agent explanation with scoring breakdown
- **Validation Checks**:
  1. Mentions missing skills identified by Jaccard similarity
  2. References seniority differences from Guttman scaling
  3. Alignment with actual score differences

- **Implementation**:
  ```python
  class ExplanationValidator:
      def __init__(self, nlp_processor):  # Could use spaCy, NLTK, etc.
          self.nlp = nlp_processor
      
      def validate_explanation(self, explanation, scoring_breakdown):
          """
          Validate that explanation mentions:
          1. Missing skills from Jaccard similarity
          2. Seniority differences from Guttman scaling
          """
          validation_results = {
              'mentions_missing_skills': False,
              'mentions_seniority': False,
              'missing_skills_coverage': [],
              'seniority_mentions': [],
              'alignment_score': 0.0
          }
          
          # Extract missing skills from breakdown
          missing_skills_a = scoring_breakdown['candidate_a']['missing_skills']
          missing_skills_b = scoring_breakdown['candidate_b']['missing_skills']
          
          # Check if explanation mentions missing skills
          explanation_lower = explanation.lower()
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
          
          # Calculate alignment score (0-1)
          alignment_score = self._calculate_alignment(explanation, scoring_breakdown)
          validation_results['alignment_score'] = alignment_score
          
          return validation_results
      
      def _calculate_alignment(self, explanation, scoring_breakdown):
          """
          Calculate how well explanation aligns with scoring breakdown.
          Returns score between 0 and 1.
          """
          # Extract key factors from breakdown
          key_factors = []
          
          # Missing skills factor
          if scoring_breakdown['candidate_a']['missing_skills']:
              key_factors.append('missing_skills_a')
          if scoring_breakdown['candidate_b']['missing_skills']:
              key_factors.append('missing_skills_b')
          
          # Seniority factor
          if abs(scoring_breakdown['candidate_a']['seniority_diff'] - 
                 scoring_breakdown['candidate_b']['seniority_diff']) > 0.1:
              key_factors.append('seniority_difference')
          
          # Check if explanation mentions these factors
          mentioned_factors = 0
          explanation_lower = explanation.lower()
          
          if 'missing_skills_a' in key_factors or 'missing_skills_b' in key_factors:
              # Check for skill mentions
              if any(keyword in explanation_lower for keyword in ['skill', 'missing', 'lack', 'doesn\'t have']):
                  mentioned_factors += 1
          
          if 'seniority_difference' in key_factors:
              if any(keyword in explanation_lower for keyword in ['senior', 'junior', 'experience', 'level']):
                  mentioned_factors += 1
          
          if len(key_factors) == 0:
              return 1.0  # No factors to mention
          
          return mentioned_factors / len(key_factors)
  ```

#### D. Explainability Test Orchestrator
- **Function**: Run explainability test for all candidate pairs
- **Implementation**:
  ```python
  class ExplainabilityTest:
      def __init__(self, recruiter_agent, breakdown_extractor, validator):
          self.recruiter_agent = recruiter_agent
          self.breakdown_extractor = breakdown_extractor
          self.validator = validator
      
      def run_test(self, job_posting, candidates):
          """
          Run explainability test for all candidate pairs.
          For each pair where A is ranked higher than B:
          1. Generate Recruiter Agent explanation
          2. Extract scoring breakdown
          3. Validate explanation
          4. Generate report
          """
          results = []
          
          # Get all candidate pairs (A ranked higher than B)
          candidate_pairs = self._get_ranked_pairs(job_posting, candidates)
          
          for candidate_a, candidate_b in candidate_pairs:
              # Calculate scores
              score_a = self.breakdown_extractor.algorithm.calculate_match_score(
                  job_posting, candidate_a
              )
              score_b = self.breakdown_extractor.algorithm.calculate_match_score(
                  job_posting, candidate_b
              )
              
              # Generate explanation
              explanation = self.recruiter_agent.generate_explanation(
                  job_posting, candidate_a, candidate_b, score_a, score_b
              )
              
              # Extract breakdown
              breakdown = self.breakdown_extractor.extract_breakdown(
                  job_posting, candidate_a, candidate_b
              )
              
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
      
      def _get_ranked_pairs(self, job_posting, candidates):
          """Get all pairs where first candidate ranks higher"""
          scores = []
          for candidate in candidates:
              score = self.breakdown_extractor.algorithm.calculate_match_score(
                  job_posting, candidate
              )
              scores.append((candidate, score))
          
          # Sort by score descending
          scores.sort(key=lambda x: x[1], reverse=True)
          
          # Generate pairs
          pairs = []
          for i in range(len(scores)):
              for j in range(i + 1, len(scores)):
                  pairs.append((scores[i][0], scores[j][0]))
          
          return pairs
      
      def _generate_report(self, results):
          """Generate evaluation report"""
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
  ```

---

## Implementation Recommendations

### 1. **Modify Hybrid Algorithm to Return Detailed Breakdown**
   - Ensure `calculate_match_score()` can return detailed components
   - Separate Jaccard similarity and Guttman scaling scores
   - Track missing skills and seniority metrics

### 2. **Neo4j Integration for Skill Degradation**
   - Create functions to safely modify graph (use transactions)
   - Implement rollback mechanism to restore original state after tests
   - Consider using test database or snapshots

### 3. **Test Data Management**
   - Create test datasets with known "perfect match" candidates
   - Define standard degradation sequences
   - Store test results for comparison

### 4. **Reporting and Visualization**
   - Generate charts for score decay over degradation steps
   - Create tables comparing explanations vs. scoring breakdowns
   - Export results to CSV/JSON for analysis

### 5. **Integration Points**
   - Ensure Recruiter Agent can access candidate and job data
   - Connect to LLM API (OpenAI, Anthropic, etc.)
   - Set up NLP processing for explanation validation

---

## File Structure Suggestion

```
evaluation/
├── __init__.py
├── skill_degradation/
│   ├── __init__.py
│   ├── degradation_engine.py
│   ├── score_decay_analyzer.py
│   └── degradation_test.py
├── explainability/
│   ├── __init__.py
│   ├── recruiter_agent.py
│   ├── breakdown_extractor.py
│   ├── explanation_validator.py
│   └── explainability_test.py
├── utils/
│   ├── __init__.py
│   ├── test_data_generator.py
│   └── report_generator.py
└── main.py  # Orchestrator to run both tests
```

---

## Next Steps

1. **Review existing Hybrid Algorithm implementation** - Understand current scoring structure
2. **Set up Neo4j connection** - Ensure you can modify graph safely
3. **Integrate LLM for Recruiter Agent** - Choose and configure LLM provider
4. **Create test datasets** - Generate or import test candidates and job postings
5. **Implement components incrementally** - Start with degradation test, then explainability
6. **Run tests and analyze results** - Generate reports and validate findings

