from __future__ import annotations
from typing import Protocol, Sequence, Dict, Any, List, Optional, AsyncIterator, runtime_checkable
from langchain_core.messages import BaseMessage

@runtime_checkable
class AnswerAgent(Protocol):
    def retrieve(self, question: str) -> tuple[str, List[Dict[str, Any]]]:
        """Return (context_str, citations)."""
        ...


    async def astream_answer(
    self,
    question: str,
    history_messages: Sequence[BaseMessage],
    context: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """Yield answer tokens. If context is None, do internal retrieval."""
        ...

    def count(self) -> int: # optional utility
        ...