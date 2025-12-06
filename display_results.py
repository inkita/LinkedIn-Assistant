#!/usr/bin/env python3
"""
Display evaluation results in a formatted, presentable way.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime


def print_header(title: str, width: int = 80):
    """Print a formatted header"""
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width + "\n")


def print_section(title: str, width: int = 80):
    """Print a section header"""
    print("\n" + "-" * width)
    print(f"  {title}")
    print("-" * width)


def display_degradation_results(results: Dict):
    """Display skill degradation test results"""
    print_header("SKILL DEGRADATION TEST RESULTS", width=80)
    
    if 'error' in results:
        print(f"❌ Error: {results['error']}")
        return
    
    # Original candidate info
    print("📋 ORIGINAL CANDIDATE")
    print(f"   Name: {results['original_candidate']['name']}")
    print(f"   Title: {results['original_candidate']['title']}")
    print(f"   Experience: {results['original_candidate']['years_experience']} years")
    print(f"   Skills: {', '.join(results['original_candidate']['skills'])}")
    print(f"   Original Score: {results['original_score']:.3f}")
    
    print_section("DEGRADATION SEQUENCE")
    
    # Show degradation steps
    for i, step in enumerate(results['degradation_steps'], 1):
        step_type = step['type'].replace('_', ' ').title()
        if step['type'] == 'title':
            print(f"   Step {i}: {step_type} → {step['value']}")
        elif step['type'] == 'remove_skill':
            print(f"   Step {i}: {step_type} → Removed '{step['value']}'")
        elif step['type'] == 'reduce_experience':
            print(f"   Step {i}: {step_type} → Reduced by {step['years']} years")
        elif step['type'] == 'reduce_skill_level':
            print(f"   Step {i}: {step_type} → {step['skill']} → {step['level']}")
    
    print_section("SCORE DECAY ANALYSIS")
    
    # Show decay metrics
    print(f"{'Step':<8} {'Score':<12} {'Decay':<15} {'Cumulative':<15}")
    print("-" * 50)
    print(f"{'Original':<8} {results['original_score']:<12.3f} {'-':<15} {'0.0%':<15}")
    
    for metric in results['decay_metrics']:
        step = f"Step {metric['step']}"
        score = f"{metric['score']:.3f}"
        decay = f"{metric['percentage_decay']:.1f}%"
        cumulative = f"{metric['cumulative_decay']:.1f}%"
        print(f"{step:<8} {score:<12} {decay:<15} {cumulative:<15}")
    
    print_section("SUMMARY METRICS")
    
    print(f"   Final Score: {results['final_score']:.3f}")
    print(f"   Total Score Drop: {results['total_degradation']:.3f}")
    print(f"   Percentage Drop: {results['total_degradation_percentage']:.1f}%")
    
    if results['critical_point']:
        print(f"   ⚠️  Critical Point: Step {results['critical_point']} (score dropped below 50%)")
    else:
        print(f"   ℹ️  Critical Point: Not reached (score remained above 50%)")
    
    # Visual score decay
    print_section("VISUAL SCORE DECAY")
    max_score = results['original_score']
    bar_width = 50
    
    print(f"   Original: {'█' * bar_width} {results['original_score']:.3f}")
    
    for metric in results['decay_metrics']:
        bar_length = int((metric['score'] / max_score) * bar_width)
        bar = '█' * bar_length + '░' * (bar_width - bar_length)
        print(f"   Step {metric['step']}:  {bar} {metric['score']:.3f}")


def display_explainability_results(results: Dict):
    """Display explainability test results"""
    print_header("EXPLAINABILITY TEST RESULTS", width=80)
    
    if 'error' in results:
        print(f"❌ Error: {results['error']}")
        return
    
    print_section("OVERALL METRICS")
    
    print(f"   Total Candidate Pairs Tested: {results['total_tests']}")
    print(f"   Missing Skills Mention Rate: {results['mentions_missing_skills_rate']:.1%}")
    print(f"   Skill Coverage Mention Rate: {results.get('mentions_skill_coverage_rate', 0):.1%}")
    print(f"   Average Alignment Score: {results['average_alignment_score']:.3f}")
    
    # Visual indicators
    print("\n   Validation Coverage:")
    missing_coverage = results['mentions_missing_skills_rate']
    skill_coverage = results.get('mentions_skill_coverage_rate', 0)
    
    missing_bar = '█' * int(missing_coverage * 20) + '░' * int((1 - missing_coverage) * 20)
    coverage_bar = '█' * int(skill_coverage * 20) + '░' * int((1 - skill_coverage) * 20)
    
    print(f"   Missing Skills: {missing_bar} {missing_coverage:.1%}")
    print(f"   Skill Coverage: {coverage_bar} {skill_coverage:.1%}")
    
    print_section("DETAILED RESULTS")
    
    # Show first 5 detailed results
    detailed_results = results['detailed_results'][:5]
    
    for i, result in enumerate(detailed_results, 1):
        print(f"\n   Pair {i}: {result['candidate_a_name']} vs {result['candidate_b_name']}")
        print(f"   ──────────────────────────────────────────────────────────────")
        print(f"   Scores: {result['candidate_a_name']} = {result['score_a']:.3f}, "
              f"{result['candidate_b_name']} = {result['score_b']:.3f}")
        print(f"   Score Difference: {abs(result['score_a'] - result['score_b']):.3f}")
        
        # Breakdown
        breakdown = result['breakdown']
        print(f"\n   Scoring Breakdown:")
        print(f"   • {result['candidate_a_name']}:")
        print(f"     - Jaccard Similarity: {breakdown['candidate_a']['jaccard']:.3f}")
        print(f"     - Guttman Scaling: {breakdown['candidate_a']['guttman']:.3f}")
        print(f"     - Missing Skills: {', '.join(breakdown['candidate_a']['missing_skills']) if breakdown['candidate_a']['missing_skills'] else 'None'}")
        print(f"     - Seniority Level: {breakdown['candidate_a']['seniority_level']}")
        
        print(f"   • {result['candidate_b_name']}:")
        print(f"     - Jaccard Similarity: {breakdown['candidate_b']['jaccard']:.3f}")
        print(f"     - Guttman Scaling: {breakdown['candidate_b']['guttman']:.3f}")
        print(f"     - Missing Skills: {', '.join(breakdown['candidate_b']['missing_skills']) if breakdown['candidate_b']['missing_skills'] else 'None'}")
        print(f"     - Seniority Level: {breakdown['candidate_b']['seniority_level']}")
        
        # Explanation
        print(f"\n   Recruiter Agent Explanation:")
        explanation = result['explanation']
        # Wrap long explanations
        words = explanation.split()
        lines = []
        current_line = "     "
        for word in words:
            if len(current_line + word) > 75:
                lines.append(current_line)
                current_line = "     " + word + " "
            else:
                current_line += word + " "
        lines.append(current_line)
        for line in lines:
            print(line)
        
        # Validation
        validation = result['validation']
        print(f"\n   Validation:")
        print(f"     ✓ Mentions Missing Skills: {'✅ Yes' if validation['mentions_missing_skills'] else '❌ No'}")
        if validation['missing_skills_coverage']:
            print(f"       Covered Skills: {', '.join(validation['missing_skills_coverage'])}")
        print(f"     ✓ Mentions Skill Coverage: {'✅ Yes' if validation.get('mentions_skill_coverage', False) else '❌ No'}")
        if validation.get('skill_coverage_mentions'):
            print(f"       Keywords Found: {', '.join(set(validation['skill_coverage_mentions']))}")
        print(f"     ✓ Alignment Score: {validation['alignment_score']:.3f}")
    
    if len(results['detailed_results']) > 5:
        print(f"\n   ... and {len(results['detailed_results']) - 5} more pairs")


def display_summary(degradation_results: Dict, explainability_results: Dict):
    """Display combined summary"""
    print_header("EVALUATION PROTOCOLS SUMMARY", width=80)
    
    print("📊 SKILL DEGRADATION TEST")
    print("-" * 80)
    if 'error' not in degradation_results:
        print(f"   Original Score: {degradation_results.get('original_score', 0):.3f}")
        print(f"   Final Score: {degradation_results.get('final_score', 0):.3f}")
        print(f"   Score Drop: {degradation_results.get('total_degradation', 0):.3f} "
              f"({degradation_results.get('total_degradation_percentage', 0):.1f}%)")
        print(f"   Critical Point: Step {degradation_results.get('critical_point', 'N/A')}")
        print(f"   Total Degradation Steps: {len(degradation_results.get('degradation_steps', []))}")
    else:
        print(f"   ❌ Error: {degradation_results['error']}")
    
    print("\n💬 EXPLAINABILITY TEST")
    print("-" * 80)
    if 'error' not in explainability_results:
        print(f"   Total Tests: {explainability_results.get('total_tests', 0)}")
        print(f"   Missing Skills Mention Rate: {explainability_results.get('mentions_missing_skills_rate', 0):.1%}")
        print(f"   Skill Coverage Mention Rate: {explainability_results.get('mentions_skill_coverage_rate', 0):.1%}")
        print(f"   Average Alignment Score: {explainability_results.get('average_alignment_score', 0):.3f}")
    else:
        print(f"   ❌ Error: {explainability_results['error']}")
    
    print("\n" + "=" * 80)


def find_latest_results(results_dir: str = "results") -> Optional[tuple]:
    """Find the latest result files"""
    results_path = Path(results_dir)
    if not results_path.exists():
        return None
    
    degradation_files = list(results_path.glob("degradation_*.json"))
    explainability_files = list(results_path.glob("explainability_*.json"))
    
    if not degradation_files or not explainability_files:
        return None
    
    # Get latest files
    latest_degradation = max(degradation_files, key=lambda p: p.stat().st_mtime)
    latest_explainability = max(explainability_files, key=lambda p: p.stat().st_mtime)
    
    return latest_degradation, latest_explainability


def main():
    """Main function"""
    import argparse
    parser = argparse.ArgumentParser(description='Display evaluation results')
    parser.add_argument('--degradation', help='Path to degradation results JSON')
    parser.add_argument('--explainability', help='Path to explainability results JSON')
    parser.add_argument('--summary-only', action='store_true', help='Show only summary')
    parser.add_argument('--latest', action='store_true', help='Use latest results')
    
    args = parser.parse_args()
    
    degradation_file = None
    explainability_file = None
    
    if args.latest:
        latest = find_latest_results()
        if latest:
            degradation_file, explainability_file = latest
            print(f"📁 Using latest results:")
            print(f"   Degradation: {degradation_file}")
            print(f"   Explainability: {explainability_file}")
        else:
            print("❌ No result files found in results/ directory")
            sys.exit(1)
    else:
        degradation_file = args.degradation or "results/degradation_20251204_235444.json"
        explainability_file = args.explainability or "results/explainability_20251204_235444.json"
    
    # Load results
    try:
        with open(degradation_file, 'r') as f:
            degradation_results = json.load(f)
    except FileNotFoundError:
        print(f"❌ Degradation results file not found: {degradation_file}")
        sys.exit(1)
    
    try:
        with open(explainability_file, 'r') as f:
            explainability_results = json.load(f)
    except FileNotFoundError:
        print(f"❌ Explainability results file not found: {explainability_file}")
        sys.exit(1)
    
    # Display results
    if args.summary_only:
        display_summary(degradation_results, explainability_results)
    else:
        display_degradation_results(degradation_results)
        display_explainability_results(explainability_results)
        display_summary(degradation_results, explainability_results)
    
    print("\n✅ Results displayed successfully!\n")


if __name__ == "__main__":
    main()

