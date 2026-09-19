"use client";

import { useEffect, useState, type ReactNode } from "react";
// MSW는 NODE_ENV와 무관하게 이 환경변수 하나로만 켜고 끈다.
// enabled  → 로컬/Vercel Preview/Production 모두에서 MSW 실행 (백엔드 없이 데모 가능)
// disabled 또는 미설정 → MSW를 시작하지 않고 기존 FastAPI 연결 구조 사용
// NEXT_PUBLIC_*는 빌드 시점에 값이 박히므로 값 변경 후에는 재빌드/재배포가 필요하다.
const enabled = process.env.NEXT_PUBLIC_API_MOCKING === "enabled";

export default function MockProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(!enabled);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    // 배포본에서 스위치 상태를 바로 확인할 수 있도록 남기는 최소 로그.
    console.info("[MSW] mocking:", process.env.NEXT_PUBLIC_API_MOCKING ?? "(unset)");
    if (!enabled) return;
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
