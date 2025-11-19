#!/usr/bin/env python3
"""
Index resumes and jobs into BM25 and FAISS with custom text fields and metadata.

Resume text fields indexed: `Resume_str` and `Category` (concatenated).
Resume metadata saved per document: `Experience`, `Name`, `Email` (or EmailID).

Job text fields indexed: `title` and `description` (concatenated).
Job metadata saved per document: `Experience` (years), `company_name`, `location`, `posted_date`.

Writes outputs to `outputs/indexes/`:
 - bm25_job.pkl, bm25_corpus_tokens.pkl
 - job_embeddings.npy, candidate_embeddings.npy
 - faiss_job.index (if faiss available)
 - metadata_jobs.json, metadata_candidates.json

Usage:
  python3 scripts/index_with_custom_metadata.py --resumes "/path/to/Resume.xlsx" --jobs "/path/to/jobs.xlsx"

If reading the provided XLSX fails, the script will try CSV fallbacks with same basename in the same folder or in `outputs/`.
"""
from pathlib import Path
import argparse
import pandas as pd
import numpy as np
import json
import pickle
import re


def read_any(path: Path):
    if not path.exists():
        raise FileNotFoundError(path)
    # prefer CSV for large files; if extension is xlsx try to read and fall back
    try:
        if str(path).lower().endswith('.csv'):
            return pd.read_csv(path)
        else:
            # try openpyxl engine first
            return pd.read_excel(path, engine='openpyxl')
    except Exception as e:
        # try CSV fallback with same name
        csv_equiv = path.with_suffix('.csv')
        if csv_equiv.exists():
            return pd.read_csv(csv_equiv)
        # try outputs folder
        out_csv = Path('outputs') / path.name
        if out_csv.exists():
            try:
                return pd.read_csv(out_csv)
            except Exception:
                pass
        raise


def simple_tokenize(text):
    if pd.isna(text) or text is None:
        return []
    s = str(text).lower()
    toks = re.findall(r"\w+", s)
    if toks:
        return toks
    split = [t.strip() for t in re.split(r"\s+", s) if t.strip()]
    split = [t for t in split if re.search(r"[a-z0-9]", t)]
    return split


def build_bm25_from_texts(job_texts, out_path):
    """Build BM25 index for jobs"""
    try:
        from rank_bm25 import BM25Okapi
    except Exception:
        raise RuntimeError("rank_bm25 is required; pip install rank_bm25")
    tokenized = [simple_tokenize(t) for t in job_texts]
    bm25 = BM25Okapi(tokenized)
    out_path.mkdir(parents=True, exist_ok=True)
    with open(out_path / 'bm25_job.pkl', 'wb') as f:
        pickle.dump(bm25, f)
    with open(out_path / 'bm25_corpus_tokens.pkl', 'wb') as f:
        pickle.dump(tokenized, f)
    print(f"✓ Built BM25 job index: {len(tokenized)} documents")
    return out_path


def build_bm25_resumes(resume_texts, out_path):
    """Build BM25 index for resumes"""
    try:
        from rank_bm25 import BM25Okapi
    except Exception:
        raise RuntimeError("rank_bm25 is required; pip install rank_bm25")
    tokenized = [simple_tokenize(t) for t in resume_texts]
    bm25 = BM25Okapi(tokenized)
    out_path.mkdir(parents=True, exist_ok=True)
    with open(out_path / 'bm25_resumes.pkl', 'wb') as f:
        pickle.dump(bm25, f)
    with open(out_path / 'bm25_resumes_corpus_tokens.pkl', 'wb') as f:
        pickle.dump(tokenized, f)
    print(f"✓ Built BM25 resume index: {len(tokenized)} documents")
    return out_path


