#!/usr/bin/env python3
"""
Search candidates given a job using BM25 or FAISS.

Returns: candidate_id, name, email, skills_matched, years_experience, category

Usage:
  # Search using job index
  python3 scripts/search_candidates_for_job.py --job-index 0 --method faiss --topk 5
  
  # Search using job text
  python3 scripts/search_candidates_for_job.py --job-text "Python developer position" --method bm25 --topk 10
  
  # Search using job from CSV
  python3 scripts/search_candidates_for_job.py --job-csv outputs/jobs_augmented.csv --row 0 --method both --topk 5
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


def load_job_text(job_index=None, job_text=None, job_csv=None, row=None):
    """Load job text from index, direct text, or CSV."""
    if job_text:
        return job_text
    
    if job_index is not None:
        # Load from job CSV
        paths = [
            Path('outputs/jobs_augmented.csv'),
            Path('jobs_augmented.xlsx')
        ]
        for p in paths:
            if p.exists():
                try:
                    if str(p).endswith('.csv'):
                        df = pd.read_csv(p, low_memory=False)
                    else:
                        df = pd.read_excel(p, engine='openpyxl')
                    
                    if job_index >= len(df):
                        raise ValueError(f'Job index {job_index} out of range (max {len(df)-1})')
                    
                    # Get title + description
                    cols = {c.lower(): c for c in df.columns}
                    title_col = None
                    for c in ['title', 'job_title', 'jobtitle']:
                        if c in cols:
                            title_col = cols[c]
                            break
                    
                    desc_col = None
                    for c in ['description', 'job_description', 'details']:
                        if c in cols:
                            desc_col = cols[c]
                            break
                    
                    text_parts = []
                    if title_col and pd.notna(df.loc[job_index, title_col]):
                        text_parts.append(str(df.loc[job_index, title_col]))
                    if desc_col and pd.notna(df.loc[job_index, desc_col]):
                        text_parts.append(str(df.loc[job_index, desc_col]))
                    
                    return ' '.join(text_parts)
                except Exception as e:
                    continue
    
    if job_csv and row is not None:
        p = Path(job_csv)
        if not p.exists():
            raise FileNotFoundError(f'{p} not found')
        
        # Detect file type and use appropriate reader
        if p.suffix.lower() in ['.xlsx', '.xls']:
            df = pd.read_excel(p, engine='openpyxl' if p.suffix.lower() == '.xlsx' else None)
        elif str(p).endswith('.csv'):
            df = pd.read_csv(p, low_memory=False)
        else:
            df = pd.read_excel(p, engine='openpyxl')
        
        if row >= len(df):
            raise ValueError(f'Row {row} out of range (max {len(df)-1})')
        
        cols = {c.lower(): c for c in df.columns}
        title_col = None
        for c in ['title', 'job_title', 'jobtitle']:
            if c in cols:
                title_col = cols[c]
                break
        
        desc_col = None
        for c in ['description', 'job_description', 'details']:
            if c in cols:
                desc_col = cols[c]
                break
        
        text_parts = []
        if title_col and pd.notna(df.loc[row, title_col]):
            text_parts.append(str(df.loc[row, title_col]))
        if desc_col and pd.notna(df.loc[row, desc_col]):
            text_parts.append(str(df.loc[row, desc_col]))
        
        return ' '.join(text_parts)
    
    raise ValueError('Must provide --job-index, --job-text, or --job-csv with --row')


def search_bm25(query_text, topk=5):
    """Search candidates using BM25."""
    index_dir = Path('outputs/indexes')
    
    # Load BM25
    with open(index_dir / 'bm25_resumes.pkl', 'rb') as f:
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
    with open(index_dir / 'metadata_resumes.json', 'r') as f:
        metadata = json.load(f)
    
    # Load corpus tokens to compute skill overlap
    with open(index_dir / 'bm25_resumes_corpus_tokens.pkl', 'rb') as f:
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
        resume_skills = set(meta.get('extracted_skills', []))
        matched_skills = query_skills & resume_skills
        
        results.append({
            'rank': rank,
            'candidate_id': meta.get('ID') or meta.get('id'),
            'name': meta.get('Name'),
            'email': meta.get('Email'),
            'skills_matched': sorted(list(matched_skills)),  # Use extracted skills
            'years_experience': meta.get('Experience'),
            'category': meta.get('Category'),
            'score': float(scores[idx]),
            'method': 'bm25'
        })
    
    return results


def search_faiss(query_text, topk=5):
    """Search candidates using FAISS."""
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
    index = faiss.read_index(str(index_dir / 'faiss_resumes.index'))
    
    # Search
    D, I = index.search(query_emb, topk)
    
    # Load metadata
    with open(index_dir / 'metadata_resumes.json', 'r') as f:
        metadata = json.load(f)
    
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
        resume_skills = set(meta.get('extracted_skills', []))
        matched_skills = query_skills & resume_skills
        
        results.append({
            'rank': rank,
            'candidate_id': meta.get('ID') or meta.get('id'),
            'name': meta.get('Name'),
            'email': meta.get('Email'),
            'skills_matched': sorted(list(matched_skills)),  # Use extracted skills
            'years_experience': meta.get('Experience'),
            'category': meta.get('Category'),
            'score': float(score),
            'method': 'faiss'
        })
    
    return results


def main():
    parser = argparse.ArgumentParser(description='Search candidates for a given job')
    parser.add_argument('--job-index', type=int, help='Job index from the job dataset')
    parser.add_argument('--job-text', help='Direct job text (title + description)')
    parser.add_argument('--job-csv', help='Path to job CSV file')
    parser.add_argument('--row', type=int, help='Row index in job CSV')
    parser.add_argument('--method', choices=['bm25', 'faiss', 'both'], default='both', 
                       help='Search method (default: both)')
    parser.add_argument('--topk', type=int, default=5, help='Number of results to return (default: 5)')
    parser.add_argument('--output', help='Output JSON file (optional)')
    
    args = parser.parse_args()
    
    # Load job text
    try:
        job_text = load_job_text(
            job_index=args.job_index,
            job_text=args.job_text,
            job_csv=args.job_csv,
            row=args.row
        )
    except Exception as e:
        print(f'Error loading job: {e}')
        return 1
    
    print(f'Job text preview: {job_text[:200]}...\n')
    
    # Perform search
    results = {}
    
    if args.method in ['bm25', 'both']:
        print('Searching with BM25...')
        try:
            bm25_results = search_bm25(job_text, topk=args.topk)
            results['bm25'] = bm25_results
            
            print(f'\nBM25 Results (top {len(bm25_results)}):')
            for r in bm25_results:
                print(f"  {r['rank']}. {r['name']} ({r['email']})")
                print(f"     ID: {r['candidate_id']}, Category: {r['category']}, Exp: {r['years_experience']}, Score: {r['score']:.4f}")
                print(f"     Skills matched: {', '.join(r['skills_matched'][:10])}")
        except Exception as e:
            print(f'BM25 search failed: {e}')
    
    if args.method in ['faiss', 'both']:
        print('\nSearching with FAISS...')
        try:
            faiss_results = search_faiss(job_text, topk=args.topk)
            results['faiss'] = faiss_results
            
            print(f'\nFAISS Results (top {len(faiss_results)}):')
            for r in faiss_results:
                print(f"  {r['rank']}. {r['name']} ({r['email']})")
                print(f"     ID: {r['candidate_id']}, Category: {r['category']}, Exp: {r['years_experience']}, Score: {r['score']:.4f}")
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
