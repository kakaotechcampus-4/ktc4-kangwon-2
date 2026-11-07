import { Suspense, type ReactNode } from "react";
import AppSidebar from "./AppSidebar";
import WorkspaceTopBar from "./WorkspaceTopBar";
import ContentShell from "./ContentShell";
import Tour from "./Tour";

/**
 * 서비스 화면의 공통 셸. 원·반이 없으면 메인 밖은 안내 카드가 대신 뜬다.
 *   AppLayout
 *   ├ AppSidebar      (데스크톱: 좌측 고정 / 모바일: 하단 네비)
 *   ├ WorkspaceTopBar (얇은 상단 띠 — 지금 어디인지와 오늘 날짜)
 *   ├ Content         (각 페이지가 AppHeader + PageContainer 로 구성)
 *   └ Tour            (처음 온 선생님 안내 — 홈 · 관찰 · 일과 · 주간 기록)
 *
 * 사이드바가 lg 에서 fixed 라서 본문에 같은 폭만큼 왼쪽 여백을 준다.
 */
export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-[calc(100*var(--app-vh))] bg-cream">
      <AppSidebar />
      <ContentShell>
        <Suspense fallback={<div className="h-[60px] border-b border-line" />}>
          <WorkspaceTopBar />
        </Suspense>
        {children}
      </ContentShell>
      {/* 처음 온 화면이면 그 화면에서 할 일을 한 칸씩 짚어 준다. 한 번 보면 다시 안 뜬다. */}
      <Tour />
    </div>
  );
}

/** 헤더 아래 콘텐츠 여백을 통일하는 래퍼 */
export function PageContainer({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`px-4 pt-[18px] pb-8 lg:px-10 lg:pt-[26px] lg:pb-12 min-w-0 ${className}`}>
      {children}
    </div>
  );
}
