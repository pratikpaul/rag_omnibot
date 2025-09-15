"""Embedding factories (OpenAI by default)."""

from .openai_embedder import get_embedding_function

__all__ = ["get_embedding_function"]