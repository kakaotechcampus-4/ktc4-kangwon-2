import { apiRequest } from "./client";
import { saveToken, clearToken } from "../auth/token";
import { captureSession } from "../auth/request-session";

/** `POST /api/auth/signup` · `POST /api/auth/login` 의 응답 (docs/api-spec.md §0). */
export type AuthResult = {
  token: string;
  user: { id: number; email: string; name: string; center_id: number | null };
};

/** 현재 계정의 원 번호를 서버에서 확인한다 (docs/api-spec.md §0). */
export async function getCurrentUser(): Promise<AuthResult["user"]> {
  const session = captureSession();
  const user = await apiRequest<AuthResult["user"]>("/api/auth/me");
  session.assertCurrent();
  return user;
}

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

/**
 * 비밀번호를 바꾼다 (`PATCH /api/auth/password`).
 *
 * 지금 비밀번호가 틀리면 422 `VALIDATION_FAILED` 에 `current_password` 가 담겨 온다.
 * 서버는 바꾸기 전 토큰을 모두 끊고 새 토큰을 준다(ADR-092) — 저장하지 않으면 다음 요청이 401 이다.
 */
export async function changePassword(current: string, next: string): Promise<void> {
  const result = await apiRequest<AuthResult>("/api/auth/password", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ current_password: current, new_password: next }),
  });
  saveToken(result.token);
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

/** 카카오 동의 화면 주소 (docs/api-spec.md §0-1). 서버에 키가 없으면 503 `DEPENDENCY_UNAVAILABLE`. */
export const kakaoAuthorizeUrl = (state: string) =>
  apiRequest<{ url: string }>(`/api/auth/kakao/authorize?state=${encodeURIComponent(state)}`);

/** 카카오가 돌려준 인가 코드로 로그인한다. 처음이면 서버가 계정을 만든다 (ADR-069). */
export async function kakaoLogin(code: string): Promise<AuthResult> {
  const result = await apiRequest<AuthResult>("/api/auth/kakao", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
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

/** 로그인한 교사. `center_id` 가 null 이면 온보딩을 아직 안 끝냈다 (docs/api-spec.md §0). */
export const getMe = () => apiRequest<AuthResult["user"]>("/api/auth/me");
