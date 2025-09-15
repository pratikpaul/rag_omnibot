# omnibot/agents/benefits_iq.py
from __future__ import annotations
import asyncio
import threading
from typing import List, Tuple, Sequence, Dict, Any, Optional, AsyncIterator

from langchain_chroma import Chroma
from langchain.prompts import ChatPromptTemplate
from langchain_ollama import OllamaLLM
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langchain_core.output_parsers import StrOutputParser

from omnibot.embeddings.openai_embedder import get_embedding_function
from omnibot.config.constants import (
    PDF_CHROMA_DIR, PDF_TOP_K, MAX_CHUNK_CHARS, HISTORY_TURNS, PDF_LLM_MODEL
)
from omnibot.config.prompts import BENEFITS_TEMPLATE
from .protocols import AnswerAgent
import os


class BenefitsIQ(AnswerAgent):
    """
    Implements AnswerAgent protocol:
      - retrieve(question) -> (context_str, citations)
      - astream_answer(question, history_messages, context?) -> async token stream
      - count()
    """

    def __init__(
        self,
        chroma_path: str = PDF_CHROMA_DIR,
        k: int = PDF_TOP_K,
        max_chunk_chars: int = MAX_CHUNK_CHARS,
        history_turns: int = HISTORY_TURNS,
        model_name: str = PDF_LLM_MODEL,
        llm_kwargs: Dict[str, Any] | None = None,
    ):
        self.chroma_path = chroma_path
        self.k = int(k)
        self.max_chunk_chars = int(max_chunk_chars)
        self.history_turns = int(history_turns)

        # Vector store
        self.embeddings = get_embedding_function()
        self.db = Chroma(persist_directory=self.chroma_path, embedding_function=self.embeddings)

        # LLM + prompt
        kwargs = dict(num_predict=256, temperature=0.2, keep_alive="10m")
        if llm_kwargs:
            kwargs.update(llm_kwargs)
        self.llm = OllamaLLM(model=model_name, **kwargs)
        # base_url = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
        # self.llm = OllamaLLM(model=model_name, base_url=base_url, **kwargs)
        self.prompt = ChatPromptTemplate.from_template(BENEFITS_TEMPLATE)
        self.parser = StrOutputParser()
        self.chain = self.prompt | self.llm | self.parser  # supports .stream(...); some builds also support .astream(...)

    # --------- Protocol: Retrieval ----------
    def retrieve(self, question: str) -> tuple[str, List[Dict[str, Any]]]:
        """
        Return a compact context string and citations for the given question.
        """
        results = self.db.similarity_search_with_score(question, k=self.k)
        context_chunks: List[str] = []
        citations: List[Dict[str, Any]] = []
        for doc, score in results:
            text = (doc.page_content or "")[: self.max_chunk_chars]
            context_chunks.append(text)
            md = doc.metadata or {}
            citations.append(
                {
                    "id": md.get("id"),
                    "source": md.get("source"),
                    "page": md.get("page"),
                    "score": float(score),
                }
            )
        context_text = "\n\n---\n\n".join(context_chunks)
        return context_text, citations

    # --------- Protocol: Stream answer (async) ----------
    # async def astream_answer(
    #     self,
    #     question: str,
    #     history_messages: Sequence[BaseMessage],
    #     context: Optional[str] = None,
    # ) -> AsyncIterator[str]:
    #     """
    #     If context is None, do internal retrieval first; otherwise, generate with given context.
    #     Streams tokens asynchronously. Falls back to a background thread if .astream is unavailable.
    #     """
    #     if context is None:
    #         context, _ = self.retrieve(question)
    #
    #     history_block = self.history_from_messages(history_messages)
    #     if not context.strip():
    #         yield "I couldn't find that in the provided documents."
    #         return
    #
    #     payload = {"context": context, "history": history_block, "question": question}
    #
    #     # Prefer native async if available (newer LangChain/Ollama builds)
    #     if hasattr(self.chain, "astream"):
    #         async for tok in self.chain.astream(payload):
    #             yield tok
    #         return
    #
    #     # Fallback: run .stream(...) in a background thread and bridge via an asyncio.Queue
    #     loop = asyncio.get_running_loop()
    #     queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
    #
    #     def producer():
    #         try:
    #             for chunk in self.chain.stream(payload):
    #                 asyncio.run_coroutine_threadsafe(queue.put(chunk), loop)
    #         finally:
    #             asyncio.run_coroutine_threadsafe(queue.put(None), loop)
    #
    #     threading.Thread(target=producer, daemon=True).start()
    #
    #     while True:
    #         item = await queue.get()
    #         if item is None:
    #             break
    #         yield item

    async def astream_answer(
            self,
            query: str,
            history_messages: Sequence[BaseMessage],
            context: Optional[str] = None,
    ) -> AsyncIterator[str]:
        if context is None:
            context, _ = self.retrieve(query)

        history_block = self.history_from_messages(history_messages)
        if not context.strip():
            yield "I couldn't find any relevant information in the provided documents."
            return

        payload = {"context": context, "history": history_block, "question": query}

        # Prefer native async if available (newer LangChain/Ollama builds)
        if hasattr(self.chain, "astream"):
            async for tok in self.chain.astream(payload):
                yield tok
            return

        # ✅ Proper fallback: stream in a background thread and forward to async generator
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Optional[str]] = asyncio.Queue()

        def producer():
            try:
                for chunk in self.chain.stream(payload):
                    asyncio.run_coroutine_threadsafe(queue.put(chunk), loop)
            finally:
                # signal completion
                asyncio.run_coroutine_threadsafe(queue.put(None), loop)

        threading.Thread(target=producer, daemon=True).start()

        while True:
            item = await queue.get()
            if item is None:
                break
            yield item

    # --------- Helpers ----------
    def history_from_messages(self, messages: Sequence[BaseMessage]) -> str:
        """
        Build a short transcript from a sequence of messages.
        Keeps the last N pairs (most recent first).
        """
        pairs: List[Tuple[str, str]] = []
        last_user: Optional[str] = None
        for m in messages:
            if isinstance(m, HumanMessage):
                last_user = m.content if isinstance(m.content, str) else str(m.content)
            elif isinstance(m, AIMessage) and last_user is not None:
                pairs.append((last_user, m.content if isinstance(m.content, str) else str(m.content)))
                last_user = None
        recent = pairs[-self.history_turns :]
        lines = [f"User: {u}\nAssistant: {a}" for u, a in reversed(recent)]
        return "\n\n".join(lines) if lines else "(none)"

    # --------- Protocol: Stats ----------
    def count(self) -> int:
        try:
            return int(self.db._collection.count())
        except Exception:
            return -1
