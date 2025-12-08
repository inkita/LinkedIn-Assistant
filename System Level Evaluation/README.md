# LinkedIn-Assistant

This repository contains a compact end-to-end pipeline for extracting metadata and skills from resumes and job postings, building both sparse (BM25) and dense (FAISS using SentenceTransformers) indexes, and running search between candidates and jobs.

Key features

- Skill extraction (vocabulary-driven) for resumes and job descriptions; results saved to enriched CSVs.
- BM25 sparse ranking (rank_bm25) for keyword matches.
- Dense semantic search with FAISS + SentenceTransformers ('all-MiniLM-L6-v2'), using normalized embeddings and IndexFlatIP for cosine similarity.
- Metadata preservation: candidate ID/Category/Experience/Email and job Location/Posted_date are included in search outputs.
  
Repository layout (important files)

- `scripts/extract_skills.py` — extract skills from input Excel/CSV files and write enriched CSVs (adds `extracted_skills` and `extracted_skills_json`).
- `scripts/index_with_custom_metadata.py` — build BM25 and FAISS indexes for both resumes and jobs, and write metadata JSON files used by search scripts.
- `scripts/search_jobs_for_resume.py` — given a resume (row or CSV), return top-K job matches (BM25/FAISS/both).
- `scripts/search_candidates_for_job.py` — given a job (row, CSV, or free-text JD), return top-K candidate matches.
- `outputs/` — generated CSVs, index files, and metadata JSONs. Index files expected by search scripts are in `outputs/indexes/`.

Quick start (run locally)

1. (Recommended) create a virtual environment and activate it.

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Extract skills and build indexes for your files (example usage):

```bash
# extract skills from provided Excel files and write enriched CSVs to outputs/
python3 scripts/extract_skills.py --resumes Resume_200_samples.xlsx --jobs jobs_augmented.xlsx --out outputs

# build BM25 + FAISS indexes and metadata in outputs/indexes
python3 scripts/index_with_custom_metadata.py --resumes outputs/Resume_200_samples_with_skills.csv --jobs outputs/jobs_augmented_with_skills.csv --outdir outputs/indexes
```

4. Run a search (examples):

```bash
# Search jobs for a given resume (by row in Excel/CSV):
python3 scripts/search_jobs_for_resume.py --resume-csv resume_test_set.xlsx --row 0 --method both --topk 5

# Search candidates for a job posting (by row or by free-text):
python3 scripts/search_candidates_for_job.py --job-csv job_postings_test_set.xlsx --row 0 --method both --topk 10
# or free-text JD
python3 scripts/search_candidates_for_job.py --job-text "<paste job description here>" --method both --topk 10
```

