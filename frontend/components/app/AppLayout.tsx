import type { ReactNode } from "react";
import AppSidebar from "./AppSidebar";
import WorkspaceTopBar from "./WorkspaceTopBar";

/**
 * 온보딩 이후 일반 서비스 화면의 공통 셸.
 *   AppLayout
 *   ├ AppSidebar      (데스크톱: 좌측 고정 / 모바일: 하단 네비)
 *   ├ WorkspaceTopBar (얇은 상단 띠 — 지금 어디인지와 오늘 날짜)
 *   └ Content         (각 페이지가 AppHeader + PageContainer 로 구성)
 *
 * 사이드바가 lg 에서 fixed 라서 본문에 같은 폭만큼 왼쪽 여백을 준다.
 */
export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-cream">
      <AppSidebar />
      <div className="min-w-0 pb-[84px] lg:pb-0 lg:ml-[232px]">
        <WorkspaceTopBar />
        {children}
      </div>
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
