# LinkedIn Assistant - Evaluation Protocols

ASU CSE 573 - G7

This project implements evaluation protocols for the LinkedIn Assistant system, specifically:
1. **Skill Degradation Test** - Measures score decay rate as candidate skills are systematically degraded
2. **Explainability Test** - Validates that Recruiter Agent explanations align with the underlying scoring algorithm

## Project Structure

```
LinkedIn-Assistant/
├── src/
│   ├── __init__.py
│   ├── models.py              # Data models (Candidate, JobPosting, ScoreBreakdown)
│   ├── algorithm.py           # Hybrid Algorithm implementation
│   ├── evaluation/
│   │   ├── __init__.py
│   │   ├── skill_degradation.py    # Skill degradation test components
│   │   └── explainability.py       # Explainability test components
│   └── utils/
│       ├── __init__.py
│       ├── neo4j_utils.py     # Neo4j integration for skill degradation
│       └── reporting.py       # Report generation utilities
├── run_evaluations.py         # Main script to run evaluations
├── evaluation_example.py      # Example implementation with mock data
├── requirements.txt           # Python dependencies
├── EVALUATION_SUGGESTIONS.md  # Detailed architecture suggestions
├── INTEGRATION_GUIDE.md       # Integration guide
└── EVALUATION_SUMMARY.md      # Quick reference summary
```

## Installation

1. **Clone the repository** (if applicable)

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables** (optional, for LLM and Neo4j):
   ```bash
   # Copy .env.example to .env and fill in your credentials
   cp .env.example .env
   ```

## Quick Start

### Running the Evaluation Tests

Run all tests with sample data:
```bash
python run_evaluations.py --all
```

Run specific tests:
```bash
# Skill degradation test only
python run_evaluations.py --degradation

# Explainability test only
python run_evaluations.py --explainability
```

### Using the Code

```python
from src.algorithm import HybridAlgorithm
from src.models import Candidate, JobPosting
from src.evaluation import SkillDegradationTest, ExplainabilityTest

# Initialize algorithm
algorithm = HybridAlgorithm()

# Create job posting and candidates
job = JobPosting(
    id="job1",
    title="Senior Software Engineer",
    required_skills=["Python", "Java", "System Design"],
    experience_level="Senior"
)

candidates = [
    Candidate(
        id="cand1",
        name="Alice",
        current_title="Lead Architect",
        skills=["Python", "Java", "System Design"],
        years_experience=8,
        skill_proficiencies={"Python": "Expert"}
    ),
    # ... more candidates
]

# Run Skill Degradation Test
degradation_test = SkillDegradationTest(algorithm)
degradation_results = degradation_test.run_test(job, candidates)

# Run Explainability Test
explainability_test = ExplainabilityTest(algorithm)
explainability_results = explainability_test.run_test(job, candidates)
```

## Evaluation Protocols

### 1. Skill Degradation Test

**Purpose**: Measure how quickly candidate match scores decline as their skills are systematically degraded.

**What it does**:
- Selects a "perfect match" candidate (highest initial score)
- Applies degradation sequence:
  - Title downgrade (e.g., Lead Architect → Junior Developer)
  - Skill removal (removes required skills from Neo4j graph)
  - Experience reduction
  - Skill proficiency reduction
- Measures score decay rate at each step
- Identifies critical point (when score drops below 50% of original)

**Output Metrics**:
- Original score vs. final score
- Score decay per degradation step
- Critical degradation point
- Total degradation percentage

**Example Output**:
```json
{
  "original_score": 0.85,
  "final_score": 0.42,
  "critical_point": 3,
  "total_degradation_percentage": 50.6
}
```

### 2. Explainability Test

**Purpose**: Validate that Recruiter Agent explanations mention:
- Missing skills identified by Jaccard similarity component
- Seniority differences derived from Guttman scaling score

**What it does**:
- For every candidate pair (A ranked higher than B):
  - Generates Recruiter Agent explanation
  - Extracts detailed scoring breakdown
  - Validates explanation against breakdown
- Measures:
  - Percentage of explanations mentioning missing skills
  - Percentage mentioning seniority differences
  - Alignment score between explanation and scoring breakdown

**Output Metrics**:
- Missing skills mention rate
- Seniority mention rate
- Average alignment score
- Detailed results for each candidate pair

