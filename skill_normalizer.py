# skill_normalizer.py
import re
from sentence_transformers import SentenceTransformer, util

model = SentenceTransformer('all-MiniLM-L6-v2')
skill_vectors = {}  # {canonical: tensor}

def _clean(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[\s\-_/]+", " ", s)  # normalize separators
    return s

def normalize_skill(raw: str, threshold: float = 0.85) -> str:
    raw = raw or ""
    cleaned = _clean(raw)
    if not cleaned:
        return ""
    vec = model.encode(cleaned, convert_to_tensor=True)
    for canon, v in skill_vectors.items():
        if util.cos_sim(vec, v).item() > threshold:
            # print(f"Dedup: '{raw}' -> '{canon}'")
            return canon
    skill_vectors[cleaned] = vec
    # print(f"New skill canonicalized: '{raw}' -> '{cleaned}'")
    return cleaned
