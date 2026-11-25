"""Profile pillar management and semantic similarity scoring engine."""

import re
import sqlite3
from typing import Dict, List, Optional, Tuple

from radar.db import get_profile_embeddings, save_profile_embedding
from radar.semantic.base import BaseEmbeddingProvider, cosine_similarity


def slugify_pillar(name: str) -> str:
    """Normalize pillar name to safe tag identifier."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return f"semantic:{slug[:30]}"


def build_pillar_text(pillar: dict) -> str:
    """Construct dense descriptive text for a candidate domain pillar."""
    category = pillar.get("category", "")
    desc = pillar.get("description", "")
    keywords = ", ".join(pillar.get("keywords", []))
    return f"{category}. {desc} Key domains: {keywords}"


def ensure_profile_embeddings(
    conn: sqlite3.Connection,
    profile: dict,
    provider: BaseEmbeddingProvider,
    force: bool = False,
) -> Dict[str, List[float]]:
    """Retrieve or compute reference embeddings for all profile domain pillars."""
    cached = get_profile_embeddings(conn, provider.model_name)
    pillars = profile.get("deep_domain_expertise", [])
    if not pillars:
        return cached

    missing_pillars = []
    for p in pillars:
        cat = p.get("category")
        if force or cat not in cached:
            missing_pillars.append(p)

    if not missing_pillars:
        return cached

    texts = [build_pillar_text(p) for p in missing_pillars]
    vectors = provider.embed_texts(texts)

    for p, vec in zip(missing_pillars, vectors):
        cat = p.get("category", "General Systems")
        save_profile_embedding(conn, cat, provider.model_name, vec)
        cached[cat] = vec

    return cached


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