**Example Output**:
```json
{
  "total_tests": 15,
  "mentions_missing_skills_rate": 0.87,
  "mentions_seniority_rate": 0.73,
  "average_alignment_score": 0.82
}
```

## Integration with Your Codebase

### Step 1: Adapt the Hybrid Algorithm

Modify `src/algorithm.py` to match your actual algorithm implementation:

```python
class HybridAlgorithm:
    def calculate_match_score_detailed(self, job: JobPosting, candidate: Candidate) -> ScoreBreakdown:
        # Your Jaccard similarity calculation
        jaccard_score, missing_skills, common_skills = self._your_jaccard_method(...)
        
        # Your Guttman scaling calculation
        guttman_score, seniority_level = self._your_guttman_method(...)
        
        # Combine scores
        total_score = (jaccard_score * self.jaccard_weight) + (guttman_score * self.guttman_weight)
        
        return ScoreBreakdown(...)
```

### Step 2: Connect to Your Data

Replace `create_sample_data()` in `run_evaluations.py` with your data loading:

```python
def load_your_data():
    # Load from database, API, etc.
    job = load_job_posting(job_id)
    candidates = load_candidates()
    return job, candidates
```

### Step 3: Set Up LLM (Optional)

For explainability test with real LLM:

```python
from openai import OpenAI

client = OpenAI(api_key="your-key")
recruiter_agent = RecruiterAgent(use_llm=True, llm_client=client, model="gpt-4")
explainability_test = ExplainabilityTest(algorithm, recruiter_agent=recruiter_agent)
```

### Step 4: Set Up Neo4j (Optional)

For skill degradation with Neo4j graph:

```python
from src.utils import Neo4jSkillDegradationEngine

neo4j_engine = Neo4jSkillDegradationEngine(
    uri="bolt://localhost:7687",
    user="neo4j",
    password="password"
)

# Use in degradation test
# (Modify SkillDegradationEngine to use Neo4j operations)
```

## Configuration

### Environment Variables

Create a `.env` file with:

```bash
# Neo4j (optional)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password

# LLM (optional)
OPENAI_API_KEY=your_key
LLM_PROVIDER=openai
LLM_MODEL=gpt-4
```

## Results and Reporting

Results are saved to the `results/` directory by default:

- `degradation_YYYYMMDD_HHMMSS.json` - Skill degradation test results
- `explainability_YYYYMMDD_HHMMSS.json` - Explainability test results
- `summary_YYYYMMDD_HHMMSS.json` - Combined summary report

Use `ReportGenerator` to customize reporting:

```python
from src.utils import ReportGenerator

reporter = ReportGenerator(output_dir="custom_results")
reporter.save_degradation_results(results)
reporter.print_summary(degradation_results, explainability_results)
```

## Key Metrics for Your Professor

After running the tests, you can report:

1. **Score Decay Rate**: How many degradation steps until score drops below 50%?
2. **Critical Degradations**: Which skill removals cause the largest score drops?
3. **Explainability Coverage**: What percentage of explanations mention missing skills?
4. **Seniority Coverage**: What percentage mention seniority differences?
5. **Alignment Quality**: How well do explanations align with actual scoring breakdowns?

## Documentation

- **EVALUATION_SUGGESTIONS.md** - Detailed architectural suggestions
- **INTEGRATION_GUIDE.md** - Step-by-step integration guide
- **EVALUATION_SUMMARY.md** - Quick reference summary

## Testing

Run the example implementation:
```bash
python evaluation_example.py
```

This will run both tests with mock data and display results.

## Troubleshooting

### Issue: No candidates found
- Ensure candidates list is not empty
- Check that candidates have required fields populated

### Issue: LLM API errors
- Verify API key is set correctly
- Check API rate limits
- Use `use_llm=False` for mock explanations

### Issue: Neo4j connection errors
- Verify Neo4j is running
- Check connection credentials
- Ensure graph schema matches expected structure

## Next Steps

1. ✅ Review the code structure
2. ✅ Adapt Hybrid Algorithm to your implementation
3. ✅ Connect to your data sources
4. ✅ Run tests with your data
5. ✅ Analyze results and generate reports
6. ✅ Document findings for your professor

## License

ASU CSE 573 - G7
