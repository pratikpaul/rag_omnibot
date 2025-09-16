export type Role = "user" | "assistant";

export interface Message {
  id: string;
  role: Role;
  content: string;
}

export interface ThreadData {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: Message[];
  lastRoute?: "pdf" | "claims" | "both";
}
