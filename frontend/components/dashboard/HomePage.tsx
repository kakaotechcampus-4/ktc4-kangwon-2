"use client";

/**
 * 새싹플랜 · 홈(메인) — Sidebar + Main Content + Right Panel
 *  중앙: 인사말 헤더 → TODAY'S FOCUS 3카드
 *  우측: 오늘의 등원 인원 → 달력 → 최근 기록
 *  모바일: 헤더 → 할 일 → 등원 현황 → 최근 기록 → 달력 순으로 세로 reflow
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import AppHeader, { HeaderTools, StatusBadge } from "@/components/app/AppHeader";
import DashboardTaskCard from "./DashboardTaskCard";
import AttendanceSummary from "./AttendanceSummary";
import CalendarCard from "./CalendarCard";
import RecentRecordList from "./RecentRecordList";
import { RECENT_RECORDS, TODAY_ATTENDANCE, TODAY_TASKS } from "@/lib/dashboard/mock";
import { greetingFor } from "@/lib/greeting";

const WELCOME_KEY = "saessak.welcome";

export default function HomePage() {
  const [now] = useState(() => new Date());
  const [welcome, setWelcome] = useState(false);

  // 온보딩 직후 1회만 보이는 완료 안내 (sessionStorage 플래그)
  useEffect(() => {
    try {
      setWelcome(sessionStorage.getItem(WELCOME_KEY) === "1");
    } catch { /* noop */ }
  }, []);
  function closeWelcome() {
    setWelcome(false);
    try { sessionStorage.removeItem(WELCOME_KEY); } catch { /* noop */ }
  }

  return (
    <>
      <AppHeader title={greetingFor(now)} badge={<StatusBadge>등원 준비 완료</StatusBadge>} tools={<HeaderTools />} date={now} />

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_352px] xl:grid-cols-[minmax(0,1fr)_352px] min-h-[calc(100vh-110px)]">
        {/* 중앙 */}
        <section className="min-w-0 flex flex-col gap-[18px] px-4 pt-[18px] pb-2 lg:px-10 lg:pt-[26px] lg:pb-12">
          {welcome && (
            <div className="flex items-center gap-3 rounded-[18px] border border-line bg-sage-tint px-4 py-3 text-[13.5px] text-ink">
              <span aria-hidden="true">🌱</span>
              <span><b className="text-sage-ink">우리 반 설정이 완료되었어요.</b> 계획안 생성 화면에 반 정보와 연령이 기본값으로 적용돼요.</span>
              <button type="button" onClick={closeWelcome} className="ml-auto min-h-9 px-2.5 rounded-full text-[12.5px] text-ink-soft hover:bg-paper hover:text-ink">닫기</button>
            </div>
          )}
          <div>
            <div className="font-mono text-[11px] tracking-[.12em] text-ink-soft">TODAY&apos;S FOCUS</div>
            <div className="flex items-baseline justify-between gap-3 mt-1">
              <h2 className="font-display text-[20px] text-ink">
                오늘의 할 일<span className="font-mono text-[14px] text-ink-soft ml-1.5">{TODAY_TASKS.reduce((n, t) => n + t.count, 0)}</span>
              </h2>
              <Link href="/home" className="text-[13px] text-ink-soft hover:text-sage-ink">전체 보기 →</Link>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {TODAY_TASKS.map((t) => <DashboardTaskCard key={t.id} task={t} />)}
          </div>
        </section>

        {/* 우측 패널 — 모바일에서는 등원 → 최근 기록 → 달력 순 */}
        <aside className="min-w-0 flex flex-col gap-[22px] bg-paper border-t lg:border-t-0 lg:border-l border-line px-4 pt-5 pb-7 lg:px-[26px] lg:pt-[26px] lg:pb-10">
          <div className="order-1"><AttendanceSummary data={TODAY_ATTENDANCE} /></div>
          <div className="hidden lg:block h-px bg-line order-2" />
          <div className="order-3 lg:order-3"><CalendarCard today={now} /></div>
          <div className="hidden lg:block h-px bg-line order-4" />
          <div className="order-2 lg:order-5"><RecentRecordList records={RECENT_RECORDS} /></div>
        </aside>
      </div>
    </>
  );
}
