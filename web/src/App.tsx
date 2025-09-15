import { useEffect, useMemo, useRef, useState } from "react";

// ----- Types -----
type Role = "user" | "assistant";
type Msg = { id: string; role: Role; content: string };
type Thread = {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: Msg[];
  lastRoute?: "pdf" | "claims" | "both";
};

// ----- Utils -----
const LS_KEY = "omnibot:threads";
const uid = () =>
  (typeof crypto !== "undefined" && (crypto as any).randomUUID)
    ? (crypto as any).randomUUID()
    : `id_${Date.now().toString(36)}_${Math.random().toString(36).slice(2,8)}`;

const loadThreads = (): Thread[] => {
  try { return JSON.parse(localStorage.getItem(LS_KEY) || "[]"); }
  catch { return []; }
};
const saveThreads = (ts: Thread[]) => localStorage.setItem(LS_KEY, JSON.stringify(ts));

function streamChat(
  text: string,
  threadId: string,
  handlers: {
    onRoute?: (route: string) => void;
    onToken?: (agent: "pdf" | "claims", token: string) => void;
    onFinal?: (answer: string) => void;
    onError?: (err: any) => void;
  }
) {
  const url = `/chat/stream?text=${encodeURIComponent(text)}&thread_id=${encodeURIComponent(threadId)}`;
  const es = new EventSource(url);

  es.addEventListener("route", (ev: MessageEvent) => {
    try { handlers.onRoute?.(JSON.parse(ev.data).route); } catch {}
  });
  es.addEventListener("token", (ev: MessageEvent) => {
    try {
      const { agent, token } = JSON.parse(ev.data);
      handlers.onToken?.(agent, token);
    } catch {}
  });
  es.addEventListener("final", (ev: MessageEvent) => {
    try { handlers.onFinal?.(JSON.parse(ev.data).answer || ""); } catch {}
    es.close();
  });
  es.onerror = (e) => { es.close(); handlers.onError?.(e); };

  return () => es.close();
}

