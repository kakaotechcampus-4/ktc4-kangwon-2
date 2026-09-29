import { delay, HttpResponse } from "msw";
import type { ErrorCode } from "../lib/api/types";
const failures = new Map<string, number>();
export const resetScenarioFailures = () => failures.clear();
export const statusFor: Record<ErrorCode, number> = {
  VALIDATION_FAILED: 422,
  NOT_FOUND: 404,
  GATE_BLOCKED: 409,
  ALREADY_EXISTS: 409,
  STALE_WRITE: 409,
  UNSUPPORTED_FILE_TYPE: 400,
  NO_ACTIVITIES: 503,
  LLM_BUDGET_EXCEEDED: 503,
  DEPENDENCY_UNAVAILABLE: 503,
  GENERATION_FAILED: 500,
};
// fields 는 틀린 칸이 하나여도, 없어도 배열이다. 목업이 단수 field 를 주면
// FE 가 목업에만 맞는 처리를 하게 된다 — 객체 리터럴이라 tsc 가 안 잡는다.
export const failure = (code: ErrorCode, message: string, ...fields: string[]) =>
  HttpResponse.json({ error: { code, message, fields } }, { status: statusFor[code] });
export async function scenario(request: Request, target: string, defaultDelay = 100) {
  const url = new URL(request.url),
    page =
      typeof window === "undefined"
        ? new URLSearchParams()
        : new URLSearchParams(window.location.search);
  const applies = !page.get("mswTarget") || page.get("mswTarget") === target;
  const value = (key: string) =>
    url.searchParams.get("mock" + key) ?? (applies ? page.get("msw" + key) : null);
  const ms = Number(value("Delay") ?? defaultDelay);
  await delay(Number.isFinite(ms) ? Math.max(0, Math.min(ms, 10000)) : defaultDelay);
  const selectedMonth = value("Month");
  const code =
    target === "month" && selectedMonth && !url.pathname.endsWith("/" + selectedMonth)
      ? null
      : value("Error");
  if (code && Object.hasOwn(statusFor, code)) {
    const limit = value("Failures"),
      key = request.method + url.href + page.toString();
    const used = failures.get(key) ?? 0;
    if (limit !== null && /^\d+$/.test(limit) && used >= Number(limit)) return null;
    failures.set(key, used + 1);
    return failure(
      code as ErrorCode,
      code === "NO_ACTIVITIES"
        ? "활동 데이터가 없습니다. 운영 담당자에게 문의해주세요."
        : "개발용 실패 상황입니다.",
      ...(value("Field") ? [value("Field") as string] : []),
    );
  }
  if (value("Empty") === "true")
    return target === "classes"
      ? HttpResponse.json({ items: [] })
      : target === "children"
        ? HttpResponse.json({ items: [], count: 0 })
        : null;
  return null;
}
