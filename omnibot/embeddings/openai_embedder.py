from __future__ import annotations

from langchain_openai import OpenAIEmbeddings

from omnibot.config.constants import EMBED_MODEL


def get_embedding_function(model: str | None = None) -> OpenAIEmbeddings:
   return OpenAIEmbeddings(model=model or EMBED_MODEL)