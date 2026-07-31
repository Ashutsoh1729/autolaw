"""Embedding service — vector embeddings via OpenRouter's OpenAI-compatible API.

Generates embeddings for corpus chunks using the configured OpenRouter
embedding model (default ``nvidia/nemotron-3-embed-1b:free``) with an
automatic fallback model (default ``qwen/qwen3-embedding-8b``), in-memory
LRU caching, and exponential backoff with jitter for rate limits.
"""

from __future__ import annotations

import hashlib
import logging
import random
import time
from collections import OrderedDict
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

# Nemotron-3-Embed-1B context window (tokens). Text longer than this is
# truncated before embedding with a warning.
DEFAULT_MAX_INPUT_TOKENS = 512

# Rough tokens-per-character heuristic for estimating token counts.
CHARS_PER_TOKEN = 4


class EmbeddingError(RuntimeError):
    """Raised when all embedding models fail."""


class EmbeddingService:
    """Embed text via OpenRouter with caching, fallback, and retry logic.

    The underlying OpenAI-compatible client is injectable so tests can pass
    a fake client instead of hitting the network.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        fallback_model: str | None = None,
        dimension: int | None = None,
        cache_size: int = 4096,
        max_retries: int = 5,
        base_delay: float = 1.0,
        max_input_tokens: int = DEFAULT_MAX_INPUT_TOKENS,
        client: Any | None = None,
    ) -> None:
        """Build an embedding service.

        ``client`` is an optional pre-built OpenAI-compatible client (used
        by tests to inject a fake); when omitted, a real ``OpenAI`` client
        pointed at OpenRouter is created from settings.
        """
        self.api_key = api_key if api_key is not None else settings.openrouter_api_key
        self.base_url = base_url or settings.embedding_base_url
        self.model = model or settings.embedding_model
        self.fallback_model = fallback_model or settings.embedding_fallback_model
        self.dimension = dimension or settings.embedding_dimension
        self._max_input_tokens = max_input_tokens
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self._cache_size = cache_size
        self._client = client  # optional injected client (tests); created lazily otherwise

    # ── Public API ────────────────────────────────────────────────────────

    def embed_dimension(self) -> int:
        """Return the configured embedding dimension."""
        return self.dimension

    def embed(self, text: str) -> list[float]:
        """Embed a single text string and return its vector."""
        vectors = self.embed_batch([text])
        return vectors[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts, returning one vector per input.

        Uses the in-memory LRU cache for repeated inputs and falls back to
        the secondary model if the primary model fails after retries.
        """
        if not texts:
            return []

        # Cache lookup for fully-cached inputs.
        keys = [self._cache_key(t) for t in texts]
        result: list[list[float] | None] = []
        missing: list[int] = []
        for i, key in enumerate(keys):
            cached = self._cache.get(key)
            if cached is not None:
                result.append(cached)
            else:
                result.append(None)
                missing.append(i)

        if missing:
            missing_texts = [self._truncate(texts[i]) for i in missing]
            vectors = self._embed_with_fallback(missing_texts)
            for idx, vector in zip(missing, vectors):
                result[idx] = vector
                self._cache_set(keys[idx], vector)

        return [v for v in result if v is not None]  # type: ignore[misc]

    # ── Internal helpers ──────────────────────────────────────────────────

    def _cache_key(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _cache_set(self, key: str, vector: list[float]) -> None:
        self._cache[key] = vector
        self._cache.move_to_end(key)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

    def _truncate(self, text: str) -> str:
        """Truncate text to the model's max token budget, with a warning."""
        if self._estimate_tokens(text) <= self._max_input_tokens:
            return text
        max_chars = self._max_input_tokens * CHARS_PER_TOKEN
        # Cut at the last whitespace before the budget for cleaner chunks.
        cut = text[:max_chars].rfind(" ")
        cut = cut if cut > 0 else max_chars
        logger.warning(
            "Truncating text for embedding: %d tokens exceeds model max of %d",
            self._estimate_tokens(text),
            self._max_input_tokens,
        )
        return text[:cut]

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough token estimate (~4 chars per token)."""
        return max(1, len(text) // CHARS_PER_TOKEN)

    def _embed_with_fallback(self, texts: list[str]) -> list[list[float]]:
        """Try the primary model, then the fallback, with backoff + jitter."""
        for attempt, model in enumerate(
            (self.model, self.fallback_model) if self.fallback_model else (self.model,)
        ):
            try:
                vectors = self._call_with_retry(texts, model)
                logger.info("Embedded %d texts with model %s", len(texts), model)
                return vectors
            except Exception as exc:  # noqa: BLE001 — any API failure triggers fallback
                logger.warning(
                    "Embedding model %s failed after %d retries: %s",
                    model,
                    self._max_retries,
                    exc,
                )
                if model == self.fallback_model or not self.fallback_model:
                    raise EmbeddingError(
                        f"All embedding models failed (last error: {exc})"
                    ) from exc
        raise EmbeddingError("No embedding models configured")  # pragma: no cover

    def _call_with_retry(self, texts: list[str], model: str) -> list[list[float]]:
        """Call the embeddings API with exponential backoff + jitter."""
        if self._client is None:
            from openai import OpenAI

            if not self.api_key:
                raise EmbeddingError(
                    "OpenRouter API key is not configured "
                    "(set AUTOLAW_OPENROUTER_API_KEY)"
                )
            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key)
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.embeddings.create(model=model, input=texts)
                data = sorted(response.data, key=lambda item: item.index)
                return [item.embedding for item in data]
            except Exception as exc:  # noqa: BLE001 — retry transient API errors
                last_exc = exc
                if attempt >= self._max_retries:
                    break
                delay = self._base_delay * (2**attempt) + random.uniform(0, 0.5)
                logger.warning(
                    "Embedding API error (attempt %d/%d) for %s: %s — retrying in %.2fs",
                    attempt + 1,
                    self._max_retries + 1,
                    model,
                    exc,
                    delay,
                )
                time.sleep(delay)
        raise last_exc  # type: ignore[misc]


def get_embedding_service() -> EmbeddingService:
    """Return a configured EmbeddingService (settings-driven)."""
    return EmbeddingService()
