#!/usr/bin/env python3
"""
Add synthetic data to resumes and job postings.

Actions:
 - For resumes: if `Name` missing or empty, add synthetic names and `Email` addresses.
 - If `Email` missing, generate from `Name`.
 - For jobs: add a synthetic `posted_date` within the past year.

Writes outputs to `outputs/resumes_augmented.csv` and `outputs/jobs_augmented.csv` (and .xlsx versions).
"""
from pathlib import Path
import argparse
import pandas as pd
import numpy as np
import re


def synth_name_email(n):
    try:
        from faker import Faker
        fake = Faker()
        names = []
        emails = []
        for _ in range(n):
            name = fake.name()
            email = f"{re.sub(r'[^a-z0-9]+','.',name.lower()).strip('.')}@{fake.free_email_domain()}"
            names.append(name)
            emails.append(email)
        return names, emails
    except Exception:
        # fallback more realistic synthetic names/emails when faker not available
        # use small lists of common first/last names to create varied names
        firsts = ["Michael","David","James","John","Robert","Mary","Patricia","Jennifer","Linda","Elizabeth","Chris","Alex","Taylor","Jordan","Sam","Sara","Lisa","Karen","Emily","Daniel"]
        lasts = ["Smith","Johnson","Williams","Jones","Brown","Davis","Miller","Wilson","Moore","Taylor","Anderson","Thomas","Jackson","White","Harris","Martin","Thompson","Garcia","Martinez","Robinson"]
        names = []
        emails = []
        import random
        for i in range(n):
            f = random.choice(firsts)
            l = random.choice(lasts)
            # occasionally include a middle initial
            if random.random() < 0.25:
                mi = random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
                name = f"{f} {mi}. {l}"
            else:
                name = f"{f} {l}"
            # create a clean email
            email = re.sub(r'[^a-z0-9]+','.', name.lower()).strip('.') + f"{random.randint(1,99)}@example.com"
            names.append(name)
            emails.append(email)
        return names, emails


def add_posted_date(df, days_back=365):
    today = pd.Timestamp.now().normalize()
    rand_days = np.random.randint(0, days_back, size=len(df))
    df['posted_date'] = [(today - pd.Timedelta(int(d), 'D')).date().isoformat() for d in rand_days]
    return df


def extract_experience(text):
    """Extract number of years of experience from text.
    Returns an int (lower bound) or None if not found.
    Looks for patterns like '3-5 years', '3 to 5 years', '3+ years', '3 years'.
    """
    if text is None:
        return None
    s = str(text).lower()
    # range like '3-5 years' or '3 to 5 years'
    m = re.search(r"(\d{1,2})\s*(?:-|to|–)\s*(\d{1,2})\s*years?", s)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            pass
    # '3+ years' or '3 + years'
    m = re.search(r"(\d{1,2})\s*\+\s*years?", s)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            pass
    # simple '3 years'
    m = re.search(r"(\d{1,2})\s*years?", s)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            pass
    return None


