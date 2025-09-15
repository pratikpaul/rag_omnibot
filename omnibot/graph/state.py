from typing import TypedDict, Annotated, Sequence, List, Dict, Any

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    route: str
    context_pdf: str
    citations_pdf: List[Dict[str, Any]]
    context_claims: str
    citations_claims: List[Dict[str, Any]]
    elapsed: float