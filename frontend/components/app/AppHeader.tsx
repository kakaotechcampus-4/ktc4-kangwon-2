"use client";

import type { ReactNode } from "react";
import { Icon } from "./icons";
import { formatKoreanDate } from "@/lib/greeting";

/**
 * 콘텐츠 영역 상단 헤더. 홈에서는 인사말 + 검색/알림, 계획안 페이지에서는 제목 + 조직 칩.
 * (모바일에서는 세로로 쌓이고 검색창이 full width)
 */
export default function AppHeader({
  title,
  badge,
  description,
  tools,
  date = new Date(),
  divider = true,
}: {
  title: ReactNode;
  badge?: ReactNode;
  description?: ReactNode;
  tools?: ReactNode;
  date?: Date;
  divider?: boolean;
}) {
  return (
    <header className={`flex flex-col lg:flex-row lg:items-start lg:justify-between gap-3.5 lg:gap-5 px-4 pt-[18px] pb-4 lg:px-10 lg:pt-7 lg:pb-[22px] ${divider ? "border-b border-line" : ""}`}>
      <div>
        <div className="font-mono text-[12px] tracking-[.06em] text-ink-soft">{formatKoreanDate(date)}</div>
        <h1 className="font-display text-[22px] lg:text-[26px] text-ink mt-1.5 flex items-center gap-3 flex-wrap">
          {title}
          {badge}
        </h1>
        {description && <p className="text-[13.5px] text-ink-soft mt-1.5">{description}</p>}
      </div>
      {tools && <div className="flex items-center gap-2.5 shrink-0 w-full lg:w-auto">{tools}</div>}
    </header>
  );
}

/** ● 등원 준비 완료 — Main 계열 상태 배지 */
export function StatusBadge({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 font-body text-[12px] font-medium text-sage-ink bg-sage-tint rounded-full px-[11px] py-[5px]">
      <span className="w-1.5 h-1.5 rounded-full bg-sage-ink" aria-hidden="true" />
      {children}
    </span>
  );
}

/** 검색창 + 알림 — 홈 헤더 우측 도구 (UI만, 기능 미연결) */
export function HeaderTools({ placeholder = "기록, 원아, 문서 검색" }: { placeholder?: string }) {
  return (
    <>
      <label className="flex items-center gap-2 flex-1 lg:flex-none lg:w-[250px] min-h-[44px] px-3.5 rounded-[14px] border-[1.5px] border-line bg-paper text-ink-soft">
        <Icon name="search" className="w-[17px] h-[17px] shrink-0" strokeWidth={1.8} />
        <input type="search" placeholder={placeholder} aria-label="검색" className="w-full bg-transparent border-0 outline-none text-[13.5px] text-ink placeholder:text-ink-soft" />
      </label>
      <button type="button" aria-label="알림" className="relative inline-flex items-center justify-center w-11 h-11 rounded-[14px] border-[1.5px] border-line bg-paper text-ink-soft hover:border-sage-ink hover:text-ink transition-colors">
        <Icon name="bell" className="w-[19px] h-[19px]" />
        <span className="absolute top-2.5 right-[11px] w-[7px] h-[7px] rounded-full bg-peach-strong border-[1.5px] border-paper" aria-hidden="true" />
      </button>
    </>
  );
}

export function OrgChip({ children }: { children: ReactNode }) {
  return <span className="text-[13px] px-3 py-[7px] rounded-full bg-paper border border-line text-ink-soft whitespace-nowrap">{children}</span>;
}
