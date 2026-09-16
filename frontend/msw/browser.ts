import { setupWorker } from "msw/browser";
import { handlers } from "./handlers";

export const worker = setupWorker(...handlers);
const RELOADED_KEY = "saessak.msw.controllerReload";
const CONTROLLER_TIMEOUT_MS = 5000;

/** worker.start() 중복 실행 방지용 공유 상태. */
export const runtime: { starting?: Promise<unknown> } = {};

/**
 * MSW를 시작하고, 서비스워커가 "현재 페이지를 제어"하는 상태까지 확인한 뒤에만 resolve한다.
 * 제어권을 얻지 못하면 reject한다 — 이 경우 앱을 렌더하면 /api 요청이 Next로 빠져 HTML 404가 난다.
 */
export function startMockWorker() {
  runtime.starting ??= (async () => {
    // public/mockServiceWorker.js 를 루트 경로에서 그대로 사용한다 (basePath 없음).
    await worker.start({
      onUnhandledRequest: "bypass",
      serviceWorker: { url: "/mockServiceWorker.js" },
    });
    await ensureControlled();
  })().catch((error) => {
    runtime.starting = undefined; // 새로고침/재시도 시 다시 시작할 수 있도록 되돌린다.
    throw error;
  });
  return runtime.starting;
}

/**
 * 하드 리로드(Ctrl+Shift+R)나 워커가 막 등록된 직후에는 워커가 활성 상태여도
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
