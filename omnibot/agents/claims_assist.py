# from __future__ import annotations
# from typing import Optional, Sequence, AsyncIterator, List, Dict, Any
# from langchain_openai import ChatOpenAI
# from langchain_chroma import Chroma
# from langchain.prompts import ChatPromptTemplate
# from langchain_core.output_parsers import StrOutputParser
# from langchain_core.runnables import RunnablePassthrough
# from langchain_core.messages import BaseMessage
# from langchain_openai import ChatOpenAI, OpenAIEmbeddings
#
# from omnibot.embeddings.openai_embedder import get_embedding_function
# from omnibot.config.constants import CLAIMS_CHROMA_DIR, CLAIMS_TOP_K, CLAIMS_LLM_MODEL, EMBED_MODEL
# from omnibot.config.prompts import CLAIMS_ASSIST_SYSTEM
# from .protocols import AnswerAgent
#
# class ClaimsAssist:
#     """
#     Claims RAG built from:
#       - OpenAI embeddings ("text-embedding-3-small")
#       - Chroma persisted at CLAIMS_PERSIST_DIR
#       - retriever -> format_docs -> prompt -> ChatOpenAI -> StrOutputParser
#     """
#     def __init__(
#         self,
#         persist_dir: str = CLAIMS_CHROMA_DIR,
#         embed_model: str = EMBED_MODEL,
#         llm_model: str = CLAIMS_LLM_MODEL,
#         k: int = 4
#     ):
#         self.emb = OpenAIEmbeddings(model=embed_model)
#         self.db = Chroma(persist_directory=persist_dir, embedding_function=self.emb)
#         self.retriever = self.db.as_retriever(search_kwargs={"k": k})
#
#         def format_docs(docs):
#             return "\n\n".join(
#                 f"[{i+1}] {d.page_content}\n(SOURCE: {d.metadata.get('source', 'unknown')})"
#                 for i, d in enumerate(docs)
#             )
#
#         self._format_docs = format_docs
#
#         self.prompt = ChatPromptTemplate.from_messages([
#             ("system",
#              "You are a helpful claims assistant. Use the claims context to accurately answer the user's questions about their claims. When the user asks about specific claims, reference the claims data provided and intelligently determine how to extract or calculate the answer. You may be asked to list all claims, in which case return all claims found in the context. If asked for the latest claim, return the most recently created claim. You might also be asked to calculate totals such as the total out-of-pocket cost or other summary information—perform these calculations based on the claim details in the context. Always understand and evaluate the provided claims data thoroughly to give precise, clear, and complete responses."),
#             ("human", "Question: {question}\n\nContext:\n{context}")
#         ])
#
#         self.llm = ChatOpenAI(model=llm_model, temperature=0, streaming=True)
#         self.parser = StrOutputParser()
#
#         # Full RAG chain taking a plain question string
#         self.rag_chain = (
#             {
#                 "context": self.retriever | self._format_docs,
#                 "question": RunnablePassthrough(),
#             }
#             | self.prompt
#             | self.llm
#             | self.parser
#         )
#
#         # Also a prompt for generation when we already have context (to avoid double retrieval)
#         self.gen_prompt = self.prompt
#         self.gen_chain = self.gen_prompt | self.llm | self.parser
#
#     def retrieve_formatted(self, question: str) -> tuple[str, List[Dict[str, Any]]]:
#         """Return (formatted_context, citations) without generating an answer."""
#         docs = self.retriever.invoke(question)
#         context = self._format_docs(docs)
#         cites = [{"source": d.metadata.get("source", "unknown")} for d in docs]
#         return context, cites
#
#     async def astream_with_context(self, *, question: str, context: str):
#         """Stream answer tokens given a precomputed formatted context."""
#         if not context.strip():
#             yield "I don't know."
#             return
#         async for chunk in self.gen_chain.astream({"question": question, "context": context}):
#             yield chunk
#
#     async def astream_question(self, question: str):
#         """Stream answer tokens letting the chain do retrieval itself."""
#         async for chunk in self.rag_chain.astream(question):
#             yield chunk


# omnibot/agents/claims_assist.py
from __future__ import annotations
import asyncio
from typing import Optional, Sequence, AsyncIterator, List, Dict, Any
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_core.messages import BaseMessage

from omnibot.config.constants import CLAIMS_CHROMA_DIR, CLAIMS_TOP_K, CLAIMS_LLM_MODEL, EMBED_MODEL
from .protocols import AnswerAgent


class ClaimsAssist(AnswerAgent):
    """
    Implements the AnswerAgent protocol:
      - retrieve(question) -> (context_str, citations)
      - astream_answer(question, history_messages, context?) -> async token stream
      - count()
    """

    def __init__(
        self,
        persist_dir: str = CLAIMS_CHROMA_DIR,
        embed_model: str = EMBED_MODEL,
        llm_model: str = CLAIMS_LLM_MODEL,
        k: int = CLAIMS_TOP_K,
    ):
        self.emb = OpenAIEmbeddings(model=embed_model)
        self.db = Chroma(persist_directory=persist_dir, embedding_function=self.emb)
        self.retriever = self.db.as_retriever(search_kwargs={"k": int(k)})

        def format_docs(docs):
            return "\n\n".join(
                f"[{i+1}] {d.page_content}\n(SOURCE: {d.metadata.get('source', 'unknown')})"
                for i, d in enumerate(docs)
            )

        self._format_docs = format_docs

        self.prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are a helpful claims assistant. Use the claims context to answer precisely. "
             "Do simple totals or calculations from the context when obvious."),
            ("human", "Question: {question}\n\nContext:\n{context}")
        ])

        # streaming must be True to support astream_answer
        self.llm = ChatOpenAI(model=llm_model, temperature=0, streaming=True)
        self.parser = StrOutputParser()

        # RAG chain (does its own retrieval)
        self.rag_chain = (
            {
                "context": self.retriever | self._format_docs,
                "question": RunnablePassthrough(),
            }
            | self.prompt
            | self.llm
            | self.parser
        )

        # Generation chain (caller supplies context)
        self.gen_chain = self.prompt | self.llm | self.parser

    # ---- AnswerAgent: retrieve ----
    def retrieve(self, question: str) -> tuple[str, List[Dict[str, Any]]]:
        # sync API required by protocol
        docs = self.retriever.invoke(question)
        context = self._format_docs(docs)
        citations = []
        for d in docs:
            md = d.metadata or {}
            citations.append({
                "source": md.get("source", "unknown"),
                "page": md.get("page"),
                "id": md.get("id"),
            })
        return context, citations

    # ---- AnswerAgent: astream_answer ----
    async def astream_answer(
        self,
        question: str,
        history_messages: Sequence[BaseMessage],
        context: Optional[str] = None,
    ) -> AsyncIterator[str]:
        # We ignore history for now, but keep the arg for API parity.
        if context is None:
            # Let the chain handle retrieval internally
            async for chunk in self.rag_chain.astream(question):
                yield chunk
            return

        if not context.strip():
            yield "I couldn't find that in the provided claims."
            return

        async for chunk in self.gen_chain.astream({"question": question, "context": context}):
            yield chunk

    # ---- Optional utility ----
    def count(self) -> int:
        try:
            return int(self.db._collection.count())
        except Exception:
            return -1
