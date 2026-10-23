"use client";

import { useEffect, useState, type ReactNode } from "react";
// MSW는 NODE_ENV와 무관하게 이 환경변수 하나로만 켜고 끈다.
// enabled  → 로컬/Vercel Preview/Production 모두에서 MSW 실행 (백엔드 없이 데모 가능)
// disabled 또는 미설정 → MSW를 시작하지 않고 기존 FastAPI 연결 구조 사용
// NEXT_PUBLIC_*는 빌드 시점에 값이 박히므로 값 변경 후에는 재빌드/재배포가 필요하다.
const enabled = process.env.NEXT_PUBLIC_API_MOCKING === "enabled";

/**
 * 예전에 목업을 켜고 들어왔던 브라우저에 남아 있는 서비스워커를 지운다.
 *
 * **서비스워커는 배포를 갈아끼워도 안 사라진다.** 한 번 등록되면 그 브라우저에 남아
 * `/api` 를 계속 가로채고, 교사 화면에는 「개발용 API 를 준비하지 못했습니다」만 뜬다.
 * 실제로 멘토님·팀원 브라우저에서 났던 일이다. 사람이 DevTools 를 열어 지우게 하는 대신
 * 목업이 꺼진 빌드가 스스로 치운다. 지우고 나면 그 다음 방문부터 정상이다.
 */
const CLEANUP_RELOAD_KEY = "saessak.msw.cleanupReload";

async function unregisterStaleWorker() {
  if (typeof navigator === "undefined" || !navigator.serviceWorker) return;
  try {
    const registrations = await navigator.serviceWorker.getRegistrations();
    // 다른 서비스워커까지 지우지 않는다 — 목업 워커만 본다.
    const stale = registrations.filter((r) =>
      (r.active ?? r.waiting ?? r.installing)?.scriptURL.includes("mockServiceWorker"),
    );
    if (stale.length === 0) {
      // 정리가 끝났다. 다음에 또 남으면 다시 한 번 새로고침할 수 있게 표시를 치운다.
      sessionStorage.removeItem(CLEANUP_RELOAD_KEY);
      return;
    }
    await Promise.all(stale.map((r) => r.unregister()));
    // **두 번은 새로고침하지 않는다.** unregister 가 먹지 않는 드문 경우에 화면이 무한히 깜빡인다.
    if (sessionStorage.getItem(CLEANUP_RELOAD_KEY) === "1") {
      console.warn(
        "[MSW] 목업 워커가 새로고침 뒤에도 남아 있습니다. DevTools > Application > Service Workers 에서 지워주세요.",
      );
      return;
    }
    sessionStorage.setItem(CLEANUP_RELOAD_KEY, "1");
    console.info("[MSW] 남아 있던 목업 워커를 지웠습니다. 새로고침하면 서버에 붙습니다.");
    window.location.reload();
  } catch {
    // 지우지 못해도 화면을 막지 않는다. 시크릿 창으로 열면 된다.
  }
}

export default function MockProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(!enabled);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    // 배포본에서 스위치 상태를 바로 확인할 수 있도록 남기는 최소 로그.
    console.info("[MSW] mocking:", process.env.NEXT_PUBLIC_API_MOCKING ?? "(unset)");
    if (!enabled) {
      void unregisterStaleWorker();
      return;
    }
    let mounted = true;
    // startMockWorker()는 서비스워커가 실제 MSW health 요청(/api/__msw_health)을 가로채는 것까지
    // 확인한 뒤 resolve한다. 실패하면 reject되고, 그 경우 children을 렌더하지 않아
    // API 요청 자체가 시작되지 않는다. controller 존재 여부는 최종 판정 기준이 아니다.
    import("./browser")
      .then((module) => module.startMockWorker())
      .then(() => {
        console.info("[MSW] worker started (interception verified)");
        if (mounted) setReady(true);
      })
      .catch((error) => {
        console.error("[MSW] Worker initialization failed", error);
        if (mounted) setFailed(true);
      });
    return () => {
      mounted = false;
    };
  }, []);

  if (failed) {
    return (
      <div
        role="alert"
        className="mx-auto flex max-w-md flex-col items-center gap-3 p-8 text-center"
      >
        <p className="text-[14.5px] leading-relaxed text-ink-soft">
          개발용 API를 준비하지 못했습니다. 페이지를 새로고침해주세요.
        </p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="inline-flex min-h-[40px] items-center justify-center rounded-full border border-sage-ink/30 bg-sage px-5 text-[13px] font-semibold text-ink transition-colors hover:bg-sage-ink"
        >
          새로고침
        </button>
      </div>
    );
  }
  if (!ready) return <p role="status">개발용 API를 준비하고 있어요.</p>;
  return children;
}
