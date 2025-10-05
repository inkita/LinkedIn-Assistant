import pandas as pd

def parse_jobs(csv_path):
    df = pd.read_csv(csv_path)
    jobs = []
    for _, row in df.iterrows():
        jobs.append({
            "title": row.get("Title"),
            "company": row.get("Company"),
            "description": row.get("Description", "")
        })
    return jobs
