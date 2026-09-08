import type { ReactNode } from "react";
import Link from "next/link";
import AppSidebar from "./AppSidebar";

/**
 * 온보딩 이후 일반 서비스 화면의 공통 셸.
 *   AppLayout
 *   ├ AppSidebar (데스크톱: 좌측 고정 / 모바일: 하단 네비)
 *   └ Content    (각 페이지가 AppHeader + PageContainer 로 구성)
 * 페이지 배경은 --pg-cream(#F4F8F5), 사이드바/카드는 흰색.
 */
export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[232px_minmax(0,1fr)] bg-cream">
      <AppSidebar />
      <div className="min-w-0 pb-[84px] lg:pb-0">
        {/* 모바일 전용 상단 바 (사이드바 브랜드 영역 대체) */}
        <div className="lg:hidden sticky top-0 z-20 flex items-center justify-between px-4 py-3 bg-paper border-b border-line">
          <Link href="/home" className="flex items-center gap-2">
            <svg width="26" height="26" viewBox="0 0 30 30" aria-hidden="true">
              <circle cx="12" cy="15" r="9" className="fill-sage" />
              <circle cx="20" cy="10" r="6" className="fill-sage-ink" />
            </svg>
            <span className="font-display text-lg text-ink">새싹플랜</span>
          </Link>
          <Link href="/onboarding" aria-label="내 정보" className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-sage-tint text-sage-ink font-bold text-[13px]">김</Link>
        </div>
        {children}
      </div>
    </div>
  );
}

/** 헤더 아래 콘텐츠 여백을 통일하는 래퍼 */
export function PageContainer({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`px-4 pt-[18px] pb-8 lg:px-10 lg:pt-[26px] lg:pb-12 min-w-0 ${className}`}>{children}</div>;
}