def main(args):
    base = Path(__file__).resolve().parents[1]
    resumes_path = Path(args.resumes)
    jobs_path = Path(args.jobs)

    if not resumes_path.exists():
        print('Resumes file not found:', resumes_path)
        return
    if not jobs_path.exists():
        print('Jobs file not found:', jobs_path)
        return

    # read CSV or Excel depending on extension
    def read_any(p):
        if str(p).lower().endswith('.csv'):
            return pd.read_csv(p)
        else:
            return pd.read_excel(p)

    resumes = read_any(resumes_path)
    jobs = read_any(jobs_path)

    # --- Extract Experience for resumes ---
    # detect resume text column (common names)
    rcols = {c.lower(): c for c in resumes.columns}
    def find_rcol(cands):
        for c in cands:
            if c and c.lower() in rcols:
                return rcols[c.lower()]
        return None

    resume_text_col = find_rcol(['resume', 'resume_str', 'resume_text', 'text', 'content', 'resume_html'])
    # compute Experience for resumes using extract_experience on the text column
    if resume_text_col is not None:
        resumes['Experience'] = resumes[resume_text_col].fillna('').astype(str).apply(lambda t: extract_experience(t))
    else:
        # no obvious text column; add Experience column with None
        resumes['Experience'] = None
    # fill missing Experience with heuristics based on resume text (senior/manager/jr/intern)
    def _synth_resume_experience(text, median_val):
        t = (text or '').lower()
        if 'intern' in t:
            return 0
        if 'jr' in t or 'junior' in t or 'assistant' in t or 'entry' in t or 'associate' in t:
            return 1
        if 'senior' in t or '\bsr\b' in t or 'lead' in t:
            return 6
        if 'manager' in t or 'director' in t:
            return 4
        # default to median or 2
        return int(median_val) if median_val is not None else 2

    try:
        existing = pd.to_numeric(resumes['Experience'], errors='coerce').dropna()
        median_res_exp = int(existing.median()) if not existing.empty else None
    except Exception:
        median_res_exp = None

    if resume_text_col is not None:
        resumes['Experience'] = resumes.apply(lambda r: (_synth_resume_experience(r.get(resume_text_col,''), median_res_exp)
                                                         if pd.isna(r['Experience']) or r['Experience'] in (None,'','None')
                                                         else r['Experience']), axis=1)
    else:
        # fill all with median/default
        resumes['Experience'] = resumes['Experience'].apply(lambda v: int(median_res_exp) if (v is None or (isinstance(v, float) and np.isnan(v))) else v)

    # Resumes: add Name/Email if missing
    if 'Name' not in resumes.columns or resumes['Name'].isnull().all():
        names, emails = synth_name_email(len(resumes))
        resumes['Name'] = names
        resumes['Email'] = emails
    else:
        if 'Email' not in resumes.columns:
            resumes['Email'] = resumes['Name'].fillna('').apply(lambda n: re.sub(r"[^a-z0-9]+",'.', n.lower()).strip('.') + '@example.com')
        else:
            # fill missing emails for individual rows
            missing = resumes['Email'].isnull() | (resumes['Email'].astype(str).str.strip() == '')
            if missing.any():
                gen_n = missing.sum()
                names, emails = synth_name_email(gen_n)
                resumes.loc[missing, 'Email'] = emails

    # Jobs: add synthetic posted_date
    jobs = add_posted_date(jobs)

    # Normalize/identify job columns we care about
    cols = {c.lower(): c for c in jobs.columns}
    def find_col(cands):
        for c in cands:
            if c and c.lower() in cols:
                return cols[c.lower()]
        return None

    job_id_col = find_col(['job_id', 'id', 'jobid'])
    title_col = find_col(['title', 'job_title', 'jobtitle', 'position'])
    desc_col = find_col(['description', 'job_description', 'details', 'jobdetails', 'requirements'])
    loc_col = find_col(['location', 'city', 'job_location', 'work_location'])
    company_col = find_col(['company_name', 'company', 'employer'])

    # prepare cleaned DataFrame with only requested columns
    cleaned = jobs.copy()
    # ensure job_id exists
    if job_id_col is None:
        cleaned.insert(0, 'job_id', range(1, len(cleaned) + 1))
        job_id_col = 'job_id'

    # fill fallback columns
    cleaned['company_name'] = cleaned.get(company_col, '') if company_col else ''
    cleaned['title'] = cleaned.get(title_col, '') if title_col else ''
    cleaned['description'] = cleaned.get(desc_col, '') if desc_col else ''
    cleaned['location'] = cleaned.get(loc_col, '') if loc_col else ''

    # Experience: try to extract from description and title (prefer description)
    combined_for_exp = (cleaned['description'].fillna('') + ' ' + cleaned['title'].fillna(''))
    cleaned['Experience'] = combined_for_exp.apply(lambda t: extract_experience(t))

    # keep only requested columns (and Experience)
    out_cols = ['job_id', 'company_name', 'title', 'description', 'location', 'posted_date', 'Experience']
    for c in out_cols:
        if c not in cleaned.columns:
            cleaned[c] = ''

    cleaned = cleaned[out_cols]

    out_dir = Path(base) / 'outputs'
    out_dir.mkdir(exist_ok=True)
    # sanitize text columns to avoid illegal Excel characters
    def _sanitize_cell(v):
        if v is None:
            return ''
        s = str(v)
        # remove control characters that break openpyxl (except common whitespace)
        s = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f]', ' ', s)
        return s

    for c in ['description', 'title', 'company_name', 'location']:
        if c in cleaned.columns:
            cleaned[c] = cleaned[c].apply(_sanitize_cell)

    # drop rows where company_name is missing/empty
    cleaned['company_name'] = cleaned['company_name'].astype(str).str.strip()
    cleaned.loc[cleaned['company_name'] == '', 'company_name'] = None
    cleaned = cleaned.dropna(subset=['company_name']).reset_index(drop=True)

    # normalize and drop rows where company_name is empty or NaN
    cleaned['company_name'] = cleaned['company_name'].astype(str).fillna('').str.strip()
    cleaned['company_name'] = cleaned['company_name'].replace({'': np.nan, 'nan': np.nan, 'None': np.nan})
    before_count = len(cleaned)
    cleaned = cleaned.dropna(subset=['company_name'])
    after_count = len(cleaned)

    # fill missing Experience with simple heuristics + median fallback
    def _synth_experience(title, median_val):
        t = (title or '').lower()
        if 'intern' in t:
            return 0
        if 'jr' in t or 'junior' in t or 'assistant' in t or 'associate' in t or 'entry' in t:
            return 1
        if 'senior' in t or '\bsr\b' in t:
            return 6
        if 'lead' in t or 'manager' in t or 'director' in t:
            return 4
        # default
        return int(median_val) if median_val is not None else 2

    # compute median from existing numeric Experience
    try:
        existing = pd.to_numeric(cleaned['Experience'], errors='coerce').dropna()
        median_exp = int(existing.median()) if not existing.empty else None
    except Exception:
        median_exp = None

    # apply fill
    cleaned['Experience'] = cleaned.apply(lambda r: (_synth_experience(r.get('title',''), median_exp) if pd.isna(r['Experience']) or r['Experience'] in (None, '', 'None') else r['Experience']), axis=1)

    resumes.to_csv(out_dir / 'resumes_augmented.csv', index=False)
    # try to write Excel; sanitize via previously defined helper if necessary
    try:
        resumes.to_excel(out_dir / 'resumes_augmented.xlsx', index=False)
    except Exception:
        # attempt to sanitize text columns and retry
        text_cols = [c for c in resumes.columns if resumes[c].dtype == object]
        for c in text_cols:
            resumes[c] = resumes[c].apply(_sanitize_cell)
        try:
            resumes.to_excel(out_dir / 'resumes_augmented.xlsx', index=False)
        except Exception:
            print('Warning: writing resumes_augmented.xlsx failed; resumes_augmented.csv written instead')

    # optional: overwrite original resumes file if requested
    if getattr(args, 'overwrite_resumes', False):
        try:
            if str(resumes_path).lower().endswith('.csv'):
                resumes.to_csv(resumes_path, index=False)
            else:
                resumes.to_excel(resumes_path, index=False)
            print('Overwrote original resumes file at', resumes_path)
        except Exception as e:
            print('Warning: failed to overwrite original resumes file:', e)

    cleaned.to_csv(out_dir / 'jobs_augmented.csv', index=False)
    # write excel but avoid illegal characters
    try:
        cleaned.to_excel(out_dir / 'jobs_augmented.xlsx', index=False)
    except Exception:
        # fallback: write without Excel if it still fails
        print('Warning: writing jobs_augmented.xlsx failed; jobs_augmented.csv written instead')

    print('Wrote:', out_dir / 'resumes_augmented.csv', out_dir / 'jobs_augmented.csv')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--resumes', default=str(Path.cwd() / 'resume_test_set.xlsx'))
    parser.add_argument('--jobs', default=str(Path.cwd() / 'job_postings_test_set.xlsx'))
    parser.add_argument('--overwrite-resumes', action='store_true', dest='overwrite_resumes', help='If set, overwrite the original resumes input file with the augmented version')
    args = parser.parse_args()
    main(args)
