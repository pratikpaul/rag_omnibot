export async function newThread(): Promise<string> {
  const r = await fetch("/thread/new", { method: "POST" });
  const j = await r.json();
  return j.thread_id as string;
}

export type StreamHandlers = {
  onRoute?: (route: string) => void;
  onToken?: (agent: "pdf" | "claims", token: string) => void;
  onFinal?: (answer: string) => void;
  onError?: (err: any) => void;
};

export function streamChat(text: string, threadId: string, h: StreamHandlers) {
  const url = `/chat/stream?text=${encodeURIComponent(text)}&thread_id=${encodeURIComponent(threadId)}`;
  const es = new EventSource(url);

  es.addEventListener("route", (ev: MessageEvent) => {
    try { h.onRoute?.(JSON.parse(ev.data).route); } catch {}
  });
  es.addEventListener("token", (ev: MessageEvent) => {
    try {
      const { agent, token } = JSON.parse(ev.data);
      h.onToken?.(agent, token);
    } catch {}
  });
  es.addEventListener("final", (ev: MessageEvent) => {
    try { h.onFinal?.(JSON.parse(ev.data).answer || ""); } catch {}
    es.close();
  });
  es.onerror = (e) => { es.close(); h.onError?.(e); };

  return () => es.close();
}
