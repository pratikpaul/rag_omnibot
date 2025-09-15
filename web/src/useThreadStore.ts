import { useEffect, useMemo, useState } from "react";
import { Message, ThreadData } from "./types";

const LS_KEY = "omnibot:threads";

function load(): ThreadData[] {
  try { return JSON.parse(localStorage.getItem(LS_KEY) || "[]"); } catch { return []; }
}
function save(threads: ThreadData[]) {
  localStorage.setItem(LS_KEY, JSON.stringify(threads));
}

export function useThreadStore() {
  const [threads, setThreads] = useState<ThreadData[]>(load);
  const [activeId, setActiveId] = useState<string | null>(threads[0]?.id || null);
  useEffect(() => save(threads), [threads]);

  const active = useMemo(
    () => threads.find(t => t.id === activeId) || null,
    [threads, activeId]
  );

  function addThread(tid: string) {
    const now = Date.now();
    const t: ThreadData = { id: tid, title: "New chat", createdAt: now, updatedAt: now, messages: [] };
    setThreads(prev => [t, ...prev]);
    setActiveId(tid);
  }

  function setRoute(tid: string, route: ThreadData["lastRoute"]) {
    setThreads(prev => prev.map(t => t.id === tid ? { ...t, lastRoute: route } : t));
  }

  function appendMessage(tid: string, msg: Message) {
    setThreads(prev => prev.map(t => {
      if (t.id !== tid) return t;
      const title = t.title === "New chat" && msg.role === "user"
        ? (msg.content.slice(0, 48) || "New chat")
        : t.title;
      return { ...t, messages: [...t.messages, msg], title, updatedAt: Date.now() };
    }));
  }

  function appendAssistantToken(tid: string, token: string) {
    setThreads(prev => prev.map(t => {
      if (t.id !== tid) return t;
      const msgs = t.messages.slice();
      if (!msgs.length || msgs[msgs.length - 1].role !== "assistant") {
        msgs.push({ id: crypto.randomUUID(), role: "assistant", content: token });
      } else {
        msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], content: msgs[msgs.length - 1].content + token };
      }
      return { ...t, messages: msgs, updatedAt: Date.now() };
    }));
  }

  return { threads, activeId, active, setActiveId, addThread, appendMessage, appendAssistantToken, setRoute };
}
