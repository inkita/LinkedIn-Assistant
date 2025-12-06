# Integration Guide for Evaluation Protocols

This guide explains how to integrate the evaluation protocols with your existing LinkedIn Assistant codebase.

## Prerequisites

1. **Hybrid Algorithm**: Your existing scoring algorithm that uses:
   - Jaccard similarity for skill matching
   - Guttman scaling for seniority assessment

2. **Neo4j Database**: Connection to your Neo4j graph database (for skill degradation test)

3. **LLM Integration** (for explainability test): Choose one:
   - OpenAI API
   - Anthropic Claude API
   - Other LLM provider

## Step-by-Step Integration

### Step 1: Modify Your Hybrid Algorithm

Your `HybridAlgorithm` class needs to support detailed score breakdowns:

```python
# In your existing hybrid_algorithm.py

def calculate_match_score_detailed(self, job_posting, candidate):
    """
    Calculate match score with detailed breakdown.
    Returns a dictionary with:
    - total: Overall match score
    - jaccard_similarity: Jaccard score (0-1)
    - guttman_scaling: Guttman score (0-1)
    - missing_skills: List of required skills candidate lacks
    - common_skills: List of skills candidate has
    - seniority_level: "Senior", "Mid-level", or "Junior"
    - experience_years: Years of experience
    """
    # Your existing Jaccard calculation
    jaccard_score, missing_skills, common_skills = self._calculate_jaccard_detailed(
        job_posting.required_skills, candidate.skills
    )
    
    # Your existing Guttman scaling
    guttman_score, seniority = self._calculate_guttman_detailed(job_posting, candidate)
    
    # Combine scores (adjust weights as needed)
    total_score = (jaccard_score * 0.6) + (guttman_score * 0.4)
    
    return {
        'total': total_score,
        'jaccard_similarity': jaccard_score,
        'guttman_scaling': guttman_score,
        'missing_skills': missing_skills,
        'common_skills': common_skills,
        'seniority_level': seniority,
        'experience_years': candidate.years_experience
    }
```

### Step 2: Integrate Neo4j for Skill Degradation

If you're using Neo4j, modify the `SkillDegradationEngine` to work with your graph:

```python
from neo4j import GraphDatabase

class SkillDegradationEngine:
    def __init__(self, neo4j_uri, neo4j_user, neo4j_password):
        self.driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    
    def remove_skill_node(self, candidate_id, skill_name):
        """Remove a skill relationship from Neo4j"""
        with self.driver.session() as session:
            query = """
            MATCH (c:Candidate {id: $candidate_id})-[r:HAS_SKILL]->(s:Skill {name: $skill_name})
            DELETE r
            RETURN c
            """
            session.run(query, candidate_id=candidate_id, skill_name=skill_name)
    
    def restore_skill_node(self, candidate_id, skill_name, proficiency=None):
        """Restore a skill relationship (for test cleanup)"""
        with self.driver.session() as session:
            query = """
            MATCH (c:Candidate {id: $candidate_id}), (s:Skill {name: $skill_name})
            MERGE (c)-[r:HAS_SKILL]->(s)
            """
            if proficiency:
                query += " SET r.proficiency = $proficiency"
            query += " RETURN r"
            session.run(query, candidate_id=candidate_id, skill_name=skill_name, proficiency=proficiency)
```

**Important**: Use transactions and consider using a test database or creating snapshots before running degradation tests.

### Step 3: Integrate LLM for Recruiter Agent

Choose your LLM provider and integrate:

#### Option A: OpenAI

```python
from openai import OpenAI

class RecruiterAgent:
    def __init__(self, api_key):
        self.client = OpenAI(api_key=api_key)
    
    def generate_explanation(self, job_posting, candidate_a, candidate_b, score_a, score_b):
        prompt = self._build_prompt(job_posting, candidate_a, candidate_b, score_a, score_b)
        
        response = self.client.chat.completions.create(
            model="gpt-4",  # or "gpt-3.5-turbo"
            messages=[
                {"role": "system", "content": "You are a professional recruiter."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        
        return response.choices[0].message.content
```

#### Option B: Anthropic Claude

```python
import anthropic

class RecruiterAgent:
    def __init__(self, api_key):
        self.client = anthropic.Anthropic(api_key=api_key)
    
    def generate_explanation(self, job_posting, candidate_a, candidate_b, score_a, score_b):
        prompt = self._build_prompt(job_posting, candidate_a, candidate_b, score_a, score_b)
        
        message = self.client.messages.create(
            model="claude-3-opus-20240229",  # or "claude-3-sonnet-20240229"
            max_tokens=1024,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        return message.content[0].text
```

### Step 4: Connect to Your Data Models

Update the `Candidate` and `JobPosting` classes to match your existing data structures:

