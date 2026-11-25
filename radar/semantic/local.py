"""100% Local, zero-dependency subword feature-hashed semantic vector provider."""

from collections import Counter
import hashlib
import math
import re
from typing import List

from radar.semantic.base import BaseEmbeddingProvider

STOP_WORDS = {
    "and", "the", "for", "with", "from", "this", "that", "our", "you", "your",
    "will", "have", "can", "all", "are", "about", "into", "more", "lead", "head",
    "senior", "staff", "junior", "principal", "manager", "director", "intern",
}


class LocalHashedEmbeddingProvider(BaseEmbeddingProvider):
    """Generates L2-normalized subword and n-gram feature-hashed dense vectors.
    
    Operates 100% locally in pure Python with zero network calls, zero C-extensions,
    and zero external library dependencies. Catches morphological variations, compound
    technical terms, and non-exact synonyms.
    """

    model_name = "local-subword-hash-384"
    dimension = 384

    def __init__(self, dimension: int = 384):
        self.dimension = dimension
        self.model_name = f"local-subword-hash-{dimension}"

    def _vectorize_single(self, text: str) -> List[float]:
        clean_text = text.lower()
        words = re.findall(r"[a-z0-9_\-\+\#]{2,}", clean_text)
        if not words:
            return [0.0] * self.dimension

        counts = Counter(words)
        tokens = []

        # 1. Unigram tokens with stopword filtering and sublinear TF weighting
        for w, count in counts.items():
            if w in STOP_WORDS:
                continue
            tf_weight = 1.0 + math.log(count)
            tokens.append((f"w:{w}", tf_weight * 3.0))

            # 2. Character 4-grams and 5-grams for morphological variations
            if len(w) >= 4:
                padded = f"<{w}>"
                for n in (4, 5):
                    for i in range(len(padded) - n + 1):
                        tokens.append((f"c:{padded[i:i+n]}", tf_weight * 0.2))

        # 3. Word bigrams for compound technical terms
        for i in range(len(words) - 1):
            w1, w2 = words[i], words[i + 1]
            if w1 not in STOP_WORDS and w2 not in STOP_WORDS:
                tokens.append((f"b:{w1}_{w2}", 2.0))

        # 4. Signed feature hashing projection
        vec = [0.0] * self.dimension
        for tok, weight in tokens:
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dimension
            sign = 1.0 if ((h >> 16) & 1) else -1.0
            vec[idx] += sign * weight

        # 5. L2 unit normalization
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0.0:
            return [x / norm for x in vec]
        return vec

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return [self._vectorize_single(t) for t in texts]
