# Quick Start Guide

Get up and running with the evaluation protocols in 5 minutes!

## 1. Install Dependencies

```bash
pip install -r requirements.txt
```

## 2. Run Tests with Sample Data

```bash
python run_evaluations.py --all
```

This will:
- Run both evaluation tests
- Use sample data (no database/API needed)
- Generate results in `results/` directory
- Print summary to console

## 3. Understand the Output

### Skill Degradation Test Output:
```
Original Score: 0.850
Final Score: 0.420
Score Drop: 0.430 (50.6%)
Critical Point: Step 3
```

### Explainability Test Output:
```
Total Tests: 6
Missing Skills Mention Rate: 83.3%
Seniority Mention Rate: 66.7%
Average Alignment Score: 0.817
```

## 4. Customize for Your Codebase

### Option A: Use Your Own Data

Edit `run_evaluations.py` and replace `create_sample_data()`:

```python
def create_sample_data():
    # Load from your database/API
    job = your_load_job_function(job_id)
    candidates = your_load_candidates_function()
    return job, candidates
```

### Option B: Adapt Your Algorithm

Edit `src/algorithm.py` and replace the mock implementations with your actual:
- Jaccard similarity calculation
- Guttman scaling calculation

### Option C: Add Real LLM

```python
from openai import OpenAI

client = OpenAI(api_key="your-key")
recruiter_agent = RecruiterAgent(use_llm=True, llm_client=client)
```

## 5. Run Your Custom Tests

```bash
python run_evaluations.py --all
```

## What's Next?

- Read `INTEGRATION_GUIDE.md` for detailed integration steps
- Check `EVALUATION_SUGGESTIONS.md` for architecture details
- Review `README.md` for full documentation

## Common Issues

**Import errors?**
- Make sure you're in the project root directory
- Check that `src/` directory exists

**No results?**
- Check that `results/` directory is created
- Verify candidates list is not empty

**Need help?**
- Check the detailed guides in the documentation files
- Review the example code in `evaluation_example.py`

