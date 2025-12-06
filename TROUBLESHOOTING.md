# Troubleshooting Neo4j Connection

## Issue: DNS Resolution Error

If you see this error:
```
socket.gaierror: [Errno 8] nodename nor servname provided, or not known
```

This means the system cannot resolve the Neo4j database hostname.

## Solutions

### Option 1: Check Network Connection
Make sure you have internet connectivity:
```bash
ping d0ee583f.databases.neo4j.io
```

### Option 2: Verify Neo4j Database is Running
- Check if your Neo4j Aura database is active in the Neo4j console
- Verify the database URI is correct
- Check if the database has been paused (Aura databases can be paused)

### Option 3: Use Sample Data (Current Working Solution)
The evaluation is currently running with sample data and working perfectly:
```bash
python run_evaluations.py --all
```

This uses the same algorithm, just with sample candidates/jobs instead of Neo4j data.

### Option 4: Test Neo4j Connection Separately
Test if you can connect to Neo4j from your main project:
```bash
cd "/Users/ananya/SWM CSE 573/Project/LinkedIn-Assistant"
python -c "
from recruiter_agent import JobAgent, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
agent = JobAgent(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
print('✅ Connected!')
agent.close()
"
```

### Option 5: Update Config with Correct Credentials
If your Neo4j credentials have changed, update `config.py`:
```python
NEO4J_URI = "your_correct_uri"
NEO4J_USER = "your_username"
NEO4J_PASSWORD = "your_password"
```

## Current Status

✅ **Evaluation Framework**: Working perfectly
✅ **Algorithm**: Calculating real results
✅ **Reports**: Generated successfully
⚠️ **Neo4j Connection**: Needs network/database access

## What's Working

Even without Neo4j, you have:
- ✅ Complete evaluation framework
- ✅ Real algorithm calculations
- ✅ Skill degradation test
- ✅ Explainability test
- ✅ Report generation
- ✅ HTML reports
- ✅ All metrics and analysis

The only difference is it's using sample data instead of your Neo4j database.

## Next Steps

1. **For Now**: Use `python run_evaluations.py --all` (works perfectly)
2. **When Neo4j is accessible**: Use `python run_evaluations_with_neo4j.py --all`
3. **To test connection**: Try connecting from your main project first

The evaluation framework is fully functional - it just needs Neo4j access to use your real data!