def build_dense_faiss(job_texts, candidate_texts, out_path):
    """Build FAISS indexes for both jobs and resumes"""
    try:
        from sentence_transformers import SentenceTransformer
    except Exception:
        raise RuntimeError('sentence-transformers is required; pip install sentence-transformers')
    
    print("Encoding job texts...")
    model = SentenceTransformer('all-MiniLM-L6-v2')
    job_emb = model.encode(job_texts, show_progress_bar=True, convert_to_numpy=True)
    
    print("Encoding resume texts...")
    cand_emb = model.encode(candidate_texts, show_progress_bar=True, convert_to_numpy=True)
    
    np.save(out_path / 'job_embeddings.npy', job_emb)
    np.save(out_path / 'candidate_embeddings.npy', cand_emb)
    print(f"✓ Saved embeddings: {job_emb.shape[0]} jobs, {cand_emb.shape[0]} resumes")
    
    results = {}
    try:
        import faiss
        dim = job_emb.shape[1]
        
        # Build FAISS index for jobs
        job_emb_norm = job_emb.astype('float32')
        faiss.normalize_L2(job_emb_norm)
        job_index = faiss.IndexFlatIP(dim)
        job_index.add(job_emb_norm)
        faiss.write_index(job_index, str(out_path / 'faiss_job.index'))
        print(f"✓ Built FAISS job index: {job_emb.shape[0]} vectors × {dim} dims")
        results['faiss_job_index'] = str(out_path / 'faiss_job.index')
        
        # Build FAISS index for resumes
        cand_emb_norm = cand_emb.astype('float32')
        faiss.normalize_L2(cand_emb_norm)
        resume_index = faiss.IndexFlatIP(dim)
        resume_index.add(cand_emb_norm)
        faiss.write_index(resume_index, str(out_path / 'faiss_resumes.index'))
        print(f"✓ Built FAISS resume index: {cand_emb.shape[0]} vectors × {dim} dims")
        results['faiss_resume_index'] = str(out_path / 'faiss_resumes.index')
        
    except Exception as e:
        print(f"Warning: FAISS build failed: {e}")
        # ignore faiss failure but embeddings are saved
        pass
    return results


