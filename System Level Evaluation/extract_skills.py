#!/usr/bin/env python3
"""
Extract skills from resumes and job descriptions using NER and keyword matching.
"""

import pandas as pd
import re
import json
from pathlib import Path
from collections import Counter
import numpy as np

# Comprehensive skill vocabulary
TECHNICAL_SKILLS = {
    # Programming Languages
    'python', 'java', 'javascript', 'c++', 'c#', 'ruby', 'php', 'swift', 'kotlin', 
    'typescript', 'go', 'rust', 'scala', 'r', 'matlab', 'perl', 'sql',
    
    # Web Technologies
    'html', 'css', 'react', 'angular', 'vue', 'node.js', 'nodejs', 'express', 
    'django', 'flask', 'spring', 'asp.net', 'jquery', 'bootstrap', 'webpack',
    
    # Databases
    'mysql', 'postgresql', 'mongodb', 'oracle', 'sql server', 'redis', 'cassandra',
    'dynamodb', 'elasticsearch', 'sqlite', 'mariadb',
    
    # Cloud & DevOps
    'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'jenkins', 'gitlab', 'github',
    'terraform', 'ansible', 'chef', 'puppet', 'ci/cd', 'devops',
    
    # Data Science & ML
    'machine learning', 'deep learning', 'tensorflow', 'pytorch', 'keras', 'scikit-learn',
    'pandas', 'numpy', 'spark', 'hadoop', 'tableau', 'power bi', 'data analysis',
    'statistics', 'nlp', 'computer vision', 'ai', 'neural networks',
    
    # Tools & Frameworks
    'git', 'jira', 'confluence', 'agile', 'scrum', 'kanban', 'rest api', 'graphql',
    'microservices', 'api', 'json', 'xml', 'linux', 'unix', 'windows', 'macos',
    
    # Testing
    'junit', 'selenium', 'pytest', 'jest', 'testing', 'qa', 'quality assurance',
    'automation', 'unit testing', 'integration testing',
    
    # Other Technical
    'sap', 'erp', 'crm', 'salesforce', 'oracle', 'peoplesoft', 'workday',
}

SOFT_SKILLS = {
    # Communication
    'communication', 'verbal communication', 'written communication', 'presentation',
    'public speaking', 'interpersonal', 'negotiation', 'persuasion',
    
    # Leadership
    'leadership', 'team management', 'project management', 'people management',
    'mentoring', 'coaching', 'delegation', 'decision making',
    
    # Collaboration
    'teamwork', 'collaboration', 'cross-functional', 'stakeholder management',
    
    # Problem Solving
    'problem solving', 'critical thinking', 'analytical', 'troubleshooting',
    'debugging', 'research', 'analysis',
    
    # Organization
    'organization', 'time management', 'multitasking', 'prioritization',
    'planning', 'attention to detail', 'detail-oriented',
    
    # Adaptability
    'adaptability', 'flexibility', 'learning', 'innovation', 'creativity',
}

BUSINESS_SKILLS = {
    # Sales & Marketing
    'sales', 'marketing', 'business development', 'account management', 'crm',
    'lead generation', 'customer acquisition', 'revenue growth', 'cold calling',
    'sales strategy', 'market research', 'seo', 'sem', 'social media marketing',
    
    # Finance & Accounting
    'accounting', 'finance', 'bookkeeping', 'financial analysis', 'budgeting',
    'forecasting', 'accounts payable', 'accounts receivable', 'payroll', 'gaap',
    'financial modeling', 'excel', 'quickbooks',
    
    # Operations
    'operations', 'supply chain', 'logistics', 'inventory management', 'procurement',
    'vendor management', 'process improvement', 'lean', 'six sigma',
    
    # HR
    'recruiting', 'talent acquisition', 'hr', 'human resources', 'onboarding',
    'performance management', 'employee relations', 'benefits administration',
    
    # Customer Service
    'customer service', 'customer support', 'client relations', 'customer satisfaction',
    'help desk', 'technical support',
}

# Combine all skill vocabularies
ALL_SKILLS = TECHNICAL_SKILLS | SOFT_SKILLS | BUSINESS_SKILLS

# Create bigrams and trigrams for multi-word skills
MULTIWORD_SKILLS = {skill for skill in ALL_SKILLS if ' ' in skill}

def extract_skills_from_text(text):
    """
    Extract skills from text using keyword matching.
    
    Returns:
        list: List of extracted skills
    """
    if pd.isna(text):
        return []
    
    text = str(text).lower()
    
    # Remove special characters but keep spaces and hyphens
    text = re.sub(r'[^\w\s-]', ' ', text)
    
    found_skills = set()
    
    # First, extract multi-word skills (to avoid partial matches)
    for skill in MULTIWORD_SKILLS:
        # Use word boundaries to avoid partial matches
        pattern = r'\b' + re.escape(skill) + r'\b'
        if re.search(pattern, text):
            found_skills.add(skill)
    
    # Then extract single-word skills
    words = set(text.split())
    for skill in ALL_SKILLS:
        if ' ' not in skill:  # Single word skill
            if skill in words or skill.replace('-', '') in words:
                found_skills.add(skill)
    
    return sorted(list(found_skills))