// ----- App -----
export default function App() {
  const [threads, setThreads] = useState<Thread[]>(loadThreads);
  const [activeId, setActiveId] = useState<string | null>(threads[0]?.id || null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [menuFor, setMenuFor] = useState<string | null>(null);
  const closeRef = useRef<() => void>();
  const messagesRef = useRef<HTMLDivElement>(null);   // <-- define the ref here

  useEffect(() => { saveThreads(threads); }, [threads]);

  // Auto-scroll messages to bottom when new content or the ephemeral line changes
  useEffect(() => {
    if (!messagesRef.current) return;
    // use rAF to run after DOM paints
    requestAnimationFrame(() => {
      if (messagesRef.current) {
        messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
      }
    });
  }, [activeId, threads, threads.length, threads[0]?.messages?.length]); // simple but robust deps

  useEffect(() => {
      const onDocClick = () => setMenuFor(null);
      const onEsc = (e: KeyboardEvent) => { if (e.key === "Escape") setMenuFor(null); };
      document.addEventListener("click", onDocClick);
      document.addEventListener("keydown", onEsc);
      return () => {
        document.removeEventListener("click", onDocClick);
        document.removeEventListener("keydown", onEsc);
      };
  }, []);

  const active = useMemo(
    () => threads.find(t => t.id === activeId) || null,
    [threads, activeId]
  );

  function renameThread(id: string) {
      const t = threads.find(x => x.id === id);
      const current = t?.title ?? "Chat";
      const name = prompt("Rename chat", current);
      if (!name || !name.trim()) return;
      setThreads(prev => prev.map(x => x.id === id ? { ...x, title: name.trim(), updatedAt: Date.now() } : x));
  }

  function deleteThread(id: string) {
      setThreads(prev => {
        const next = prev.filter(x => x.id !== id);
        if (activeId === id) setActiveId(next[0]?.id || null);
        return next;
      });
  }

  async function handleNewChat() {
    const localTid =
      (typeof crypto !== "undefined" && (crypto as any).randomUUID)
        ? (crypto as any).randomUUID()
        : `id_${Date.now().toString(36)}_${Math.random().toString(36).slice(2,8)}`;

    const now = Date.now();
    const t = { id: localTid, title: "New chat", createdAt: now, updatedAt: now, messages: [] as Msg[] };

    setThreads(prev => [t, ...prev]);
    setActiveId(localTid);

    // Optional server thread mint (not required for function)
    try {
      const r = await fetch("/thread/new", { method: "POST" });
      if (r.ok) {
        const { thread_id } = await r.json();
        console.debug("Server thread minted:", thread_id);
      }
    } catch {
      // ignore
    }
  }

  function setRoute(route: Thread["lastRoute"]) {
    if (!activeId) return;
    setThreads(prev => prev.map(t => t.id === activeId ? { ...t, lastRoute: route } : t));
  }

  function appendMessage(role: Role, content: string) {
    if (!activeId) return;
    setThreads(prev => prev.map(t => {
      if (t.id !== activeId) return t;
      const msgs = [...t.messages, { id: uid(), role, content }];
      const title = (t.title === "New chat" && role === "user")
        ? (content.slice(0, 48) || "New chat")
        : t.title;
      return { ...t, messages: msgs, title, updatedAt: Date.now() };
    }));
  }

  function appendAssistantToken(token: string) {
    if (!activeId) return;
    setThreads(prev => prev.map(t => {
      if (t.id !== activeId) return t;
      const msgs = t.messages.slice();
      if (!msgs.length || msgs[msgs.length - 1].role !== "assistant") {
        msgs.push({ id: uid(), role: "assistant", content: token });
      } else {
        msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], content: msgs[msgs.length - 1].content + token };
      }
      return { ...t, messages: msgs, updatedAt: Date.now() };
    }));
  }

  // Ephemeral "thinking…" line
  const [ephemeral, setEphemeral] = useState<string | null>(null);
  function routeToStatus(route: string | null) {
    if (route === "pdf") return "BenefitsIQ agent thinking…";
    if (route === "claims") return "Claims Assist agent thinking…";
    if (route === "both") return "BenefitsIQ and Claims Assist agents thinking…";
    return null;
  }

  async function send() {
    if (!activeId || !text.trim() || busy) return;

    const q = text.trim();
    setText("");
    appendMessage("user", q);
    setBusy(true);

    // Close any previous stream
    closeRef.current?.();

    let gotTokens = false;

    closeRef.current = streamChat(q, activeId, {
      onRoute: (r) => {
        setRoute(r as any);
        const label = routeToStatus(r);
        if (label) setEphemeral(label);
      },
      onToken: (_agent, tok) => {
        if (!gotTokens) setEphemeral(null); // hide "thinking…" at first token
        gotTokens = true;
        appendAssistantToken(tok);
      },
      onFinal: (answer) => {
        if (!gotTokens && answer) appendMessage("assistant", answer);
        setEphemeral(null);
        setBusy(false);
      },
      onError: (e) => {
        console.error("SSE error", e);
        setEphemeral(null);
        setBusy(false);
      },
    });
  }

  return (
    <div className="app">
      {/* Sidebar */}
      <div className="sidebar">
        <button className="newbtn" onClick={handleNewChat}>+ New Chat</button>
        <h2>History</h2>
        {threads.length === 0 && <div className="meta">No chats yet</div>}
        {threads.map(t => (
          <div
            key={t.id}
            className={
              "thread" +
              (t.id === activeId ? " active" : "") +
              (menuFor === t.id ? " menu-open" : "")
            }
            onClick={() => { setActiveId(t.id); setMenuFor(null); }}
            title={t.id}
          >
            {t.title}

            {/* ⋯ button (unchanged) */}
            <button
              className="dotbtn"
              title="More"
              onClick={(e) => {
                e.stopPropagation();
                setMenuFor(menuFor === t.id ? null : t.id);
              }}
              aria-haspopup="menu"
              aria-expanded={menuFor === t.id}
            >
              <span className="dots">⋯</span>
            </button>

            {/* popup menu (unchanged) */}
            {menuFor === t.id && (
              <div
                className="thread-menu"
                role="menu"
                onClick={(e) => e.stopPropagation()}
              >
                <button role="menuitem" onClick={() => { setMenuFor(null); renameThread(t.id); }}>Rename</button>
                <button role="menuitem" onClick={() => { setMenuFor(null); deleteThread(t.id); }}>Delete</button>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Main */}
      <div className="main">
        <div className="meta">
          {active ? `Omnibot v0.1` : "Pick or create a chat"}
        </div>

        {/* Messages scroll container */}
        <div className="messages" ref={messagesRef}>
          {active?.messages.map(m => (
            <div key={m.id} className={"msg " + m.role}>{m.content}</div>
          ))}
          {/* Ephemeral status */}
          {ephemeral && <div className="ephemeral">{ephemeral}</div>}
        </div>

        <div className="inputbar">
          <input
            placeholder={activeId ? "Ask a question..." : "Click + New Chat first"}
            value={text}
            onChange={e => setText(e.target.value)}
            onKeyDown={e => e.key === "Enter" && !e.shiftKey ? send() : null}
            disabled={!activeId || busy}
          />
          <button onClick={send} disabled={!activeId || busy}>Send</button>
        </div>
      </div>
    </div>
  );
}
