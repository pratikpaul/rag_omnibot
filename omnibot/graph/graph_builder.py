# from __future__ import annotations
# import time, asyncio
# from typing import List
#
# from langgraph.graph import StateGraph, START, END
# from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
# import aiosqlite
# from langchain_core.messages import HumanMessage, AIMessage
#
# from omnibot.agents.benefits_iq import BenefitsIQ
# from omnibot.agents.claims_assist import ClaimsAssist
# from omnibot.agents.protocols import AnswerAgent
# from omnibot.router.router import fast_route
# from omnibot.config.constants import CHECKPOINT_DB
# from omnibot.graph.state import AgentState
#
# # Instantiate agents once per process
# pdf_core: AnswerAgent = BenefitsIQ()
# claims_core: AnswerAgent = ClaimsAssist()
# # PDF_AGENT: AnswerAgent = BenefitsIQ()
# # CLAIMS_AGENT: AnswerAgent = ClaimsAssist()
#
# async def router_node(state: AgentState) -> AgentState:
#     question = next((m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), "")
#     route = await fast_route(question or "")
#     return {"route": route}
#
# async def retrieve_pdf_node(state: AgentState) -> AgentState:
#     if state.get("route") not in ("pdf", "both"):
#         return {"context_pdf": "", "citations_pdf": []}
#     q = next((m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), "")
#     if not q:
#         return {"context_pdf": "", "citations_pdf": []}
#     ctx, cites = pdf_core.retrieve(q)
#     return {"context_pdf": ctx, "citations_pdf": cites}
#
# async def retrieve_claims_node(state: AgentState) -> AgentState:
#     if state.get("route") not in ("claims", "both"):
#         return {"context_claims": "", "citations_claims": []}
#     q = next((m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), "")
#     if not q:
#         return {"context_claims": "", "citations_claims": []}
#     ctx, cites = claims_core.retrieve_formatted(q)
#     return {"context_claims": ctx, "citations_claims": cites}
#
# async def _astream_pdf(question: str, history: str, context: str) -> str:
#     pieces: List[str] = []
#     if not context.strip():
#         msg = "(PDF: I couldn't find that in the provided documents.) "
#         print(msg, end="", flush=True)
#         return msg
#     async for chunk in pdf_core.chain.astream({"context": context, "history": history, "question": question}):
#         print(chunk, end="", flush=True)
#         pieces.append(chunk)
#     return "".join(pieces)
#
# async def _astream_claims(question: str, context: str) -> str:
#     pieces: List[str] = []
#     if not context.strip():
#         msg = "(CLAIMS: I don't know.) "
#         print(msg, end="", flush=True)
#         return msg
#     async for chunk in claims_core.astream_with_context(question=question, context=context):
#         print(chunk, end="", flush=True)
#         pieces.append(chunk)
#     return "".join(pieces)
#
# async def combine_node(state: AgentState) -> AgentState:
#     t0 = time.perf_counter()
#     q = next((m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), "")
#     if not q:
#         return {"messages": [AIMessage(content="(no question)")], "elapsed": 0.0}
#
#     route = state.get("route", "pdf")
#     history_block = pdf_core.history_from_messages(state["messages"])
#
#     tasks = []
#     if route in ("pdf", "both"):
#         print("\n[BenefitsIQ Agent] ", end="", flush=True)
#         tasks.append(asyncio.create_task(_astream_pdf(q, history_block, state.get("context_pdf", ""))))
#     if route in ("claims", "both"):
#         print("\n[Claims Agent] ", end="", flush=True)
#         tasks.append(asyncio.create_task(_astream_claims(q, state.get("context_claims", ""))))
#
#     if not tasks:
#         msg = "I couldn't determine a suitable source to answer that."
#         print(msg)
#         return {"messages": [AIMessage(content=msg)], "elapsed": time.perf_counter() - t0}
#
#     results = await asyncio.gather(*tasks)
#
#     if route == "both" and len(results) == 2:
#         combined = f"**From PDF:**\n{results[0]}\n\n**From Claims:**\n{results[1]}"
#     else:
#         combined = results[0]
#
#     return {"messages": [AIMessage(content=combined)], "elapsed": time.perf_counter() - t0}
#
# async def build_graph_async():
#     print("Building graph...")
#     graph = StateGraph(AgentState)
#     graph.add_node("router", router_node)
#     graph.add_node("retrieve_pdf", retrieve_pdf_node)
#     graph.add_node("retrieve_claims", retrieve_claims_node)
#     graph.add_node("combine", combine_node)
#
#
#     graph.add_edge(START, "router")
#     graph.add_edge("router", "retrieve_pdf")
#     graph.add_edge("router", "retrieve_claims")
#     graph.add_edge("retrieve_pdf", "combine")
#     graph.add_edge("retrieve_claims", "combine")
#     graph.add_edge("combine", END)
#
#
#     conn = await aiosqlite.connect(str(CHECKPOINT_DB))
#     checkpointer = AsyncSqliteSaver(conn)
#     return graph.compile(checkpointer=checkpointer), conn

