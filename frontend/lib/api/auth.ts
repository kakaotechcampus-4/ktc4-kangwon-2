import { apiRequest } from "./client";
import { saveToken, clearToken } from "../auth/token";

/** `POST /api/auth/signup` · `POST /api/auth/login` 의 응답 (docs/api-spec.md §0). */
export type AuthResult = {
  token: string;
  user: { id: number; email: string; name: string; center_id: number | null };
};

/**
 * 서버에 계정을 만들고 토큰을 받아 둔다.
 *
 * **비밀번호는 서버로 그대로 보내고 서버가 해싱한다.** 브라우저에서 미리 해싱해 보내면
 * 그 해시가 곧 비밀번호가 되어(그대로 재전송하면 통과) 아무 이득이 없다.
 */
export async function signup(name: string, email: string, password: string): Promise<AuthResult> {
  const result = await apiRequest<AuthResult>("/api/auth/signup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email, password }),
  });
  saveToken(result.token);
  return result;
}

export async function login(email: string, password: string): Promise<AuthResult> {
  const result = await apiRequest<AuthResult>("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  saveToken(result.token);
  return result;
}

/**
 * 서버에 알리지 않는다. 토큰을 버리면 이 브라우저에서는 못 쓴다.
 *
 * 남은 토큰은 만료(12시간)까지 유효하다 — 강제 무효화가 필요해지면 서버에 저장소를 둔다.
 */
export function logout(): void {
  clearToken();
}
