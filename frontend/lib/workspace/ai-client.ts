import { readToken } from "../auth/token";

export async function requestAI<T>(
  task: string,
  payload: unknown,
  signal?: AbortSignal,
): Promise<T> {
  // **토큰을 같이 보낸다.** 트렌드는 원마다 끌 수 있고(FR-808), 그 판정을 서버가
  // 해야 한다. 화면에서만 막으면 이 주소를 직접 부르는 요청은 그대로 돈다.
  const token = typeof window === "undefined" ? null : readToken();
  const response = await fetch("/api/assistant", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ task, payload }),
    signal,
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(data.error || "AI 요청을 처리하지 못했어요. 다시 시도해주세요.");
  return data as T;
}
