"""100% Local semantic vector search and embedding subsystem."""

from typing import Optional

from radar.semantic.base import BaseEmbeddingProvider, cosine_similarity
from radar.semantic.local import LocalHashedEmbeddingProvider
from radar.semantic.matcher import (
    ensure_profile_embeddings,
    evaluate_semantic_match,
    slugify_pillar,
)

__all__ = [
    "BaseEmbeddingProvider",
    "LocalHashedEmbeddingProvider",
    "cosine_similarity",
    "ensure_profile_embeddings",
    "evaluate_semantic_match",
    "get_embedding_provider",
    "slugify_pillar",
]


def get_embedding_provider(
    provider_name: Optional[str] = None,
) -> BaseEmbeddingProvider:
    """Instantiate the local offline embedding provider.
    
    Operates 100% locally with zero external network or API dependencies,
    and zero external library requirements.
    """
    return LocalHashedEmbeddingProvider(dimension=384)
