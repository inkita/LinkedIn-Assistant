#!/usr/bin/env python3
"""
Generate an HTML report from evaluation results.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional


def find_latest_results(results_dir: str = "results") -> Optional[tuple]:
    """Find the latest result files"""
    results_path = Path(results_dir)
    if not results_path.exists():
        return None
    
    degradation_files = list(results_path.glob("degradation_*.json"))
    explainability_files = list(results_path.glob("explainability_*.json"))
    
    if not degradation_files or not explainability_files:
        return None
    
    latest_degradation = max(degradation_files, key=lambda p: p.stat().st_mtime)
    latest_explainability = max(explainability_files, key=lambda p: p.stat().st_mtime)
    
    return latest_degradation, latest_explainability


def generate_html_report(degradation_results: Dict, explainability_results: Dict, output_file: str = "evaluation_report.html"):
    """Generate HTML report"""
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LinkedIn Assistant - Evaluation Protocols Report</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
            padding: 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #0066cc;
            border-bottom: 3px solid #0066cc;
            padding-bottom: 10px;
            margin-bottom: 30px;
        }}
        h2 {{
            color: #004499;
            margin-top: 30px;
            margin-bottom: 15px;
            padding-left: 10px;
            border-left: 4px solid #0066cc;
        }}
        h3 {{
            color: #555;
            margin-top: 20px;
            margin-bottom: 10px;
        }}
        .section {{
            margin-bottom: 40px;
            padding: 20px;
            background: #fafafa;
            border-radius: 5px;
        }}
        .metric {{
            display: inline-block;
            margin: 10px 20px 10px 0;
            padding: 15px 25px;
            background: white;
            border-radius: 5px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .metric-label {{
            font-size: 0.9em;
            color: #666;
            margin-bottom: 5px;
        }}
        .metric-value {{
            font-size: 1.8em;
            font-weight: bold;
            color: #0066cc;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            background: white;
        }}
        th {{
            background: #0066cc;
            color: white;
            padding: 12px;
            text-align: left;
        }}
        td {{
            padding: 10px;
            border-bottom: 1px solid #ddd;
        }}
        tr:hover {{
            background: #f5f5f5;
        }}
        .progress-bar {{
            width: 100%;
            height: 30px;
            background: #e0e0e0;
            border-radius: 15px;
            overflow: hidden;
            margin: 10px 0;
        }}
        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #0066cc, #0088ff);
            transition: width 0.3s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: bold;
        }}
        .badge {{
            display: inline-block;
            padding: 5px 10px;
            border-radius: 3px;
            font-size: 0.85em;
            font-weight: bold;
        }}
        .badge-success {{
            background: #4caf50;
            color: white;
        }}
        .badge-warning {{
            background: #ff9800;
            color: white;
        }}
        .badge-info {{
            background: #2196f3;
            color: white;
        }}
        .explanation-box {{
            background: #f9f9f9;
            padding: 15px;
            border-left: 4px solid #0066cc;
            margin: 10px 0;
            border-radius: 3px;
        }}
        .score-visual {{
            display: flex;
            align-items: center;
            margin: 10px 0;
        }}
        .score-bar {{
            flex: 1;
            height: 25px;
            background: #e0e0e0;
            border-radius: 12px;
            overflow: hidden;
            margin-right: 10px;
        }}
        .score-fill {{
            height: 100%;
            background: linear-gradient(90deg, #0066cc, #0088ff);
        }}
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .summary-card {{
            background: white;
            padding: 20px;
            border-radius: 5px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }}
        .timestamp {{
            text-align: right;
            color: #666;
            font-size: 0.9em;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 LinkedIn Assistant - Evaluation Protocols Report</h1>
        <p style="color: #666; margin-bottom: 30px;">
            This report presents the results of the Skill Degradation Test and Explainability Test 
            for the LinkedIn Assistant Hybrid Algorithm evaluation.
        </p>
"""
    
    # Skill Degradation Section
    if 'error' not in degradation_results:
        html += """
        <div class="section">
            <h2>📉 Skill Degradation Test</h2>
            
            <h3>Original Candidate</h3>
            <div class="summary-grid">
                <div class="summary-card">
                    <div class="metric-label">Name</div>
                    <div class="metric-value" style="font-size: 1.2em;">""" + degradation_results['original_candidate']['name'] + """</div>
                </div>
                <div class="summary-card">
                    <div class="metric-label">Title</div>
                    <div class="metric-value" style="font-size: 1.2em;">""" + degradation_results['original_candidate']['title'] + """</div>
                </div>
                <div class="summary-card">
                    <div class="metric-label">Experience</div>
                    <div class="metric-value" style="font-size: 1.2em;">""" + str(degradation_results['original_candidate']['years_experience']) + """ years</div>
                </div>
                <div class="summary-card">
                    <div class="metric-label">Original Score</div>
                    <div class="metric-value">""" + f"{degradation_results['original_score']:.3f}" + """</div>
                </div>
            </div>
            
            <h3>Score Decay Analysis</h3>
            <table>
                <thead>
                    <tr>
                        <th>Step</th>
                        <th>Score</th>
                        <th>Decay</th>
                        <th>Cumulative Decay</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td><strong>Original</strong></td>
                        <td><strong>""" + f"{degradation_results['original_score']:.3f}" + """</strong></td>
                        <td>-</td>
                        <td>0.0%</td>
                    </tr>
"""
        
        for metric in degradation_results['decay_metrics']:
            html += f"""
                    <tr>
                        <td>Step {metric['step']}</td>
                        <td>{metric['score']:.3f}</td>
                        <td>{metric['percentage_decay']:.1f}%</td>
                        <td>{metric['cumulative_decay']:.1f}%</td>
                    </tr>
"""
        
        html += """
                </tbody>
            </table>
            
            <h3>Summary Metrics</h3>
            <div class="summary-grid">
                <div class="summary-card">
                    <div class="metric-label">Final Score</div>
                    <div class="metric-value">""" + f"{degradation_results['final_score']:.3f}" + """</div>
                </div>
                <div class="summary-card">
                    <div class="metric-label">Total Score Drop</div>
                    <div class="metric-value">""" + f"{degradation_results['total_degradation']:.3f}" + """</div>
                </div>
                <div class="summary-card">
                    <div class="metric-label">Percentage Drop</div>
                    <div class="metric-value">""" + f"{degradation_results['total_degradation_percentage']:.1f}%" + """</div>
                </div>
                <div class="summary-card">
                    <div class="metric-label">Critical Point</div>
                    <div class="metric-value" style="font-size: 1.2em;">""" + (f"Step {degradation_results['critical_point']}" if degradation_results['critical_point'] else "Not reached") + """</div>
                </div>
            </div>
            
            <h3>Visual Score Decay</h3>
"""
        
        max_score = degradation_results['original_score']
        for metric in degradation_results['decay_metrics']:
            percentage = (metric['score'] / max_score) * 100
            html += f"""
            <div class="score-visual">
                <div style="width: 100px; font-weight: bold;">Step {metric['step']}:</div>
                <div class="score-bar">
                    <div class="score-fill" style="width: {percentage}%;"></div>
                </div>
                <div style="width: 80px; text-align: right; font-weight: bold;">{metric['score']:.3f}</div>
            </div>
"""
    
    # Explainability Section
    if 'error' not in explainability_results:
        html += """
        <div class="section">
            <h2>💬 Explainability Test</h2>
            
            <h3>Overall Metrics</h3>
            <div class="summary-grid">
                <div class="summary-card">
                    <div class="metric-label">Total Tests</div>
                    <div class="metric-value">""" + str(explainability_results['total_tests']) + """</div>
                </div>
                <div class="summary-card">
                    <div class="metric-label">Missing Skills Mention Rate</div>
                    <div class="metric-value">""" + f"{explainability_results['mentions_missing_skills_rate']:.1%}" + """</div>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: """ + f"{explainability_results['mentions_missing_skills_rate'] * 100}" + """%;">
                            """ + f"{explainability_results['mentions_missing_skills_rate']:.1%}" + """
                        </div>
                    </div>
                </div>
                <div class="summary-card">
                    <div class="metric-label">Seniority Mention Rate</div>
                    <div class="metric-value">""" + f"{explainability_results['mentions_seniority_rate']:.1%}" + """</div>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: """ + f"{explainability_results['mentions_seniority_rate'] * 100}" + """%;">
                            """ + f"{explainability_results['mentions_seniority_rate']:.1%}" + """
                        </div>
                    </div>
                </div>
                <div class="summary-card">
                    <div class="metric-label">Average Alignment Score</div>
                    <div class="metric-value">""" + f"{explainability_results['average_alignment_score']:.3f}" + """</div>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: """ + f"{explainability_results['average_alignment_score'] * 100}" + """%;">
                            """ + f"{explainability_results['average_alignment_score']:.1%}" + """
                        </div>
                    </div>
                </div>
            </div>
            
            <h3>Sample Explanations</h3>
"""
        
        for i, result in enumerate(explainability_results['detailed_results'][:5], 1):
            validation = result['validation']
            html += f"""
            <div style="margin: 20px 0; padding: 15px; background: white; border-radius: 5px; border-left: 4px solid #0066cc;">
                <h4>Pair {i}: {result['candidate_a_name']} vs {result['candidate_b_name']}</h4>
                <p><strong>Scores:</strong> {result['candidate_a_name']} = {result['score_a']:.3f}, {result['candidate_b_name']} = {result['score_b']:.3f}</p>
                
                <div class="explanation-box">
                    <strong>Recruiter Agent Explanation:</strong><br>
                    {result['explanation']}
                </div>
                
                <div style="margin-top: 10px;">
                    <span class="badge {'badge-success' if validation['mentions_missing_skills'] else 'badge-warning'}">
                        {'✓' if validation['mentions_missing_skills'] else '✗'} Missing Skills
                    </span>
                    <span class="badge {'badge-success' if validation['mentions_seniority'] else 'badge-warning'}">
                        {'✓' if validation['mentions_seniority'] else '✗'} Seniority
                    </span>
                    <span class="badge badge-info">
                        Alignment: {validation['alignment_score']:.3f}
                    </span>
                </div>
            </div>
"""
    
    # Summary Section
    html += """
        <div class="section">
            <h2>📋 Executive Summary</h2>
            <div class="summary-grid">
"""
    
    if 'error' not in degradation_results:
        html += f"""
                <div class="summary-card">
                    <h3>Skill Degradation</h3>
                    <p><strong>Score Drop:</strong> {degradation_results['total_degradation']:.3f} ({degradation_results['total_degradation_percentage']:.1f}%)</p>
                    <p><strong>Critical Point:</strong> {'Step ' + str(degradation_results['critical_point']) if degradation_results['critical_point'] else 'Not reached'}</p>
                </div>
"""
    
    if 'error' not in explainability_results:
        html += f"""
                <div class="summary-card">
                    <h3>Explainability</h3>
                    <p><strong>Missing Skills Coverage:</strong> {explainability_results['mentions_missing_skills_rate']:.1%}</p>
                    <p><strong>Seniority Coverage:</strong> {explainability_results['mentions_seniority_rate']:.1%}</p>
                    <p><strong>Alignment Score:</strong> {explainability_results['average_alignment_score']:.3f}</p>
                </div>
"""
    
    html += f"""
            </div>
        </div>
        
        <div class="timestamp">
            Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        </div>
    </div>
</body>
</html>
"""
    
    with open(output_file, 'w') as f:
        f.write(html)
    
    return output_file


def main():
    """Main function"""
    import argparse
    parser = argparse.ArgumentParser(description='Generate HTML report from evaluation results')
    parser.add_argument('--degradation', help='Path to degradation results JSON')
    parser.add_argument('--explainability', help='Path to explainability results JSON')
    parser.add_argument('--output', default='evaluation_report.html', help='Output HTML file')
    parser.add_argument('--latest', action='store_true', help='Use latest results')
    
    args = parser.parse_args()
    
    if args.latest:
        latest = find_latest_results()
        if latest:
            degradation_file, explainability_file = latest
        else:
            print("❌ No result files found")
            return
    else:
        degradation_file = args.degradation or "results/degradation_20251204_235444.json"
        explainability_file = args.explainability or "results/explainability_20251204_235444.json"
    
    # Load results
    with open(degradation_file, 'r') as f:
        degradation_results = json.load(f)
    
    with open(explainability_file, 'r') as f:
        explainability_results = json.load(f)
    
    # Generate HTML
    output_file = generate_html_report(degradation_results, explainability_results, args.output)
    print(f"✅ HTML report generated: {output_file}")
    print(f"   Open it in your browser to view the results!")


if __name__ == "__main__":
    main()

