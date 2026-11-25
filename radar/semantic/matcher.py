"""Profile pillar management and semantic similarity scoring engine."""

import hashlib
import re
import sqlite3
from typing import Dict, List, Optional, Tuple

from radar.db import (
    delete_profile_embeddings,
    get_profile_embedding_hashes,
    get_profile_embeddings,
    requeue_embeddings,
    save_profile_embedding,
)
from radar.semantic.base import BaseEmbeddingProvider, cosine_similarity


DEFAULT_CATEGORY = "General Systems"


def slugify_pillar(name: str) -> str:
    """Normalize pillar name to safe tag identifier."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return f"semantic:{slug[:30]}"


def build_pillar_text(pillar: dict) -> str:
    """Construct dense descriptive text for a candidate domain pillar."""
    category = pillar.get("category") or DEFAULT_CATEGORY
    desc = pillar.get("description", "")
    keywords = ", ".join(pillar.get("keywords", []))
    return f"{category}. {desc} Key domains: {keywords}"


def ensure_profile_embeddings(
    conn: sqlite3.Connection,
    profile: dict,
    provider: BaseEmbeddingProvider,
    force: bool = False,
) -> Dict[str, List[float]]:
    """Return reference embeddings for exactly the profile's current domain pillars.

    Cached vectors are reused only when the pillar text is unchanged. Removed pillars are
    deleted, and any change re-queues all jobs so stored semantic bonuses follow the profile.
    """
    cached = get_profile_embeddings(conn, provider.model_name)
    hashes = get_profile_embedding_hashes(conn, provider.model_name)

    current = {}  # category -> (pillar text, hash)
    for p in profile.get("deep_domain_expertise") or []:
        text = build_pillar_text(p)
        current[p.get("category") or DEFAULT_CATEGORY] = (text, hashlib.sha1(text.encode()).hexdigest())

    stale = [name for name in cached if name not in current]
    changed = [c for c, (_, h) in current.items() if force or c not in cached or hashes.get(c) != h]

    if stale:
        delete_profile_embeddings(conn, stale)
    if changed:
        vectors = provider.embed_texts([current[c][0] for c in changed])
        for cat, vec in zip(changed, vectors):
            save_profile_embedding(conn, cat, provider.model_name, vec, current[cat][1])
            cached[cat] = vec
    if stale or changed:
        requeue_embeddings(conn)

    return {c: cached[c] for c in current}


def evaluate_semantic_match(
    job_vector: List[float],
    profile_embeddings: Dict[str, List[float]],
    is_dense_model: bool = True,
) -> Tuple[Optional[str], float, int, Optional[str]]:
    """Find highest matching profile pillar and calculate semantic score bonus.
    
    Returns:
        (best_pillar_name, similarity, score_bonus, semantic_tag)
    """
    if not profile_embeddings or not job_vector:
        return None, 0.0, 0, None

    best_pillar = None
    best_sim = -1.0

    for pillar_name, p_vec in profile_embeddings.items():
        sim = cosine_similarity(job_vector, p_vec)
        if sim > best_sim:
            best_sim = sim
            best_pillar = pillar_name

    # Determine thresholds based on model type
    min_threshold = 0.65 if is_dense_model else 0.15
    max_threshold = 0.90 if is_dense_model else 0.40

    if best_sim < min_threshold or not best_pillar:
        return best_pillar, max(0.0, best_sim), 0, None

    # Linear scale from min_threshold to max_threshold mapped to 5..30 bonus points
    ratio = min(1.0, max(0.0, (best_sim - min_threshold) / (max_threshold - min_threshold)))
    bonus = int(5 + ratio * 25)
    tag = slugify_pillar(best_pillar)

    return best_pillar, best_sim, bonus, tag
