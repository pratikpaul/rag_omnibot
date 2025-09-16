# omnibot/api/server.py

from __future__ import annotations
import json, uuid, asyncio
import re
from dataclasses import dataclass
from typing import Optional, AsyncIterator

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

from omnibot.graph.graph_builder import build_graph_async
from omnibot.guardrails.intent_semantic import IntentClassifier, IntentConfig
from omnibot.guardrails.messages import guardrail_reply
from omnibot.router.router import fast_route
from omnibot.agents.benefits_iq import BenefitsIQ
from omnibot.agents.claims_assist import ClaimsAssist
from omnibot.agents.protocols import AnswerAgent

from fastapi.staticfiles import StaticFiles
import os

app = FastAPI(title="Omnibot API (Graph + SSE)")

# if os.path.isdir("web/dist"):
#     app.mount("/", StaticFiles(directory="web/dist", html=True), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#-----------Greetings detector-----------
@dataclass
class MemberProfile:
    name: str
    first: str  

_GREET = re.compile(r"^\s*(hi|hello|hey|greetings|good (morning|afternoon|evening))\b", re.I)

def inject_profile(ctx: str, member: MemberProfile) -> str:
    # Inject AFTER retrieval so it doesn’t affect vector search
    header = f"Member profile:\n- Name: {member.name}\n\n"
    return f"{header}{ctx}" if ctx else header

# ---------- Startup ----------
@app.on_event("startup")
async def _startup():
    # compiling graph for /chat (one-shot) and for future use
    graph, conn = await build_graph_async()
    app.state.graph = graph
    app.state.conn = conn
    # instantiate agents once for direct streaming
    app.state.pdf_agent: AnswerAgent = BenefitsIQ()
    app.state.claims_agent: AnswerAgent = ClaimsAssist()
    app.state.intent = IntentClassifier(IntentConfig())
    app.state.member = MemberProfile(name="Maria Martinez", first="Maria")

@app.on_event("shutdown")
async def _shutdown():
    try:
        await app.state.conn.close()
    except Exception:
        pass

# ---------- Helpers ----------
def _sse(event: str, data: dict) -> bytes:
    payload = json.dumps(data, ensure_ascii=False)
    return (
        f"event: {event}\n" +
        "\n".join(f"data: {line}" for line in payload.splitlines()) +
        "\n\n"
    ).encode("utf-8")

# ---------- Models ----------
class ChatIn(BaseModel):
    text: str
    thread_id: Optional[str] = None

class ChatOut(BaseModel):
    thread_id: str
    answer: str

# ---------- One-shot stays graph-driven ----------
@app.post("/chat", response_model=ChatOut)
async def chat(req: ChatIn):
    tid = req.thread_id or str(uuid.uuid4())
    label, _ = app.state.intent.classify(req.text or "")
    if label != "in_scope":
        return {"thread_id": tid, "answer": guardrail_reply(label) or ""}
    config = {"configurable": {"thread_id": tid}}
    res = await app.state.graph.ainvoke({"messages": [HumanMessage(content=req.text)]}, config=config)
    msgs = res.get("messages", [])
    answer = next((m.content for m in reversed(msgs) if isinstance(m, AIMessage)), "")
    return {"thread_id": tid, "answer": answer}

# ---------- STREAMING: direct from agents ----------
@app.get("/chat/stream")
async def chat_stream_get(text: str = Query(...), thread_id: Optional[str] = Query(None)):
    return await _chat_stream_direct(text=text, thread_id=thread_id)

@app.post("/chat/stream")
async def chat_stream_post(req: ChatIn):
    return await _chat_stream_direct(text=req.text, thread_id=req.thread_id)

async def _stream_text_as_tokens(tid: str, text: str):
  for i in range(0, len(text), 24):
      yield _sse("token", {"agent": "guardrail", "token": text[i:i+24]})
      await asyncio.sleep(0)
  yield _sse("final", {"thread_id": tid, "answer": text})


# async def _chat_stream_direct(*, text: str, thread_id: Optional[str]):
#     tid = thread_id or str(uuid.uuid4())
#     pdf_agent: AnswerAgent = app.state.pdf_agent
#     claims_agent: AnswerAgent = app.state.claims_agent
#     intent: IntentClassifier = app.state.intent
#
#     async def gen() -> AsyncIterator[bytes]:
#         label, scores = intent.classify(text or "")
#         if label != "in_scope":
#             msg = guardrail_reply(label) or ""
#             # Tell UI it's a special path (optional)
#             yield _sse("route", {"thread_id": tid, "route": "guardrail"})
#             async for frame in _stream_text_as_tokens(tid, msg):
#                 yield frame
#             return
#         # 0) route first (fast), inform client immediately
#         route = await fast_route(text or "")
#         yield _sse("route", {"thread_id": tid, "route": route})
#
#         # 1) choose agents
#         selected: list[tuple[str, AnswerAgent]] = []
#         if route in ("pdf", "both"):
#             selected.append(("pdf", pdf_agent))
#         if route in ("claims", "both"):
#             selected.append(("claims", claims_agent))
#         if not selected:
#             yield _sse("final", {"thread_id": tid, "answer": "I couldn't determine a suitable source to answer that."})
#             return
#
#         # 2) run each agent concurrently:
#         #    retrieval -> emit citations; then stream tokens as they come
#         q: asyncio.Queue[dict] = asyncio.Queue()
#
#         async def run_agent(name: str, agent: AnswerAgent):
#             # retrieval (can be slow): do in thread to avoid blocking
#             loop = asyncio.get_running_loop()
#             ctx, cites = await loop.run_in_executor(None, lambda: agent.retrieve(text))
#             # send citations ASAP
#             await q.put({"kind": "citations", "agent": name, "citations": cites})
#             # now stream tokens
#             history: list[BaseMessage] = []   # keep simple; graph keeps history on /chat
#             async for tok in agent.astream_answer(text, history, context=ctx):
#                 await q.put({"kind": "token", "agent": name, "token": tok})
#             await q.put({"kind": "done", "agent": name})
#
#         tasks = [asyncio.create_task(run_agent(n, a)) for n, a in selected]
#
#         done = 0
#         while done < len(tasks):
#             ev = await q.get()
#             if ev["kind"] == "citations":
#                 yield _sse("citations", {"agent": ev["agent"], "citations": ev["citations"]})
#             elif ev["kind"] == "token":
#                 yield _sse("token", {"agent": ev["agent"], "token": ev["token"]})
#             elif ev["kind"] == "done":
#                 done += 1
#
#         # Optionally, you can also send a composed final answer if you want:
#         yield _sse("final", {"thread_id": tid, "answer": ""})
#
#     headers = {
#         "Content-Type": "text/event-stream",
#         "Cache-Control": "no-cache",
#         "Connection": "keep-alive",
#         "X-Accel-Buffering": "no",
#     }
#     return StreamingResponse(gen(), headers=headers)

