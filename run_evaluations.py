#!/usr/bin/env python3
"""
Main script to run evaluation protocols for LinkedIn Assistant.

Usage:
    python run_evaluations.py [--degradation] [--explainability] [--all]
"""

import argparse
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.algorithm import HybridAlgorithm
from src.models import Candidate, JobPosting
from src.evaluation import SkillDegradationTest, ExplainabilityTest
from src.utils import ReportGenerator


def create_sample_data():
    """Create sample data for testing"""
    job = JobPosting(
        id="job1",
        title="Senior Software Engineer",
        required_skills=["Python", "Java", "System Design", "AWS", "Docker"],
        experience_level="Senior",
        description="Looking for an experienced software engineer..."
    )
    
    candidates = [
        Candidate(
            id="cand1",
            name="Alice Johnson",
            current_title="Lead Architect",
            skills=["Python", "Java", "System Design", "AWS", "Docker", "Kubernetes"],
            years_experience=8,
            skill_proficiencies={
                "Python": "Expert",
                "Java": "Advanced",
                "System Design": "Expert",
                "AWS": "Advanced"
            }
        ),
        Candidate(
            id="cand2",
            name="Bob Smith",
            current_title="Junior Developer",
            skills=["Python", "JavaScript"],
            years_experience=2,
            skill_proficiencies={
                "Python": "Intermediate"
            }
        ),
        Candidate(
            id="cand3",
            name="Charlie Brown",
            current_title="Senior Engineer",
            skills=["Python", "Java", "AWS", "Docker"],
            years_experience=6,
            skill_proficiencies={
                "Python": "Advanced",
                "Java": "Advanced",
                "AWS": "Advanced"
            }
        ),
        Candidate(
            id="cand4",
            name="Diana Prince",
            current_title="Mid-level Developer",
            skills=["Python", "Java", "System Design"],
            years_experience=4,
            skill_proficiencies={
                "Python": "Intermediate",
                "Java": "Intermediate"
            }
        ),
    ]
    
    return job, candidates


def run_degradation_test(algorithm, job, candidates, reporter):
    """Run skill degradation test"""
    print("\n" + "=" * 70)
    print("Running Skill Degradation Test...")
    print("=" * 70)
    
    test = SkillDegradationTest(algorithm)
    results = test.run_test(job, candidates)
    
    if 'error' in results:
        print(f"Error: {results['error']}")
        return None
    
    # Print results
    print(f"\nOriginal Candidate: {results['original_candidate']['name']}")
    print(f"Original Title: {results['original_candidate']['title']}")
    print(f"Original Score: {results['original_score']:.3f}")
    print(f"\nDegradation Steps: {len(results['degradation_steps'])}")
    print("\nScore Decay:")
    for metric in results['decay_metrics']:
        print(f"  Step {metric['step']}: Score={metric['score']:.3f}, "
              f"Decay={metric['cumulative_decay']:.1f}%")
    
    print(f"\nFinal Score: {results['final_score']:.3f}")
    print(f"Total Degradation: {results['total_degradation']:.3f} ({results['total_degradation_percentage']:.1f}%)")
    if results['critical_point']:
        print(f"Critical Point: Step {results['critical_point']}")
    
    # Save results
    filepath = reporter.save_degradation_results(results)
    print(f"\nResults saved to: {filepath}")
    
    return results


def run_explainability_test(algorithm, job, candidates, reporter):
    """Run explainability test"""
    print("\n" + "=" * 70)
    print("Running Explainability Test...")
    print("=" * 70)
    
    test = ExplainabilityTest(algorithm)
    results = test.run_test(job, candidates)
    
    if 'error' in results:
        print(f"Error: {results['error']}")
        return None
    
    # Print results
    print(f"\nTotal Candidate Pairs Tested: {results['total_tests']}")
    print(f"Missing Skills Mention Rate: {results['mentions_missing_skills_rate']:.1%}")
    print(f"Seniority Mention Rate: {results['mentions_seniority_rate']:.1%}")
    print(f"Average Alignment Score: {results['average_alignment_score']:.3f}")
    
    # Show sample explanations
    print("\nSample Explanations:")
    for i, result in enumerate(results['detailed_results'][:3], 1):
        print(f"\n{i}. {result['candidate_a_name']} (score: {result['score_a']:.3f}) vs "
              f"{result['candidate_b_name']} (score: {result['score_b']:.3f})")
        print(f"   Explanation: {result['explanation'][:150]}...")
        print(f"   Mentions Missing Skills: {result['validation']['mentions_missing_skills']}")
        print(f"   Mentions Seniority: {result['validation']['mentions_seniority']}")
        print(f"   Alignment Score: {result['validation']['alignment_score']:.3f}")
    
    # Save results
    filepath = reporter.save_explainability_results(results)
    print(f"\nResults saved to: {filepath}")
    
    return results


def main():
    parser = argparse.ArgumentParser(description='Run evaluation protocols for LinkedIn Assistant')
    parser.add_argument('--degradation', action='store_true', help='Run skill degradation test')
    parser.add_argument('--explainability', action='store_true', help='Run explainability test')
    parser.add_argument('--all', action='store_true', help='Run all tests')
    parser.add_argument('--output-dir', default='results', help='Output directory for results')
    
    args = parser.parse_args()
    
    # If no specific test is selected, run all
    if not args.degradation and not args.explainability:
        args.all = True
    
    # Initialize components
    algorithm = HybridAlgorithm()
    reporter = ReportGenerator(output_dir=args.output_dir)
    
    # Create sample data (replace with your actual data loading)
    job, candidates = create_sample_data()
    
    degradation_results = None
    explainability_results = None
    
    # Run tests
    if args.all or args.degradation:
        degradation_results = run_degradation_test(algorithm, job, candidates, reporter)
    
    if args.all or args.explainability:
        explainability_results = run_explainability_test(algorithm, job, candidates, reporter)
    
    # Generate summary
    if degradation_results and explainability_results:
        summary_path = reporter.generate_summary_report(degradation_results, explainability_results)
        reporter.print_summary(degradation_results, explainability_results)
        print(f"\nSummary report saved to: {summary_path}")
    
    print("\n✅ Evaluation complete!")


if __name__ == "__main__":
    main()