```python
# If you're using SQLAlchemy, Django ORM, or other ORM:
from your_models import Candidate as YourCandidate, JobPosting as YourJobPosting

# Create adapter functions
def adapt_candidate(your_candidate):
    """Convert your Candidate model to evaluation Candidate"""
    return Candidate(
        id=your_candidate.id,
        name=your_candidate.name,
        current_title=your_candidate.current_title,
        skills=[s.name for s in your_candidate.skills.all()],  # Adjust based on your model
        years_experience=your_candidate.years_experience,
        skill_proficiencies={s.name: s.proficiency for s in your_candidate.skills.all()}
    )
```

### Step 5: Run the Tests

Create a test runner script:

```python
# run_evaluations.py

from your_codebase import HybridAlgorithm, get_candidates, get_job_postings
from evaluation_example import SkillDegradationTest, ExplainabilityTest

# Initialize your algorithm
algorithm = HybridAlgorithm()  # Your existing instance

# Get test data
job_posting = get_job_postings()[0]  # Or load from database
candidates = get_candidates()  # Or load from database

# Run Skill Degradation Test
print("Running Skill Degradation Test...")
degradation_test = SkillDegradationTest(algorithm)
degradation_results = degradation_test.run_test(job_posting, candidates)
print(f"Original Score: {degradation_results['original_score']}")
print(f"Final Score: {degradation_results['final_score']}")
print(f"Critical Point: Step {degradation_results['critical_point']}")

# Run Explainability Test
print("\nRunning Explainability Test...")
explainability_test = ExplainabilityTest(algorithm)
explainability_results = explainability_test.run_test(job_posting, candidates)
print(f"Missing Skills Mention Rate: {explainability_results['mentions_missing_skills_rate']:.2%}")
print(f"Seniority Mention Rate: {explainability_results['mentions_seniority_rate']:.2%}")
print(f"Average Alignment: {explainability_results['average_alignment_score']:.2f}")
```

## Testing Strategy

### 1. Skill Degradation Test

**Test Cases to Consider:**
- Degrade title only (e.g., Lead → Junior)
- Remove one critical skill
- Remove multiple skills progressively
- Reduce experience years
- Combine multiple degradations

**Expected Results:**
- Score should decline with each degradation step
- Critical skills removal should cause larger score drops
- Title downgrade should affect Guttman scaling component

### 2. Explainability Test

**Test Cases:**
- Compare candidates with different missing skills
- Compare candidates with different seniority levels
- Compare candidates with similar scores but different reasons
- Edge cases: identical candidates, very different candidates

**Validation Criteria:**
- Explanation should mention at least 80% of missing skills
- Explanation should mention seniority when there's a significant difference
- Alignment score should be > 0.7 for good explanations

## Output and Reporting

### Generate Reports

```python
import json
from datetime import datetime

def save_results(degradation_results, explainability_results, output_dir="results"):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save degradation results
    with open(f"{output_dir}/degradation_{timestamp}.json", "w") as f:
        json.dump(degradation_results, f, indent=2)
    
    # Save explainability results
    with open(f"{output_dir}/explainability_{timestamp}.json", "w") as f:
        json.dump(explainability_results, f, indent=2)
    
    # Generate summary report
    summary = {
        'timestamp': timestamp,
        'degradation_test': {
            'original_score': degradation_results['original_score'],
            'final_score': degradation_results['final_score'],
            'score_drop': degradation_results['original_score'] - degradation_results['final_score'],
            'critical_point': degradation_results['critical_point']
        },
        'explainability_test': {
            'total_tests': explainability_results['total_tests'],
            'missing_skills_rate': explainability_results['mentions_missing_skills_rate'],
            'seniority_rate': explainability_results['mentions_seniority_rate'],
            'avg_alignment': explainability_results['average_alignment_score']
        }
    }
    
    with open(f"{output_dir}/summary_{timestamp}.json", "w") as f:
        json.dump(summary, f, indent=2)
```

## Troubleshooting

### Issue: Neo4j modifications affecting production data
**Solution**: Use a separate test database or create graph snapshots before tests

### Issue: LLM API rate limits
**Solution**: Add rate limiting and caching for explanations

### Issue: Explanations don't match scoring breakdown
**Solution**: 
- Improve prompt engineering
- Add more context to the prompt
- Fine-tune validation criteria

### Issue: Score decay is too slow/fast
**Solution**: Adjust degradation sequence or check if algorithm weights are correct

## Next Steps

1. **Run initial tests** with sample data
2. **Analyze results** and identify areas for improvement
3. **Iterate on prompts** for Recruiter Agent
4. **Refine degradation sequences** based on your domain
5. **Create visualizations** of score decay and explanation quality
6. **Document findings** for your professor

## Questions to Answer for Your Professor

After running the tests, you should be able to answer:

1. **Score Decay Rate**: How many degradation steps until score drops below 50%?
2. **Critical Degradations**: Which skill removals cause the largest score drops?
3. **Explainability**: What percentage of explanations mention missing skills?
4. **Explainability**: What percentage mention seniority differences?
5. **Alignment**: How well do explanations align with actual scoring breakdowns?

