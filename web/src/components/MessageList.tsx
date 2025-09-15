import { Message } from "../types";

export default function MessageList({ messages }: { messages: Message[] }) {
  return (
    <div className="messages">
      {messages.map(m => (
        <div key={m.id} className={"msg " + m.role}>
          {m.content}
        </div>
      ))}
    </div>
  );
}