def save_metadata(resumes_meta, jobs_meta, out_path):
    """Save metadata for both resumes and jobs"""
    out_path.mkdir(parents=True, exist_ok=True)
    
    # Save candidate metadata (legacy name for compatibility)
    with open(out_path / 'metadata_candidates.json', 'w') as f:
        json.dump(resumes_meta, f, indent=2)
    print(f"✓ Saved metadata_candidates.json: {len(resumes_meta)} resumes")
    
    # Save resume metadata (for search scripts)
    with open(out_path / 'metadata_resumes.json', 'w') as f:
        json.dump(resumes_meta, f, indent=2)
    print(f"✓ Saved metadata_resumes.json: {len(resumes_meta)} resumes")
    
    # Save job metadata
    with open(out_path / 'metadata_jobs.json', 'w') as f:
        json.dump(jobs_meta, f, indent=2)
    print(f"✓ Saved metadata_jobs.json: {len(jobs_meta)} jobs")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--resumes', required=True)
    parser.add_argument('--jobs', required=True)
    parser.add_argument('--outdir', default=str(Path.cwd() / 'outputs' / 'indexes'))
    args = parser.parse_args()

    resumes_p = Path(args.resumes)
    jobs_p = Path(args.jobs)
    outp = Path(args.outdir)

    print('Reading resumes from', resumes_p)
    resumes = read_any(resumes_p)
    print('Reading jobs from', jobs_p)
    jobs = read_any(jobs_p)

    # Build resume text (Resume_str + Category)
    resume_text_col = None
    for c in ['Resume_str', 'Resume', 'resume_str', 'resume', 'text', 'resume_text']:
        if c in resumes.columns:
            resume_text_col = c
            break
    cat_col = None
    for c in ['Category', 'category']:
        if c in resumes.columns:
            cat_col = c
            break
    def make_resume_profile(r):
        parts = []
        if resume_text_col and pd.notna(r.get(resume_text_col)):
            parts.append(str(r.get(resume_text_col)))
        if cat_col and pd.notna(r.get(cat_col)):
            parts.append(str(r.get(cat_col)))
        return ' '.join(parts)

    resumes['__text_profile'] = resumes.apply(make_resume_profile, axis=1)

    # metadata for resumes: Experience, Name, Email/EmailID, Category, extracted_skills
    resumes_meta = []
    for i, r in resumes.reset_index().iterrows():
        meta = {
            'idx': int(i),
            'Experience': r.get('Experience') if 'Experience' in resumes.columns else (r.get('experience') if 'experience' in resumes.columns else None),
            'Name': r.get('Name') if 'Name' in resumes.columns else (r.get('name') if 'name' in resumes.columns else None),
            'Email': r.get('Email') if 'Email' in resumes.columns else (r.get('EmailID') if 'EmailID' in resumes.columns else (r.get('email') if 'email' in resumes.columns else None)),
            'Category': r.get('Category') if 'Category' in resumes.columns else (r.get('category') if 'category' in resumes.columns else (r.get('domain') if 'domain' in resumes.columns else None)),
            'ID': r.get('ID') if 'ID' in resumes.columns else (r.get('id') if 'id' in resumes.columns else None)
        }
        # Add extracted skills if available
        if 'extracted_skills_json' in resumes.columns and pd.notna(r.get('extracted_skills_json')):
            try:
                meta['extracted_skills'] = json.loads(r.get('extracted_skills_json'))
            except:
                meta['extracted_skills'] = []
        elif 'extracted_skills' in resumes.columns and pd.notna(r.get('extracted_skills')):
            # Handle if it's already a list
            skills = r.get('extracted_skills')
            if isinstance(skills, str):
                try:
                    meta['extracted_skills'] = json.loads(skills)
                except:
                    meta['extracted_skills'] = []
            else:
                meta['extracted_skills'] = skills if isinstance(skills, list) else []
        else:
            meta['extracted_skills'] = []
        resumes_meta.append(meta)

    # Build job text (title + description)
    title_col = None
    for c in ['title', 'Title', 'job_title', 'jobtitle']:
        if c in jobs.columns:
            title_col = c
            break
    desc_col = None
    for c in ['description', 'Description', 'job_description', 'details']:
        if c in jobs.columns:
            desc_col = c
            break

    def make_job_profile(r):
        parts = []
        if title_col and pd.notna(r.get(title_col)):
            parts.append(str(r.get(title_col)))
        if desc_col and pd.notna(r.get(desc_col)):
            parts.append(str(r.get(desc_col)))
        return ' '.join(parts)

    jobs['__text_profile'] = jobs.apply(make_job_profile, axis=1)

    # metadata for jobs: job_id, title, experience, company_name, location, posted_date, extracted_skills
    jobs_meta = []
    for i, r in jobs.reset_index().iterrows():
        # Handle both uppercase and lowercase column names
        meta = {
            'idx': int(i),
            'job_id': r.get('job_id') if 'job_id' in jobs.columns else (r.get('Job_id') if 'Job_id' in jobs.columns else r.get('ID')),
            'title': r.get('title') if 'title' in jobs.columns else (r.get('Title') if 'Title' in jobs.columns else None),
            'years_experience': r.get('experience') if 'experience' in jobs.columns else (r.get('Experience') if 'Experience' in jobs.columns else None),
            'company_name': r.get('company_name') if 'company_name' in jobs.columns else (r.get('Company') if 'Company' in jobs.columns else None),
            'location': r.get('location') if 'location' in jobs.columns else (r.get('Location') if 'Location' in jobs.columns else None),
            'posted_date': str(r.get('posted_date')) if 'posted_date' in jobs.columns else (str(r.get('Posted_date')) if 'Posted_date' in jobs.columns else None)
        }
        # Add extracted skills if available
        if 'extracted_skills_json' in jobs.columns and pd.notna(r.get('extracted_skills_json')):
            try:
                meta['extracted_skills'] = json.loads(r.get('extracted_skills_json'))
            except:
                meta['extracted_skills'] = []
        elif 'extracted_skills' in jobs.columns and pd.notna(r.get('extracted_skills')):
            # Handle if it's already a list
            skills = r.get('extracted_skills')
            if isinstance(skills, str):
                try:
                    meta['extracted_skills'] = json.loads(skills)
                except:
                    meta['extracted_skills'] = []
            else:
                meta['extracted_skills'] = skills if isinstance(skills, list) else []
        else:
            meta['extracted_skills'] = []
        jobs_meta.append(meta)

    # prepare text lists
    resume_texts = resumes['__text_profile'].astype(str).tolist()
    job_texts = jobs['__text_profile'].astype(str).tolist()

    print('\n' + '='*60)
    print('BUILDING INDEXES')
    print('='*60)
    
    # build BM25 for jobs
    print('\n1. Building BM25 index for jobs...')
    try:
        build_bm25_from_texts(job_texts, outp)
    except Exception as e:
        print(f'✗ BM25 job build failed: {e}')

    # build BM25 for resumes
    print('\n2. Building BM25 index for resumes...')
    try:
        build_bm25_resumes(resume_texts, outp)
    except Exception as e:
        print(f'✗ BM25 resume build failed: {e}')

    # build dense embeddings + FAISS for both
    print('\n3. Building dense embeddings and FAISS indexes...')
    try:
        res = build_dense_faiss(job_texts, resume_texts, outp)
        if res:
            print(f'✓ FAISS indexes created successfully')
    except Exception as e:
        print(f'✗ Dense build failed: {e}')

    # save metadata
    print('\n4. Saving metadata...')
    save_metadata(resumes_meta, jobs_meta, outp)
    
    print('\n' + '='*60)
    print('INDEXING COMPLETE')
    print('='*60)
    print(f'\n✓ Output directory: {outp}')
    print(f'✓ Resumes indexed: {len(resume_texts)}')
    print(f'✓ Jobs indexed: {len(job_texts)}')
    print('\nFiles created:')
    if outp.exists():
        for file in sorted(outp.iterdir()):
            size = file.stat().st_size
            if size > 1024*1024:
                size_str = f"{size/(1024*1024):.1f} MB"
            elif size > 1024:
                size_str = f"{size/1024:.1f} KB"
            else:
                size_str = f"{size} bytes"
            print(f"  - {file.name:40s} {size_str:>10s}")
    print()


if __name__ == '__main__':
    main()
