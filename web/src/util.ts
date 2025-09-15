export function uid() {
  // Safe fallback if older browser lacks crypto.randomUUID
  // @ts-ignore
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return `id_${Date.now().toString(36)}_${Math.random().toString(36).slice(2,8)}`;
}
