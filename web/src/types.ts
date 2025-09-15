export type Role = "user" | "assistant";

export interface Message {
  id: string;
  role: Role;
  content: string;
}

export interface ThreadData {
  id: string;
  title: string;            // first user message (trimmed)
  createdAt: number;
  updatedAt: number;
  messages: Message[];
  lastRoute?: "pdf" | "claims" | "both";
}
