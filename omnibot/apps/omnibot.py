from __future__ import annotations
import asyncio
from langchain_core.messages import HumanMessage, AIMessage
from omnibot.graph.graph_builder import build_graph_async

async def main_async():
    app, conn = await build_graph_async()
    config = {"configurable": {"thread_id": "omnibot-thread-4"}}
    print("Omnibot ready. Type :q to quit.")
    try:
        while True:
            q = input("\nYou: ").strip()
            if q in {":q", ":quit", ":exit"}: break
            if not q: continue

            print("\nOmnibot: ", end="", flush=True)
            async for _ in app.astream({"messages": [HumanMessage(content=q)]}, config=config, stream_mode="values"):
                pass
            st = await app.aget_state(config)
            print(f"\n(elapsed {st.values.get('elapsed', 0.0):.2f}s)")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main_async())