async def _chat_stream_direct(*, text: str, thread_id: Optional[str]):
    import re, uuid, asyncio
    from types import SimpleNamespace

    tid = thread_id or str(uuid.uuid4())
    pdf_agent: AnswerAgent = app.state.pdf_agent
    claims_agent: AnswerAgent = app.state.claims_agent
    intent: IntentClassifier = app.state.intent

    # --- Member "memory" (use app.state.member if set at startup; else default to Maria) ---
    member = getattr(app.state, "member", SimpleNamespace(name="Maria Martinez", first="Maria"))

    GREET_RE = re.compile(r"^\s*(hi|hello|hey|greetings|good\s+(morning|afternoon|evening))\b", re.I)

    def _inject_profile(ctx: str) -> str:
        """Prefix retrieved context with a tiny member profile block (post-retrieval)."""
        header = f"Member profile:\n- Name: {member.name}\n\n"
        return f"{header}{ctx}" if ctx else header

    async def gen() -> AsyncIterator[bytes]:
        # ---- 0) Greeting short-circuit ----
        if GREET_RE.match(text or ""):
            yield _sse("route", {"thread_id": tid, "route": "greet"})
            msg = (
                f"Hi {member.first}! 👋 I’m here to help with your benefits (EOC) and claims — "
                f"things like copays, deductibles, in-network rules, and what you owe on a claim. "
                f"What would you like to check today?"
            )
            async for frame in _stream_text_as_tokens(tid, msg):
                yield frame
            return

        # ---- 1) Semantic guardrail (medical / off-topic) ----
        label, scores = intent.classify(text or "")
        if label != "in_scope":
            reply = guardrail_reply(label) or ""
            # make it a bit more personal
            if reply and not reply.lower().startswith("hi"):
                reply = f"Hi {member.first}! " + reply
            yield _sse("route", {"thread_id": tid, "route": "guardrail"})
            async for frame in _stream_text_as_tokens(tid, reply):
                yield frame
            return

        # ---- 2) Normal routing ----
        route = await fast_route(text or "")
        yield _sse("route", {"thread_id": tid, "route": route})

        # ---- 3) Choose agents ----
        selected: list[tuple[str, AnswerAgent]] = []
        if route in ("pdf", "both"):
            selected.append(("pdf", pdf_agent))
        if route in ("claims", "both"):
            selected.append(("claims", claims_agent))
        if not selected:
            yield _sse("final", {"thread_id": tid, "answer": f"Sorry {member.first}, I couldn't determine a suitable source to answer that."})
            return

        # ---- 4) Run each agent concurrently: retrieve → emit citations → stream tokens ----
        q: asyncio.Queue[dict] = asyncio.Queue()

        async def run_agent(name: str, agent: AnswerAgent):
            loop = asyncio.get_running_loop()
            # retrieval: offload to thread
            ctx, cites = await loop.run_in_executor(None, lambda: agent.retrieve(text))
            # inject personalization AFTER retrieval so search isn't skewed
            ctx = _inject_profile(ctx)
            # send citations ASAP
            await q.put({"kind": "citations", "agent": name, "citations": cites})
            # stream tokens
            history: list[BaseMessage] = []
            async for tok in agent.astream_answer(text, history, context=ctx):
                await q.put({"kind": "token", "agent": name, "token": tok})
            await q.put({"kind": "done", "agent": name})

        tasks = [asyncio.create_task(run_agent(n, a)) for n, a in selected]

        done = 0
        while done < len(tasks):
            ev = await q.get()
            if ev["kind"] == "citations":
                yield _sse("citations", {"agent": ev["agent"], "citations": ev["citations"]})
            elif ev["kind"] == "token":
                yield _sse("token", {"agent": ev["agent"], "token": ev["token"]})
            elif ev["kind"] == "done":
                done += 1

        # ---- 5) Final marker  ----
        yield _sse("final", {"thread_id": tid, "answer": ""})

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(gen(), headers=headers)

