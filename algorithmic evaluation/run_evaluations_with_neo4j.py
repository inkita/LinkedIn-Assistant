#!/usr/bin/env python3
"""
Run evaluation protocols using your actual Neo4j database.
"""

import argparse
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.integration import Neo4jHybridAlgorithm, Neo4jDataLoader
from src.evaluation import SkillDegradationTest, ExplainabilityTest
from src.utils import ReportGenerator

# Try to import config, fall back to defaults
try:
    import config
    DEFAULT_NEO4J_URI = config.NEO4J_URI
    DEFAULT_NEO4J_USER = config.NEO4J_USER
    DEFAULT_NEO4J_PASSWORD = config.NEO4J_PASSWORD
except ImportError:
    DEFAULT_NEO4J_URI = None
    DEFAULT_NEO4J_USER = None
    DEFAULT_NEO4J_PASSWORD = None


def main():
    parser = argparse.ArgumentParser(description='Run evaluation protocols with Neo4j')
    parser.add_argument('--degradation', action='store_true', help='Run skill degradation test')
    parser.add_argument('--explainability', action='store_true', help='Run explainability test')
    parser.add_argument('--all', action='store_true', help='Run all tests')
    parser.add_argument('--output-dir', default='results', help='Output directory for results')
    
    # Neo4j connection parameters
    parser.add_argument('--neo4j-uri', help='Neo4j URI (or set NEO4J_URI env var)')
    parser.add_argument('--neo4j-user', help='Neo4j username (or set NEO4J_USER env var)')
    parser.add_argument('--neo4j-password', help='Neo4j password (or set NEO4J_PASSWORD env var)')
    
    # Data selection
    parser.add_argument('--job-id', help='Specific job ID to test (optional)')
    parser.add_argument('--candidate-limit', type=int, help='Limit number of candidates to load')
    parser.add_argument('--job-limit', type=int, help='Limit number of jobs to load')
    
    args = parser.parse_args()
    
    # If no specific test is selected, run all
    if not args.degradation and not args.explainability:
        args.all = True
    
    # Get Neo4j credentials
    import os
    neo4j_uri = args.neo4j_uri or os.getenv('NEO4J_URI') or DEFAULT_NEO4J_URI
    neo4j_user = args.neo4j_user or os.getenv('NEO4J_USER') or DEFAULT_NEO4J_USER
    neo4j_password = args.neo4j_password or os.getenv('NEO4J_PASSWORD') or DEFAULT_NEO4J_PASSWORD
    
    if not all([neo4j_uri, neo4j_user, neo4j_password]):
        print("❌ Error: Neo4j credentials required!")
        print("   Options:")
        print("   1. Create config.py with NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD")
        print("   2. Use --neo4j-uri, --neo4j-user, --neo4j-password arguments")
        print("   3. Set environment variables: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD")
        sys.exit(1)
    
    # Initialize components
    print("🔌 Connecting to Neo4j...")
    algorithm = Neo4jHybridAlgorithm(neo4j_uri, neo4j_user, neo4j_password)
    data_loader = Neo4jDataLoader(neo4j_uri, neo4j_user, neo4j_password)
    reporter = ReportGenerator(output_dir=args.output_dir)
    
    try:
        # Load data from Neo4j
        print("\n📥 Loading candidates from Neo4j...")
        candidates = data_loader.load_candidates(limit=args.candidate_limit)
        print(f"   Loaded {len(candidates)} candidates")
        
        if not candidates:
            print("❌ No candidates found in Neo4j. Please upload candidates first.")
            sys.exit(1)
        
        # Load job posting(s)
        if args.job_id:
            print(f"\n📥 Loading job {args.job_id} from Neo4j...")
            job = data_loader.load_job_by_id(args.job_id)
            if not job:
                print(f"❌ Job {args.job_id} not found in Neo4j")
                sys.exit(1)
            jobs = [job]
        else:
            print("\n📥 Loading job postings from Neo4j...")
            jobs = data_loader.load_job_postings(limit=args.job_limit or 1)
            print(f"   Loaded {len(jobs)} job postings")
        
        if not jobs:
            print("❌ No job postings found in Neo4j. Please upload jobs first.")
            sys.exit(1)
        
        # Use first job for evaluation
        job = jobs[0]
        # If required skills are missing, infer from candidate skills (top 5 frequent)
        if not job.required_skills:
            from collections import Counter
            skill_counter = Counter()
            for cand in candidates:
                skill_counter.update([s for s in cand.skills if s])
            inferred = [s for s, _ in skill_counter.most_common(5)]
            job.required_skills = inferred
            print(f"   Required skills were empty; inferred from candidates: {', '.join(inferred)}")
        print(f"\n📋 Using job: {job.title} (ID: {job.id})")
        print(f"   Required skills: {', '.join(job.required_skills[:5])}{'...' if len(job.required_skills) > 5 else ''}")
        
        degradation_results = None
        explainability_results = None
        
        # Run tests
        if args.all or args.degradation:
            print("\n" + "=" * 70)
            print("Running Skill Degradation Test...")
            print("=" * 70)
            
            degradation_test = SkillDegradationTest(algorithm)
            degradation_results = degradation_test.run_test(job, candidates)
            
            if 'error' not in degradation_results:
                print(f"\n✅ Degradation Test Complete!")
                print(f"   Original Score: {degradation_results['original_score']:.3f}")
                print(f"   Final Score: {degradation_results['final_score']:.3f}")
                print(f"   Score Drop: {degradation_results['total_degradation']:.3f} ({degradation_results['total_degradation_percentage']:.1f}%)")
                
                filepath = reporter.save_degradation_results(degradation_results)
                print(f"   Results saved to: {filepath}")
            else:
                print(f"❌ Error: {degradation_results['error']}")
        
        if args.all or args.explainability:
            print("\n" + "=" * 70)
            print("Running Explainability Test...")
            print("=" * 70)
            
            explainability_test = ExplainabilityTest(algorithm)
            explainability_results = explainability_test.run_test(job, candidates)
            
            if 'error' not in explainability_results:
                print(f"\n✅ Explainability Test Complete!")
                print(f"   Total Tests: {explainability_results['total_tests']}")
                print(f"   Missing Skills Mention Rate: {explainability_results['mentions_missing_skills_rate']:.1%}")
                print(f"   Skill Coverage Mention Rate: {explainability_results.get('mentions_skill_coverage_rate', 0):.1%}")
                print(f"   Average Alignment Score: {explainability_results['average_alignment_score']:.3f}")
                
                filepath = reporter.save_explainability_results(explainability_results)
                print(f"   Results saved to: {filepath}")
            else:
                print(f"❌ Error: {explainability_results['error']}")
        
        # Generate summary
        if degradation_results and explainability_results and 'error' not in degradation_results and 'error' not in explainability_results:
            summary_path = reporter.generate_summary_report(degradation_results, explainability_results)
            reporter.print_summary(degradation_results, explainability_results)
            print(f"\n📊 Summary report saved to: {summary_path}")
        
        print("\n✅ Evaluation complete!")
        
    finally:
        # Clean up connections
        algorithm.close()
        data_loader.close()


if __name__ == "__main__":
    main()

