"""Base embedding provider contract and vector mathematics."""

from abc import ABC, abstractmethod
import math
from typing import List


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Compute cosine similarity between two float vectors in pure Python."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot / (norm1 * norm2)


class BaseEmbeddingProvider(ABC):
    """Abstract interface for embedding generation."""

    model_name: str
    dimension: int

    @abstractmethod
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate embedding vectors for a list of input texts."""
        pass

    def embed_text(self, text: str) -> List[float]:
        """Convenience method to embed a single string."""
        results = self.embed_texts([text])
        return results[0] if results else [0.0] * self.dimension
