"""
Reporting utilities for evaluation results.
"""

import json
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path


class ReportGenerator:
    """Generate reports from evaluation test results"""
    
    def __init__(self, output_dir: str = "results"):
        """
        Initialize report generator.
        
        Args:
            output_dir: Directory to save reports
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
    
    def save_degradation_results(self, results: Dict, filename: Optional[str] = None) -> str:
        """
        Save skill degradation test results to JSON file.
        
        Args:
            results: Results from SkillDegradationTest.run_test()
            filename: Optional custom filename
            
        Returns:
            Path to saved file
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"degradation_{timestamp}.json"
        
        filepath = self.output_dir / filename
        with open(filepath, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        return str(filepath)
    
    def save_explainability_results(self, results: Dict, filename: Optional[str] = None) -> str:
        """
        Save explainability test results to JSON file.
        
        Args:
            results: Results from ExplainabilityTest.run_test()
            filename: Optional custom filename
            
        Returns:
            Path to saved file
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"explainability_{timestamp}.json"
        
        filepath = self.output_dir / filename
        with open(filepath, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        return str(filepath)
    
    def generate_summary_report(self, degradation_results: Dict, explainability_results: Dict, 
                                filename: Optional[str] = None) -> str:
        """
        Generate a summary report combining both test results.
        
        Args:
            degradation_results: Results from SkillDegradationTest
            explainability_results: Results from ExplainabilityTest
            filename: Optional custom filename
            
        Returns:
            Path to saved file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        summary = {
            'timestamp': timestamp,
            'degradation_test': {
                'original_score': degradation_results.get('original_score'),
                'final_score': degradation_results.get('final_score'),
                'score_drop': degradation_results.get('total_degradation'),
                'score_drop_percentage': degradation_results.get('total_degradation_percentage'),
                'critical_point': degradation_results.get('critical_point'),
                'total_steps': len(degradation_results.get('degradation_steps', []))
            },
            'explainability_test': {
                'total_tests': explainability_results.get('total_tests', 0),
                'mentions_missing_skills_rate': explainability_results.get('mentions_missing_skills_rate', 0),
                'mentions_skill_coverage_rate': explainability_results.get('mentions_skill_coverage_rate', 0),
                'average_alignment_score': explainability_results.get('average_alignment_score', 0)
            }
        }
        
        if filename is None:
            filename = f"summary_{timestamp}.json"
        
        filepath = self.output_dir / filename
        with open(filepath, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        return str(filepath)
    
    def print_summary(self, degradation_results: Dict, explainability_results: Dict):
        """Print a human-readable summary to console"""
        print("\n" + "=" * 70)
        print("EVALUATION PROTOCOLS SUMMARY")
        print("=" * 70)
        
        print("\n📊 SKILL DEGRADATION TEST")
        print("-" * 70)
        if 'error' not in degradation_results:
            print(f"Original Score: {degradation_results.get('original_score', 0):.3f}")
            print(f"Final Score: {degradation_results.get('final_score', 0):.3f}")
            print(f"Score Drop: {degradation_results.get('total_degradation', 0):.3f} ({degradation_results.get('total_degradation_percentage', 0):.1f}%)")
            print(f"Critical Point: Step {degradation_results.get('critical_point', 'N/A')}")
            print(f"Total Degradation Steps: {len(degradation_results.get('degradation_steps', []))}")
        else:
            print(f"Error: {degradation_results['error']}")
        
        print("\n💬 EXPLAINABILITY TEST")
        print("-" * 70)
        if 'error' not in explainability_results:
            print(f"Total Tests: {explainability_results.get('total_tests', 0)}")
            print(f"Missing Skills Mention Rate: {explainability_results.get('mentions_missing_skills_rate', 0):.1%}")
            print(f"Skill Coverage Mention Rate: {explainability_results.get('mentions_skill_coverage_rate', 0):.1%}")
            print(f"Average Alignment Score: {explainability_results.get('average_alignment_score', 0):.3f}")
        else:
            print(f"Error: {explainability_results['error']}")
        
        print("\n" + "=" * 70)

