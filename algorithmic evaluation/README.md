# LinkedIn Assistant - Evaluation Protocols

ASU CSE 573 - G7

This project implements evaluation protocols for the LinkedIn Assistant system, specifically:
1. **Skill Degradation Test** - Measures score decay rate as candidate skills are systematically degraded
2. **Explainability Test** - Validates that Recruiter Agent explanations align with the underlying scoring algorithm

## Installation

1. **Clone the repository**

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables** (optional, for LLM and Neo4j):
   ```bash
   # Copy .env.example to .env and fill in your credentials
   cp .env.example .env
   ```


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

## Results and Reporting

Results are saved to the `results/` directory by default:

- `degradation_YYYYMMDD_HHMMSS.json` - Skill degradation test results
- `explainability_YYYYMMDD_HHMMSS.json` - Explainability test results
- `summary_YYYYMMDD_HHMMSS.json` - Combined summary report