# omnibot/graph/graph_builder.py
from __future__ import annotations
import time, asyncio
from typing import List, Sequence, Optional

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
import aiosqlite
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

from omnibot.agents.benefits_iq import BenefitsIQ
from omnibot.agents.claims_assist import ClaimsAssist
from omnibot.agents.protocols import AnswerAgent
from omnibot.router.router import fast_route
from omnibot.config.constants import CHECKPOINT_DB
from omnibot.graph.state import AgentState

# Instantiate agents once per process
pdf_core: AnswerAgent = BenefitsIQ()
claims_core: AnswerAgent = ClaimsAssist()

# ---------------- Nodes ----------------

async def router_node(state: AgentState): # -> AgentState:
    question = next((m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), "")
    route = await fast_route(question or "")
    # return {"route": route}
    yield {"route": route}
    return

async def retrieve_pdf_node(state: AgentState):# -> AgentState:
    if state.get("route") not in ("pdf", "both"):
        # return {"context_pdf": "", "citations_pdf": []}
        yield {"context_pdf": "", "citations_pdf": []}
        return
    q = next((m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), "")
    if not q:
        # return {"context_pdf": "", "citations_pdf": []}
        yield {"context_pdf": "", "citations_pdf": []}
        return
    ctx, cites = pdf_core.retrieve(q)
    # return {"context_pdf": ctx, "citations_pdf": cites}
    yield {"context_pdf": ctx, "citations_pdf": cites}
    return

async def retrieve_claims_node(state: AgentState):# -> AgentState:
    if state.get("route") not in ("claims", "both"):
        # return {"context_claims": "", "citations_claims": []}
        yield {"context_claims": "", "citations_claims": []}
        return
    q = next((m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), "")
    if not q:
        # return {"context_claims": "", "citations_claims": []}
        yield {"context_claims": "", "citations_claims": []}
        return
    # 🔁 protocol-compliant retrieval (replaces retrieve_formatted)
    ctx, cites = claims_core.retrieve(q)
    # return {"context_claims": ctx, "citations_claims": cites}
    yield {"context_claims": ctx, "citations_claims": cites}
    return
# -------- Generic agent streamer (protocol-based) --------
async def _astream_agent(
    agent: AnswerAgent,
    question: str,
    history_messages: Sequence[BaseMessage],
    context: Optional[str],
    prefix: str = ""
) -> str:
    pieces: List[str] = []
    # If context is empty/None, the agent will do internal retrieval per my protocol.
    async for chunk in agent.astream_answer(question, history_messages, context=context if context is not None else None):
        if prefix:
            # print the prefix once for readability
            print(prefix, end="", flush=True)
            prefix = ""  # only once
        print(chunk, end="", flush=True)
        pieces.append(chunk)
    return "".join(pieces) if pieces else ""

