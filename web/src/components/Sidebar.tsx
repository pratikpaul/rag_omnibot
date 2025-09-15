import { newThread } from "../api";
import { useStore } from "../store";

export default function Sidebar() {
  const { threads, activeId, setActiveId, addThreadLocal } = useStore();

  async function handleNew() {
    const tid = await newThread();
    addThreadLocal(tid);
  }

  return (
    <div className="sidebar">
      <button className="newbtn" onClick={handleNew}>+ New Chat</button>
      <h2>History</h2>
      {threads.length === 0 && <div className="meta">No chats yet</div>}
      {threads.map(t => (
        <div
          key={t.id}
          className={"thread" + (t.id === activeId ? " active" : "")}
          onClick={() => setActiveId(t.id)}
          title={t.id}
        >
          {t.title}
        </div>
      ))}
    </div>
  );
}