def extract_experience_years(text):
    """
    Extract years of experience from text.
    
    Returns:
        float or None: Estimated years of experience
    """
    if pd.isna(text):
        return None
    
    text = str(text).lower()
    
    # Pattern: "X years", "X+ years", "X-Y years"
    patterns = [
        r'(\d+)\+?\s*(?:years?|yrs?)',
        r'(\d+)\s*(?:to|-)\s*(\d+)\s*(?:years?|yrs?)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            if len(match.groups()) == 1:
                return float(match.group(1))
            else:
                # Take average of range
                return (float(match.group(1)) + float(match.group(2))) / 2
    
    return None


def extract_skills_from_resume_dataset(resume_csv_path, output_path=None):
    """
    Extract skills from resume dataset and save enriched version.
    
    Args:
        resume_csv_path: Path to resume CSV file
        output_path: Path to save enriched resume CSV (optional)
    
    Returns:
        DataFrame with extracted skills
    """
    print(f"Loading resumes from {resume_csv_path}...")
    df = pd.read_csv(resume_csv_path)
    
    print(f"Loaded {len(df)} resumes")
    
    # Extract skills from Resume_str
    print("Extracting skills from resumes...")
    df['extracted_skills'] = df['Resume_str'].apply(extract_skills_from_text)
    df['skills_count'] = df['extracted_skills'].apply(len)
    
    # Convert to JSON string for storage
    df['extracted_skills_json'] = df['extracted_skills'].apply(json.dumps)
    
    # Show statistics
    total_skills = df['skills_count'].sum()
    avg_skills = df['skills_count'].mean()
    
    print(f"\nExtraction Statistics:")
    print(f"  Total skills extracted: {total_skills}")
    print(f"  Average skills per resume: {avg_skills:.1f}")
    print(f"  Resumes with 0 skills: {(df['skills_count'] == 0).sum()}")
    print(f"  Resumes with 5+ skills: {(df['skills_count'] >= 5).sum()}")
    
    # Show most common skills
    all_skills_list = [skill for skills in df['extracted_skills'] for skill in skills]
    skill_counts = Counter(all_skills_list)
    print(f"\nTop 20 most common skills:")
    for skill, count in skill_counts.most_common(20):
        print(f"  {skill}: {count}")
    
    # Save if output path provided
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Save with extracted skills
        df.to_csv(output_path, index=False)
        print(f"\nSaved enriched resume data to: {output_path}")
    
    return df


def extract_skills_from_job_dataset(job_file_path, output_path=None):
    """
    Extract skills from job dataset and save enriched version.
    
    Args:
        job_file_path: Path to job file (CSV or Excel)
        output_path: Path to save enriched job CSV (optional)
    
    Returns:
        DataFrame with extracted skills
    """
    print(f"Loading jobs from {job_file_path}...")
    
    file_path = Path(job_file_path)
    if file_path.suffix.lower() in ['.xlsx', '.xls']:
        df = pd.read_excel(job_file_path, engine='openpyxl')
    else:
        df = pd.read_csv(job_file_path)
    
    print(f"Loaded {len(df)} jobs")
    
    # Extract skills from title + description
    print("Extracting skills from job descriptions...")
    
    def extract_from_job(row):
        text = ''
        if 'title' in df.columns and pd.notna(row['title']):
            text += str(row['title']) + ' '
        if 'description' in df.columns and pd.notna(row['description']):
            text += str(row['description'])
        return extract_skills_from_text(text)
    
    df['extracted_skills'] = df.apply(extract_from_job, axis=1)
    df['skills_count'] = df['extracted_skills'].apply(len)
    
    # Convert to JSON string for storage
    df['extracted_skills_json'] = df['extracted_skills'].apply(json.dumps)
    
    # Show statistics
    total_skills = df['skills_count'].sum()
    avg_skills = df['skills_count'].mean()
    
    print(f"\nExtraction Statistics:")
    print(f"  Total skills extracted: {total_skills}")
    print(f"  Average skills per job: {avg_skills:.1f}")
    print(f"  Jobs with 0 skills: {(df['skills_count'] == 0).sum()}")
    print(f"  Jobs with 5+ skills: {(df['skills_count'] >= 5).sum()}")
    
    # Show most common skills
    all_skills_list = [skill for skills in df['extracted_skills'] for skill in skills]
    skill_counts = Counter(all_skills_list)
    print(f"\nTop 20 most common skills in jobs:")
    for skill, count in skill_counts.most_common(20):
        print(f"  {skill}: {count}")
    
    # Save if output path provided
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        df.to_csv(output_path, index=False)
        print(f"\nSaved enriched job data to: {output_path}")
    
    return df


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Extract skills from resumes and job descriptions')
    parser.add_argument('--resume-csv', help='Path to resume CSV file')
    parser.add_argument('--job-file', help='Path to job file (CSV or Excel)')
    parser.add_argument('--output-resume', help='Output path for enriched resume CSV')
    parser.add_argument('--output-job', help='Output path for enriched job CSV')
    
    args = parser.parse_args()
    
    if args.resume_csv:
        extract_skills_from_resume_dataset(args.resume_csv, args.output_resume)
    
    if args.job_file:
        extract_skills_from_job_dataset(args.job_file, args.output_job)
    
    if not args.resume_csv and not args.job_file:
        print("Please provide --resume-csv or --job-file")
        parser.print_help()
