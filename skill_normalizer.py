# skill_normalizer.py
from __future__ import annotations
import re, threading
from typing import Dict, List
from sentence_transformers import SentenceTransformer, util
import torch

# light & fast general-purpose model
model = SentenceTransformer("all-MiniLM-L6-v2")

# canonical -> embedding tensor (shared cache)
_vectors: Dict[str, "torch.Tensor"] = {}
_lock = threading.RLock()                 # <— protect _vectors

_sep_re = re.compile(r"[\s\-_\/]+")

def _clean(s: str) -> str:
    s = (s or "").strip().lower()
    s = _sep_re.sub(" ", s)
    return s

def normalize_skill(raw: str, threshold: float = 0.85) -> str:
    cleaned = _clean(raw)
    if not cleaned:
        return ""

    # encode can be done outside the lock
    vec = model.encode(cleaned, convert_to_tensor=True)

    # read snapshot safely
    with _lock:
        items = list(_vectors.items())

    # similarity check against snapshot
    best = None
    best_sim = -1.0
    for canon, v in items:
        sim = util.cos_sim(vec, v).item()
        if sim > best_sim:
            best_sim, best = sim, canon
        if sim > threshold:
            return canon

    # if no existing match, add cleaned as new canonical
    with _lock:
        # double-check if another thread just added a near-duplicate
        for canon, v in _vectors.items():
            if util.cos_sim(vec, v).item() > threshold:
                return canon
        _vectors[cleaned] = vec
    return cleaned

def normalize_list(raw_terms: List[str], threshold: float = 0.85) -> List[str]:
    seen = set()
    out: List[str] = []
    for r in raw_terms or []:
        canon = normalize_skill(r, threshold=threshold)
        if canon and canon not in seen:
            seen.add(canon)
            out.append(canon)
    return out
