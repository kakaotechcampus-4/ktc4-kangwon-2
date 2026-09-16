export async function requestAI<T>(
  task: string,
  payload: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch("/api/assistant", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task, payload }),
    signal,
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(data.error || "AI 요청을 처리하지 못했어요. 다시 시도해주세요.");
  return data as T;
}
