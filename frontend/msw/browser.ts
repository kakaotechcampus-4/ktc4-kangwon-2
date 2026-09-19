import { setupWorker } from "msw/browser";
import type { UnhandledRequestCallback } from "msw";
import { handlers } from "./handlers";

export const worker = setupWorker(...handlers);
const RELOADED_KEY = "saessak.msw.controllerReload";
/** handlers.ts에 등록된 interception 판정 전용 probe 경로. */
export const MSW_HEALTH_PATH = "/api/__msw_health";
const INTERCEPTION_FAILED =
  "[MSW] 서비스워커가 실제 API 요청을 가로채지 못했습니다. 새로고침 후에도 반복되면 DevTools > Application > Service Workers에서 'Bypass for network'와 워커 상태를 확인해주세요.";
const CONTROLLER_TIMEOUT_MS = 5000;

/** worker.start() 중복 실행 방지용 공유 상태. */
export const runtime: { starting?: Promise<unknown> } = {};

/** mock이 아니라 실제 Next.js Route Handler가 응답하는 경로 — 진단 대상에서 제외한다. */
const REAL_ROUTE_PREFIXES = ["/api/assistant", "/api/templates/extract"];

/**
 * 핸들러가 없는 /api 요청을 조용히 흘려보내지 않고 콘솔 에러로 알린다.
 * "bypass"로 두면 handler 누락이 Next의 HTML 404로만 나타나서
 * 서비스워커가 요청을 가로채지 못한 상황과 구분할 수 없다.
 * /api 밖(페이지, /_next, 정적 파일 등)은 그대로 통과시킨다.
 */
export const handleUnhandledRequest: UnhandledRequestCallback = (request, print) => {
  const { pathname } = new URL(request.url);
  // 경로 자체이거나 그 하위 경로일 때만 실제 Route Handler로 본다.
  // startsWith만 쓰면 /api/assistant-wrong 같은 오타까지 조용히 빠져나간다.
  const isRealRoute = REAL_ROUTE_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
  if (isRealRoute) return;
  if (pathname.startsWith("/api/")) print.error();
};

/**
 * MSW를 시작하고, 실제 /api 요청이 MSW handler를 통과하는 것까지 확인한 뒤에만 resolve한다.
 * 실패하면 reject한다 — 이 경우 앱을 렌더하면 /api 요청이 Next로 빠져 HTML 404가 난다.
 */
export function startMockWorker() {
  runtime.starting ??= (async () => {
    // public/mockServiceWorker.js 를 루트 경로에서 그대로 사용한다 (basePath 없음).
    await worker.start({
      onUnhandledRequest: handleUnhandledRequest,
      serviceWorker: { url: "/mockServiceWorker.js" },
    });
    await ensureControlled(); // 보조 단계: 서비스워커 등록·제어권 확보
    await ensureIntercepting(); // 최종 판정: 요청이 정말 MSW를 통과하는지
  })().catch((error) => {
    runtime.starting = undefined; // 새로고침/재시도 시 다시 시작할 수 있도록 되돌린다.
    throw error;
  });
  return runtime.starting;
}

/**
 * 최종 readiness 판정. 제어권(controller)이 있어도 fetch가 MSW를 통과한다는 보장은 없다
 * (예: DevTools의 "Bypass for network", 스코프 밖 요청). 그래서 전용 probe를 실제로 요청해
 * MSW handler가 응답했는지로 판정한다. 조건을 하나라도 못 채우면 실패로 끝낸다(fail-closed).
 */
export async function ensureIntercepting() {
  let response: Response;
  try {
    response = await fetch(MSW_HEALTH_PATH, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
  } catch (error) {
    throw new Error(INTERCEPTION_FAILED, { cause: error });
  }
  if (!response.ok) throw new Error(INTERCEPTION_FAILED);
  if (!(response.headers.get("content-type") ?? "").toLowerCase().includes("application/json"))
    throw new Error(INTERCEPTION_FAILED);
  // Next의 HTML 404를 JSON으로 읽으면 SyntaxError가 나므로, parsing 실패도 readiness 실패로 정리한다.
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new Error(INTERCEPTION_FAILED);
  }
  if (typeof body !== "object" || body === null) throw new Error(INTERCEPTION_FAILED);
  if ((body as { msw?: unknown }).msw !== true) throw new Error(INTERCEPTION_FAILED);
}

/**
 * 보조 단계. 하드 리로드(Ctrl+Shift+R)나 워커가 막 등록된 직후에는 워커가 활성 상태여도
 * 현재 페이지를 제어하지 않는다(navigator.serviceWorker.controller === null).
 * 제어권을 기다리고, 최초 1회만 새로고침하고, 그래도 없으면 실패로 끝낸다(fail-closed).
 */
export async function ensureControlled() {
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) {
    throw new Error(
      "[MSW] 이 브라우저에서는 서비스워커를 사용할 수 없어 개발용 API를 준비하지 못했습니다.",
    );
  }
  if (navigator.serviceWorker.controller) {
    clearReloadFlag();
    return;
  }

  await Promise.race([navigator.serviceWorker.ready, wait(CONTROLLER_TIMEOUT_MS)]);
  if (navigator.serviceWorker.controller) {
    clearReloadFlag();
    return;
  }

  await waitForController(CONTROLLER_TIMEOUT_MS);
  if (navigator.serviceWorker.controller) {
    clearReloadFlag();
    return;
  }

  // 아직 한 번도 새로고침하지 않았다면 한 번만 새로고침해 제어권을 넘겨받는다(무한 루프 방지).
  if (!readReloadFlag()) {
    writeReloadFlag();
    console.info("[MSW] 서비스워커 제어 확보를 위해 한 번 새로고침합니다.");
    window.location.reload();
    await new Promise(() => {
      /* 새로고침될 때까지 resolve하지 않는다. */
    });
  }

  throw new Error(
    "[MSW] 서비스워커가 이 페이지를 제어하지 못했습니다. 새로고침 후에도 반복되면 DevTools > Application > Service Workers에서 상태를 확인해주세요.",
  );
}

function waitForController(timeoutMs: number) {
  return new Promise<void>((resolve) => {
    const done = () => {
      navigator.serviceWorker.removeEventListener("controllerchange", done);
      clearTimeout(timer);
      resolve();
    };
    const timer = setTimeout(done, timeoutMs);
    navigator.serviceWorker.addEventListener("controllerchange", done);
  });
}

const wait = (ms: number) =>
  new Promise<void>((resolve) => {
    setTimeout(resolve, ms);
  });
const readReloadFlag = () => {
  try {
    return sessionStorage.getItem(RELOADED_KEY) === "1";
  } catch {
    return true;
  }
};
const writeReloadFlag = () => {
  try {
    sessionStorage.setItem(RELOADED_KEY, "1");
  } catch {
    /* noop */
  }
};
const clearReloadFlag = () => {
  try {
    sessionStorage.removeItem(RELOADED_KEY);
  } catch {
    /* noop */
  }
};
