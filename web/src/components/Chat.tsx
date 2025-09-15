import { useState } from "react";
import { streamChat } from "../api";
import { useStore } from "../store";
import { uid } from "../util";
import MessageList from "./MessageList";

export default function Chat() {
  const { active, activeId, appendMessage, appendAssistantToken, setRoute } = useStore();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  async function send() {
    if (!activeId || !text.trim()) return;
    const q = text.trim();
    setText("");
    appendMessage(activeId, { id: uid(), role: "user", content: q });
    setBusy(true);

    const close = streamChat(q, activeId, {
      onRoute: (route) => setRoute(activeId, route as any),
      onToken: (_agent, token) => appendAssistantToken(activeId, token),
      onFinal: () => setBusy(false),
      onError: () => setBusy(false),
    });

    // NOTE: if you add a "Stop" button later, call close()
  }

  return (
    <div className="main">
      <div className="meta">{active ? `Thread: ${active.id}` : "Pick or create a chat"}</div>
      {active && <MessageList messages={active.messages} />}
      <div className="inputbar">
        <input
          placeholder="Ask a question..."
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={e => e.key === "Enter" && !e.shiftKey ? send() : null}
          disabled={!activeId || busy}
        />
        <button onClick={send} disabled={!activeId || busy}>Send</button>
      </div>
    </div>
  );
}
