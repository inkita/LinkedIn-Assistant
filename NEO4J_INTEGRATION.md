# Neo4j Integration Guide

Your evaluation framework is now connected to your actual Neo4j database!

## Quick Start

### Option 1: Use config.py (Recommended)

The `config.py` file already has your Neo4j credentials. Just run:

```bash
python run_evaluations_with_neo4j.py --all
```

### Option 2: Command Line Arguments

```bash
python run_evaluations_with_neo4j.py --all \
    --neo4j-uri "neo4j+s://dc47a5a0.databases.neo4j.io" \
    --neo4j-user "neo4j" \
    --neo4j-password "YOUR_PASSWORD"
```

### Option 3: Environment Variables

```bash
export NEO4J_URI="neo4j+s://dc47a5a0.databases.neo4j.io"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="YOUR_PASSWORD"

python run_evaluations_with_neo4j.py --all
```

## What's Integrated

### ✅ Neo4jHybridAlgorithm
- Connects to your Neo4j database
- Uses actual Neo4j queries for Guttman scaling
- Queries skill hierarchies from your graph
- Calculates proficiency scores from Neo4j relationships

### ✅ Neo4jDataLoader
- Loads candidates from your Neo4j database
- Loads job postings from your Neo4j database
- Handles your existing schema (Candidate, Job, Skill nodes)

### ✅ Evaluation Tests
- Skill Degradation Test uses your actual algorithm
- Explainability Test uses your actual algorithm
- All calculations use real Neo4j data

## How It Works

### 1. Algorithm Integration

The `Neo4jHybridAlgorithm` class:
- Extends the base `HybridAlgorithm`
- Overrides `_guttman_scaling_detailed()` to query Neo4j
- Queries your actual skill hierarchies
- Uses proficiency levels from HAS_SKILL relationships

### 2. Data Loading

The `Neo4jDataLoader` class:
- Queries your Candidate nodes
- Queries your Job nodes  
- Queries REQUIRES_SKILL relationships
- Converts Neo4j data to evaluation framework models

### 3. Evaluation Execution

When you run `run_evaluations_with_neo4j.py`:
1. Connects to your Neo4j database
2. Loads actual candidates and jobs
3. Runs evaluation tests using your real algorithm
4. Generates reports with real results

## Neo4j Schema Expected

The integration expects this schema (matching your existing setup):

```
(:Candidate {candidate_id, name, title?, years_experience?})
  -[:HAS_SKILL {proficiency?}]-> (:Skill {name})

(:Job {job_id, title, experience_level?, description?})
  -[:REQUIRES_SKILL]-> (:Skill {name})
```

## Customization

### Adjust Algorithm Weights

Edit `config.py`:
```python
JACCARD_WEIGHT = 0.6  # Your preference
GUTTMAN_WEIGHT = 0.4  # Your preference
```

### Customize Neo4j Queries

Edit `src/integration.py`:
- Modify `_guttman_scaling_detailed()` for your Guttman calculation
- Modify `_calculate_proficiency_from_neo4j()` for your proficiency logic
- Modify data loading queries to match your exact schema

## Testing

### Test Connection
```bash
python -c "
from src.integration import Neo4jDataLoader
import config

loader = Neo4jDataLoader(config.NEO4J_URI, config.NEO4J_USER, config.NEO4J_PASSWORD)
candidates = loader.load_candidates(limit=5)
print(f'Loaded {len(candidates)} candidates')
loader.close()
"
```

### Run Full Evaluation
```bash
python run_evaluations_with_neo4j.py --all
```

## Troubleshooting

### Connection Issues
- Verify Neo4j URI format (bolt:// or neo4j+s://)
- Check credentials in config.py
- Ensure Neo4j database is accessible

### No Data Found
- Make sure you've uploaded candidates and jobs to Neo4j
- Check node labels match expected schema (Candidate, Job, Skill)
- Verify relationship types (HAS_SKILL, REQUIRES_SKILL)

### Schema Mismatches
- Update queries in `src/integration.py` to match your schema
- Check property names (candidate_id vs id, etc.)
- Verify relationship properties exist

## Next Steps

1. ✅ Run evaluation with your Neo4j data
2. ✅ Review results
3. ✅ Customize algorithm weights if needed
4. ✅ Adjust Neo4j queries for your exact schema
5. ✅ Generate reports for your professor

Your evaluation framework is now fully integrated with your actual LinkedIn Assistant system! 🎉

