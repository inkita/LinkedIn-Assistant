#!/usr/bin/env python3
"""
Search jobs given a resume using BM25 or FAISS.

Returns: job_id, company_name, position (title), years_experience, category, skills_matched

Usage:
  # Search using resume index
  python3 scripts/search_jobs_for_resume.py --resume-index 0 --method faiss --topk 5
  
  # Search using resume text
  python3 scripts/search_jobs_for_resume.py --resume-text "Python developer with 5 years experience" --method bm25 --topk 10
  
  # Search using resume from CSV
  python3 scripts/search_jobs_for_resume.py --resume-csv data/resume_unpacked/Resume/Resume.csv --row 0 --method both --topk 5
"""
import argparse
import json
import pickle
import re
from pathlib import Path
import numpy as np
import pandas as pd


def simple_tokenize(text):
    if not text:
        return []
    return re.findall(r'\w+', str(text).lower())


def load_resume_text(resume_index=None, resume_text=None, resume_csv=None, row=None):
    """Load resume text from index, direct text, or CSV."""
    if resume_text:
        return resume_text
    
    if resume_index is not None:
        # Load from resume CSV
        paths = [
            Path('data/resume_unpacked/Resume/Resume.csv'),
            Path('outputs/resumes_augmented.csv')
        ]
        for p in paths:
            if p.exists():
                df = pd.read_csv(p, low_memory=False)
                if resume_index >= len(df):
                    raise ValueError(f'Resume index {resume_index} out of range (max {len(df)-1})')
                
                # Get Resume_str + Category
                cols = {c.lower(): c for c in df.columns}
                text_col = None
                for c in ['resume_str', 'resume', 'resume_text', 'text']:
                    if c in cols:
                        text_col = cols[c]
                        break
                if text_col is None:
                    text_col = df.columns[-1]
                
                cat_col = None
                if 'category' in cols:
                    cat_col = cols['category']
                
                text_parts = [str(df.loc[resume_index, text_col])]
                if cat_col and pd.notna(df.loc[resume_index, cat_col]):
                    text_parts.append(str(df.loc[resume_index, cat_col]))
                
                return ' '.join(text_parts)
    
    if resume_csv and row is not None:
        p = Path(resume_csv)
        if not p.exists():
            raise FileNotFoundError(f'{p} not found')
        
        # Detect file type and use appropriate reader
        if p.suffix.lower() in ['.xlsx', '.xls']:
            df = pd.read_excel(p, engine='openpyxl' if p.suffix.lower() == '.xlsx' else None)
        else:
            df = pd.read_csv(p, low_memory=False)
        
        if row >= len(df):
            raise ValueError(f'Row {row} out of range (max {len(df)-1})')
        
        cols = {c.lower(): c for c in df.columns}
        text_col = None
        for c in ['resume_str', 'resume', 'resume_text', 'text']:
            if c in cols:
                text_col = cols[c]
                break
        if text_col is None:
            text_col = df.columns[-1]
        
        cat_col = None
        if 'category' in cols:
            cat_col = cols['category']
        
        text_parts = [str(df.loc[row, text_col])]
        if cat_col and pd.notna(df.loc[row, cat_col]):
            text_parts.append(str(df.loc[row, cat_col]))
        
        return ' '.join(text_parts)
    
    raise ValueError('Must provide --resume-index, --resume-text, or --resume-csv with --row')


def search_bm25(query_text, topk=5):
    """Search jobs using BM25."""
    index_dir = Path('outputs/indexes')
    
    # Load BM25
    with open(index_dir / 'bm25_job.pkl', 'rb') as f:
        bm25 = pickle.load(f)
    
    # Tokenize query
    query_tokens = simple_tokenize(query_text)
    if not query_tokens:
        return []
    
    # Get scores
    scores = bm25.get_scores(query_tokens)
    
    # Get top-k indices
    top_indices = np.argsort(scores)[::-1][:topk]
    
    # Load metadata
    with open(index_dir / 'metadata_jobs.json', 'r') as f:
        metadata = json.load(f)
    
    # Load corpus tokens to compute skill overlap
    with open(index_dir / 'bm25_corpus_tokens.pkl', 'rb') as f:
        corpus_tokens = pickle.load(f)
    
    # Load skill extraction function
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from extract_skills import extract_skills_from_text
    
    # Extract skills from query
    query_skills = set(extract_skills_from_text(query_text))
    
    results = []
    
    for rank, idx in enumerate(top_indices, 1):
        if idx >= len(metadata):
            continue
        
        meta = metadata[idx]
        
        # Use extracted skills from metadata
        job_skills = set(meta.get('extracted_skills', []))
        matched_skills = query_skills & job_skills
        
        results.append({
            'rank': rank,
            'job_id': meta.get('job_id'),
            'company_name': meta.get('company_name'),
            'position': meta.get('title'),
            'years_experience': meta.get('years_experience'),
            'location': meta.get('location'),
            'posted_date': meta.get('posted_date'),
            'category': None,  # Not in job metadata
            'skills_matched': sorted(list(matched_skills)),  # Use extracted skills
            'score': float(scores[idx]),
            'method': 'bm25'
        })
    
    return results