# async def combine_node(state: AgentState) -> AgentState:
#     t0 = time.perf_counter()
#     q = next((m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), "")
#     if not q:
#         return {"messages": [AIMessage(content="(no question)")], "elapsed": 0.0}
#
#     route = state.get("route", "pdf")
#     history_msgs: Sequence[BaseMessage] = state.get("messages", [])
#
#     tasks = []
#     if route in ("pdf", "both"):
#         tasks.append(asyncio.create_task(
#             _astream_agent(
#                 pdf_core,
#                 q,
#                 history_msgs,
#                 state.get("context_pdf", ""),          # avoid double retrieval if we have it
#                 prefix="\n[BenefitsIQ Agent] "
#             )
#         ))
#     if route in ("claims", "both"):
#         tasks.append(asyncio.create_task(
#             _astream_agent(
#                 claims_core,
#                 q,
#                 history_msgs,
#                 state.get("context_claims", ""),       # avoid double retrieval if we have it
#                 prefix="\n[Claims Agent] "
#             )
#         ))
#
#     if not tasks:
#         msg = "I couldn't determine a suitable source to answer that."
#         print(msg)
#         return {"messages": [AIMessage(content=msg)], "elapsed": time.perf_counter() - t0}
#
#     results = await asyncio.gather(*tasks)
#
#     if route == "both" and len(results) == 2:
#         combined = f"**From PDF:**\n{results[0]}\n\n**From Claims:**\n{results[1]}"
#     else:
#         combined = results[0]
#
#     return {"messages": [AIMessage(content=combined)], "elapsed": time.perf_counter() - t0}

# 

# BEFORE: async def combine_node(state: AgentState) -> AgentState:
# AFTER  : async def combine_node(state: AgentState):
# async def combine_node(state: AgentState):
#     t0 = time.perf_counter()
#     q = next((m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), "")
#     if not q:
#         # FINAL UPDATE then plain return
#         yield {"messages": [AIMessage(content="(no question)")], "elapsed": 0.0}
#         return
#
#     route = state.get("route", "pdf")
#     history_msgs: Sequence[BaseMessage] = state.get("messages", [])
#     ctx_pdf = state.get("context_pdf", "")
#     ctx_claims = state.get("context_claims", "")
#
#     # announce route so SSE can display it immediately
#     yield {"route": route}
#
#     if route not in ("pdf", "claims", "both"):
#         msg = "I couldn't determine a suitable source to answer that."
#         yield {"messages": [AIMessage(content=msg)], "elapsed": time.perf_counter() - t0}
#         return
#
#     import asyncio
#     queue: asyncio.Queue[dict] = asyncio.Queue()
#     results = {"pdf": [], "claims": []}
#     tasks = []
#
#     async def pump(name: str, agent: AnswerAgent, ctx: str):
#         async for tok in agent.astream_answer(q, history_msgs, context=ctx):
#             await queue.put({"agent": name, "token": tok})
#         await queue.put({"agent": name, "done": True})
#
#     if route in ("pdf", "both"):
#         tasks.append(asyncio.create_task(pump("pdf", pdf_core, ctx_pdf)))
#     if route in ("claims", "both"):
#         tasks.append(asyncio.create_task(pump("claims", claims_core, ctx_claims)))
#
#     if not tasks:
#         msg = "I couldn't determine a suitable source to answer that."
#         yield {"messages": [AIMessage(content=msg)], "elapsed": time.perf_counter() - t0}
#         return
#
#     done = 0
#     while done < len(tasks):
#         ev = await queue.get()
#         if "token" in ev:
#             # stream out token updates
#             agent_name = ev["agent"]
#             results[agent_name].append(ev["token"])
#             yield {"stream_event": ev}   # {agent: "pdf"/"claims", token: "..."}
#         elif ev.get("done"):
#             done += 1
#
#     # Build final message exactly like your working code
#     if route == "both" and len(tasks) == 2:
#         combined = f"**From PDF:**\n{''.join(results['pdf'])}\n\n**From Claims:**\n{''.join(results['claims'])}"
#     elif route == "pdf":
#         combined = "".join(results["pdf"])
#     else:
#         combined = "".join(results["claims"])
#
#     # FINAL UPDATE then plain return
#     yield {"messages": [AIMessage(content=combined)], "elapsed": time.perf_counter() - t0}
#     return

