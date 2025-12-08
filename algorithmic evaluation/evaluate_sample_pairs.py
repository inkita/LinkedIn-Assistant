#!/usr/bin/env python3
"""
Evaluate 5 sample candidate pairs and display results in a table format.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.integration import Neo4jHybridAlgorithm, Neo4jDataLoader
from src.evaluation import ExplainabilityTest
from src.utils import ReportGenerator
import config


def create_results_table(results):
    """Create a formatted table of results"""
    print("\n" + "=" * 120)
    print("EXPLAINABILITY TEST RESULTS - 5 SAMPLE PAIRS")
    print("=" * 120)
    print()
    
    # Table header
    header = f"{'Pair':<6} {'Candidate A':<25} {'Score A':<10} {'Candidate B':<25} {'Score B':<10} {'Missing Skills':<15} {'Skill Coverage':<15} {'Alignment':<10}"
    print(header)
    print("-" * 120)
    
    # Get first 5 pairs
    sample_pairs = results['detailed_results'][:5]
    
    for i, result in enumerate(sample_pairs, 1):
        candidate_a = result['candidate_a_name']
        candidate_b = result['candidate_b_name']
        score_a = result['score_a']
        score_b = result['score_b']
        
        validation = result['validation']
        mentions_missing = "✅ Yes" if validation['mentions_missing_skills'] else "❌ No"
        mentions_coverage = "✅ Yes" if validation.get('mentions_skill_coverage', False) else "❌ No"
        alignment = f"{validation['alignment_score']:.3f}"
        
        # Truncate long names
        name_a = candidate_a[:23] + ".." if len(candidate_a) > 25 else candidate_a
        name_b = candidate_b[:23] + ".." if len(candidate_b) > 25 else candidate_b
        
        row = f"{i:<6} {name_a:<25} {score_a:<10.3f} {name_b:<25} {score_b:<10.3f} {mentions_missing:<15} {mentions_coverage:<15} {alignment:<10}"
        print(row)
    
    print("-" * 120)
    print()
    
    # Summary statistics
    print("SUMMARY STATISTICS:")
    print(f"  Total Pairs Tested: {len(sample_pairs)}")
    print(f"  Missing Skills Mention Rate: {results['mentions_missing_skills_rate']:.1%}")
    print(f"  Skill Coverage Mention Rate: {results.get('mentions_skill_coverage_rate', 0):.1%}")
    print(f"  Average Alignment Score: {results['average_alignment_score']:.3f}")
    print()
    
    # Detailed breakdown for each pair
    print("=" * 120)
    print("DETAILED BREAKDOWN")
    print("=" * 120)
    print()
    
    for i, result in enumerate(sample_pairs, 1):
        print(f"PAIR {i}: {result['candidate_a_name']} vs {result['candidate_b_name']}")
        print("-" * 120)
        print(f"  Scores: {result['candidate_a_name']} = {result['score_a']:.3f}, {result['candidate_b_name']} = {result['score_b']:.3f}")
        print(f"  Score Difference: {abs(result['score_a'] - result['score_b']):.3f}")
        print()
        
        breakdown = result['breakdown']
        print(f"  {result['candidate_a_name']}:")
        print(f"    - Jaccard Similarity: {breakdown['candidate_a']['jaccard']:.3f}")
        print(f"    - Guttman Scaling: {breakdown['candidate_a']['guttman']:.3f}")
        print(f"    - Common Skills: {len(breakdown['candidate_a'].get('common_skills', []))} skills")
        print(f"    - Missing Skills: {', '.join(breakdown['candidate_a']['missing_skills']) if breakdown['candidate_a']['missing_skills'] else 'None'}")
        print()
        
        print(f"  {result['candidate_b_name']}:")
        print(f"    - Jaccard Similarity: {breakdown['candidate_b']['jaccard']:.3f}")
        print(f"    - Guttman Scaling: {breakdown['candidate_b']['guttman']:.3f}")
        print(f"    - Common Skills: {len(breakdown['candidate_b'].get('common_skills', []))} skills")
        print(f"    - Missing Skills: {', '.join(breakdown['candidate_b']['missing_skills']) if breakdown['candidate_b']['missing_skills'] else 'None'}")
        print()
        
        print(f"  Explanation:")
        explanation = result['explanation']
        # Wrap long explanations
        words = explanation.split()
        lines = []
        current_line = "    "
        for word in words:
            if len(current_line + word) > 110:
                lines.append(current_line)
                current_line = "    " + word + " "
            else:
                current_line += word + " "
        lines.append(current_line)
        for line in lines:
            print(line)
        print()
        
        validation = result['validation']
        print(f"  Validation:")
        print(f"    ✓ Mentions Missing Skills: {mentions_missing}")
        if validation['missing_skills_coverage']:
            print(f"      Covered Skills: {', '.join(validation['missing_skills_coverage'])}")
        print(f"    ✓ Mentions Skill Coverage: {mentions_coverage}")
        if validation.get('skill_coverage_mentions'):
            print(f"      Keywords: {', '.join(set(validation['skill_coverage_mentions']))}")
        print(f"    ✓ Alignment Score: {alignment}")
        print()
        print()


def main():
    """Main function"""
    # Get Neo4j credentials
    neo4j_uri = config.NEO4J_URI
    neo4j_user = config.NEO4J_USER
    neo4j_password = config.NEO4J_PASSWORD
    
    print("🔌 Connecting to Neo4j...")
    algorithm = Neo4jHybridAlgorithm(neo4j_uri, neo4j_user, neo4j_password)
    data_loader = Neo4jDataLoader(neo4j_uri, neo4j_user, neo4j_password)
    
    try:
        # Load data
        print("\n📥 Loading candidates from Neo4j...")
        candidates = data_loader.load_candidates(limit=10)  # Load 10 to get good pairs
        print(f"   Loaded {len(candidates)} candidates")
        
        if len(candidates) < 2:
            print("❌ Need at least 2 candidates for evaluation")
            return
        
        print("\n📥 Loading job postings from Neo4j...")
        jobs = data_loader.load_job_postings(limit=1)
        print(f"   Loaded {len(jobs)} job postings")
        
        if not jobs:
            print("❌ No job postings found")
            return
        
        job = jobs[0]
        print(f"\n📋 Using job: {job.title}")
        if not job.required_skills:
            # Infer skills from candidates
            from collections import Counter
            all_skills = []
            for c in candidates:
                all_skills.extend([s.lower() for s in c.skills])
            skill_counts = Counter(all_skills)
            top_skills = [skill for skill, count in skill_counts.most_common(5)]
            job.required_skills = top_skills
            print(f"   Required skills were empty; inferred from candidates: {', '.join(top_skills)}")
        else:
            print(f"   Required skills: {', '.join(job.required_skills[:5])}{'...' if len(job.required_skills) > 5 else ''}")
        
        # Run explainability test
        print("\n" + "=" * 70)
        print("Running Explainability Test on 5 Sample Pairs...")
        print("=" * 70)
        
        explainability_test = ExplainabilityTest(algorithm)
        
        # Get ranked pairs
        pairs = explainability_test._get_ranked_pairs(job, candidates)
        
        # Limit to first 5 pairs
        sample_pairs = pairs[:5]
        print(f"\nSelected 5 candidate pairs for evaluation...")
        
        # Evaluate each pair
        results_list = []
        for candidate_a, candidate_b in sample_pairs:
            score_a = algorithm.calculate_match_score(job, candidate_a)
            score_b = algorithm.calculate_match_score(job, candidate_b)
            
            explanation = explainability_test.recruiter_agent.generate_explanation(
                job, candidate_a, candidate_b, score_a, score_b
            )
            
            breakdown = explainability_test.breakdown_extractor.extract_breakdown(job, candidate_a, candidate_b)
            validation = explainability_test.validator.validate_explanation(explanation, breakdown)
            
            results_list.append({
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
        
        # Calculate summary metrics
        total_tests = len(results_list)
        mentions_missing_skills = sum(1 for r in results_list if r['validation']['mentions_missing_skills'])
        mentions_skill_coverage = sum(1 for r in results_list if r['validation'].get('mentions_skill_coverage', False))
        avg_alignment = sum(r['validation']['alignment_score'] for r in results_list) / total_tests
        
        results = {
            'total_tests': total_tests,
            'mentions_missing_skills_rate': mentions_missing_skills / total_tests,
            'mentions_skill_coverage_rate': mentions_skill_coverage / total_tests,
            'average_alignment_score': avg_alignment,
            'detailed_results': results_list
        }
        
        # Display table
        create_results_table(results)
        
        print("✅ Evaluation complete!")
        
    finally:
        algorithm.close()
        data_loader.close()


if __name__ == "__main__":
    main()

