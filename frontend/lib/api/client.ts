import { readToken } from "../auth/token";
import { captureSession } from "../auth/request-session";

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;
  constructor(status: number, body: unknown) {
    // 서버가 준 메시지는 그대로 쓰고, 없으면 사용자용 문구를 쓴다. 상태/본문은 아래 필드에 그대로 남는다.
    super(
      typeof body === "object" &&
        body !== null &&
        "error" in body &&
        typeof (body as { error?: { message?: unknown } }).error?.message === "string"
        ? (body as { error: { message: string } }).error.message
        : "요청을 처리하지 못했어요. 잠시 후 다시 시도해주세요.",
    );
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

/**
 * /api/... 요청이 JSON API가 아니라 Next의 HTML(주로 404 페이지)을 받은 경우.
 * = MSW가 요청을 가로채지 못한 전송 계층 문제이므로, 실제 API의 NOT_FOUND와 절대 섞지 않는다.
 */
export class MswTransportError extends Error {
  readonly status: number;
  readonly path: string;
  readonly body: string;
  constructor(status: number, path: string, body: string) {
    super(
      "개발용 API(MSW)가 요청을 가로채지 못했습니다. 페이지를 새로고침한 뒤 다시 시도해주세요.",
    );
    this.name = "MswTransportError";
    this.status = status;
    this.path = path;
    this.body = body;
  }
}

const looksLikeHtml = (contentType: string | null, text: string) =>
  (contentType ?? "").toLowerCase().includes("text/html") ||
  /<!DOCTYPE html/i.test(text) ||
  text.includes("This page could not be found");

/** 서버 응답의 envelope/error code를 변환하지 않고 그대로 유지합니다. */
export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  if (!path.startsWith("/api/")) throw new Error("API path must start with /api/");
  const session = path.startsWith("/api/auth/") ? null : captureSession();
  const headers = new Headers(options.headers);
  if (!headers.has("Accept")) headers.set("Accept", "application/json");
  // 토큰은 여기 한 곳에서만 붙인다. 호출부마다 붙이면 새 API 를 만들 때 빠뜨린다.
  // 서버가 아동 실명이 내려오는 API 를 전부 막고 있다(docs/api-spec.md 「인증」).
  const token = typeof window === "undefined" ? null : readToken();
  if (token && !headers.has("Authorization")) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(path, { ...options, headers });
  const text = await response.text();
  session?.assertCurrent();
  const method = options.method ?? "GET";

  // HTML 응답은 JSON API 응답이 아니다 → ApiError가 아니라 전송 오류로 분리한다.
  if (text && looksLikeHtml(response.headers.get("content-type"), text)) {
    console.error(
      "[API] " + method + " " + path + " → " + response.status + " (HTML)",
      text.slice(0, 120),
    );
    console.warn(
      "[API] MSW가 이 요청을 가로채지 못했습니다(서비스워커 미제어 또는 NEXT_PUBLIC_API_MOCKING 미설정).",
    );
    throw new MswTransportError(response.status, path, text);
  }

  let body: unknown = undefined;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      if (response.ok) throw new Error("API returned invalid JSON");
      body = text;
    }
  }
  if (!response.ok) {
    console.error("[API] " + method + " " + path + " → " + response.status, body);
    throw new ApiError(response.status, body);
  }
  return body as T;
}

/**
 * 토큰이 없거나 못 믿어서 거절된 것인지 (`401 UNAUTHENTICATED`, docs/api-spec.md 「인증」).
 *
 * 404 와 갈라 봐야 한다 — 401 은 다시 로그인시킬 일이고, 404 는 대상이 없거나 남의 원 것이다.
 * 서버가 「만료」와 「서명 불일치」를 구분해 주지 않으므로 여기서도 나누지 않는다.
 */
export function isUnauthenticated(error: unknown): error is ApiError {
  if (!(error instanceof ApiError) || error.status !== 401) return false;
  const body = error.body as { error?: { code?: unknown } } | null;
  return typeof body === "object" && body !== null && body.error?.code === "UNAUTHENTICATED";
}

/** 서버 에러 봉투. `ApiError` 가 아니거나 모양이 다르면 `null`. */
function envelope(error: unknown): { code?: unknown; fields?: unknown } | null {
  if (!(error instanceof ApiError)) return null;
  const body = error.body as { error?: unknown } | null;
  if (typeof body !== "object" || body === null) return null;
  const inner = body.error;
  return typeof inner === "object" && inner !== null ? inner : null;
}

/**
 * `VALIDATION_FAILED` 가 짚은 칸을 화면 입력 이름으로 바꾼다 (docs/api-spec.md 「공통 에러 형식」).
 *
 * 계약상 `fields` 는 늘 배열이지만 받은 값을 믿지 않고 걸러 쓴다.
 * 점 표기(`sources.3`)는 앞부분만 본다 — 화면에는 그 묶음이 하나뿐이다.
 * 화면에 없는 칸은 버린다. 서버 이름을 그대로 보여주면 교사가 어디를 고칠지 모른다.
 */
export function invalidFields(error: unknown, map: Record<string, string>): string[] {
  const fields = envelope(error)?.fields;
  if (envelope(error)?.code !== "VALIDATION_FAILED" || !Array.isArray(fields)) return [];
  const names = fields
    .filter((field): field is string => typeof field === "string")
    .map((field) => map[field] ?? map[field.split(".")[0]])
    .filter((name): name is string => !!name);
  return [...new Set(names)];
}

/** 실제 API가 돌려준 JSON NOT_FOUND인지 (= 오래된 로컬 연결 정보 정리 대상인지) */
export function isApiNotFound(error: unknown): error is ApiError {
  if (!(error instanceof ApiError) || error.status !== 404) return false;
  const body = error.body as { error?: { code?: unknown } } | null;
  return typeof body === "object" && body !== null && body.error?.code === "NOT_FOUND";
}