def search_faiss(query_text, topk=5):
    """Search jobs using FAISS."""
    index_dir = Path('outputs/indexes')
    
    try:
        import faiss
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        raise RuntimeError(f'Missing dependency: {e}. Install with: pip install faiss-cpu sentence-transformers')
    
    # Load model and encode query
    model = SentenceTransformer('all-MiniLM-L6-v2')
    query_emb = model.encode([query_text], convert_to_numpy=True).astype('float32')
    faiss.normalize_L2(query_emb)
    
    # Load FAISS index
    index = faiss.read_index(str(index_dir / 'faiss_job.index'))
    
    # Search
    D, I = index.search(query_emb, topk)
    
    # Load metadata
    with open(index_dir / 'metadata_jobs.json', 'r') as f:
        metadata = json.load(f)
    
    # Load job embeddings to compute skill similarity (approximate)
    job_embeddings = np.load(index_dir / 'job_embeddings.npy')
    
    # Load skill extraction function
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from extract_skills import extract_skills_from_text
    
    # Extract skills from query
    query_skills = set(extract_skills_from_text(query_text))
    
    results = []
    for rank, (idx, score) in enumerate(zip(I[0], D[0]), 1):
        idx = int(idx)
        if idx >= len(metadata):
            continue
        
        meta = metadata[idx]
        
        # Use extracted skills from metadata
        job_skills = set(meta.get('extracted_skills', []))
        matched_skills = query_skills & job_skills
        
        results.append({
            'rank': rank,
            'job_id': meta.get('job_id'),
            'company_name': meta.get('company_name'),
            'position': meta.get('title'),
            'years_experience': meta.get('years_experience'),
            'location': meta.get('location'),
            'posted_date': meta.get('posted_date'),
            'category': None,  # Not in job metadata
            'skills_matched': sorted(list(matched_skills)),  # Use extracted skills
            'score': float(score),
            'method': 'faiss'
        })
    
    return results


def main():
    parser = argparse.ArgumentParser(description='Search jobs for a given resume')
    parser.add_argument('--resume-index', type=int, help='Resume index from the resume dataset')
    parser.add_argument('--resume-text', help='Direct resume text')
    parser.add_argument('--resume-csv', help='Path to resume CSV file')
    parser.add_argument('--row', type=int, help='Row index in resume CSV')
    parser.add_argument('--method', choices=['bm25', 'faiss', 'both'], default='both', 
                       help='Search method (default: both)')
    parser.add_argument('--topk', type=int, default=5, help='Number of results to return (default: 5)')
    parser.add_argument('--output', help='Output JSON file (optional)')
    
    args = parser.parse_args()
    
    # Load resume text
    try:
        resume_text = load_resume_text(
            resume_index=args.resume_index,
            resume_text=args.resume_text,
            resume_csv=args.resume_csv,
            row=args.row
        )
    except Exception as e:
        print(f'Error loading resume: {e}')
        return 1
    
    print(f'Resume text preview: {resume_text[:200]}...\n')
    
    # Perform search
    results = {}
    
    if args.method in ['bm25', 'both']:
        print('Searching with BM25...')
        try:
            bm25_results = search_bm25(resume_text, topk=args.topk)
            results['bm25'] = bm25_results
            
            print(f'\nBM25 Results (top {len(bm25_results)}):')
            for r in bm25_results:
                print(f"  {r['rank']}. {r['position']} at {r['company_name']}")
                print(f"     Job ID: {r['job_id']}, Exp: {r['years_experience']}, Location: {r.get('location', 'N/A')}")
                print(f"     Posted: {r.get('posted_date', 'N/A')}, Score: {r['score']:.4f}")
                print(f"     Skills matched: {', '.join(r['skills_matched'][:10])}")
        except Exception as e:
            print(f'BM25 search failed: {e}')
    
    if args.method in ['faiss', 'both']:
        print('\nSearching with FAISS...')
        try:
            faiss_results = search_faiss(resume_text, topk=args.topk)
            results['faiss'] = faiss_results
            
            print(f'\nFAISS Results (top {len(faiss_results)}):')
            for r in faiss_results:
                print(f"  {r['rank']}. {r['position']} at {r['company_name']}")
                print(f"     Job ID: {r['job_id']}, Exp: {r['years_experience']}, Location: {r.get('location', 'N/A')}")
                print(f"     Posted: {r.get('posted_date', 'N/A')}, Score: {r['score']:.4f}")
                print(f"     Skills matched: {', '.join(r['skills_matched'][:10])}")
        except Exception as e:
            print(f'FAISS search failed: {e}')
    
    # Save results
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)
        print(f'\nResults saved to {output_path}')
    
    return 0


if __name__ == '__main__':
    exit(main())