async def combine_node(state: AgentState):
    t0 = time.perf_counter()
    q = next((m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), "")
    if not q:
        yield {"messages": [AIMessage(content="(no question)")], "elapsed": 0.0}
        return

    route = state.get("route", "pdf")
    history_msgs: Sequence[BaseMessage] = state.get("messages", [])
    yield {"route": route}

    selected: list[tuple[str, AnswerAgent]] = []
    if route in ("pdf", "both"):
        selected.append(("pdf", pdf_core))
    if route in ("claims", "both"):
        selected.append(("claims", claims_core))

    if not selected:
        msg = "I couldn't determine a suitable source to answer that."
        yield {"messages": [AIMessage(content=msg)], "elapsed": time.perf_counter() - t0}
        return

    queue: asyncio.Queue[dict] = asyncio.Queue()
    results = {name: [] for name, _ in selected}

    async def run_agent(name: str, agent: AnswerAgent):
        # 1) retrieval — run in thread so we don't block the event loop
        loop = asyncio.get_running_loop()
        ctx, cites = await loop.run_in_executor(None, lambda: agent.retrieve(q))

        # 2) emit citations immediately
        if name == "pdf":
            await queue.put({"kind": "citations_pdf", "citations": cites})
        else:
            await queue.put({"kind": "citations_claims", "citations": cites})

        # 3) stream tokens
        async for tok in agent.astream_answer(q, history_msgs, context=ctx):
            await queue.put({"kind": "token", "agent": name, "token": tok})

        await queue.put({"kind": "done", "agent": name})

    tasks = [asyncio.create_task(run_agent(name, agent)) for name, agent in selected]

    done = 0
    while done < len(tasks):
        ev = await queue.get()
        k = ev["kind"]
        if k == "token":
            results[ev["agent"]].append(ev["token"])
            # forward as SSE "token"
            yield {"stream_event": {"agent": ev["agent"], "token": ev["token"]}}
        elif k == "citations_pdf":
            yield {"citations_pdf": ev["citations"]}
        elif k == "citations_claims":
            yield {"citations_claims": ev["citations"]}
        elif k == "done":
            done += 1

    # Final message
    if route == "both":
        combined = (
            f"**From PDF:**\n{''.join(results['pdf'])}\n\n"
            f"**From Claims:**\n{''.join(results['claims'])}"
        )
    elif route == "pdf":
        combined = "".join(results["pdf"])
    else:
        combined = "".join(results["claims"])

    yield {"messages": [AIMessage(content=combined)], "elapsed": time.perf_counter() - t0}
    return

# ---------------- Build/compile ----------------

async def build_graph_async():
    print("Building graph...")
    # graph = StateGraph(AgentState)
    # graph.add_node("router", router_node)
    # graph.add_node("retrieve_pdf", retrieve_pdf_node)
    # graph.add_node("retrieve_claims", retrieve_claims_node)
    # graph.add_node("combine", combine_node)
    #
    # graph.add_edge(START, "router")
    # graph.add_edge("router", "retrieve_pdf")
    # graph.add_edge("router", "retrieve_claims")
    # graph.add_edge("retrieve_pdf", "combine")
    # graph.add_edge("retrieve_claims", "combine")
    # graph.add_edge("combine", END)

    graph = StateGraph(AgentState)
    graph.add_node("router", router_node)
    graph.add_node("combine", combine_node)

    graph.add_edge(START, "router")
    graph.add_edge("router", "combine")
    graph.add_edge("combine", END)

    conn = await aiosqlite.connect(str(CHECKPOINT_DB))
    checkpointer = AsyncSqliteSaver(conn)
    return graph.compile(checkpointer=checkpointer), conn
