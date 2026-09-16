"use client";

/**
 * 쓱싹요정 · 홈(메인) — Sidebar + Main Content + Right Panel
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
import { TODAY_TASKS } from "@/lib/dashboard/mock";
import {
  CLASS_SETTINGS_CHANGED,
  loadClassSettings,
  totalChildrenFor,
} from "@/lib/onboarding/settings";
import { greetingFor } from "@/lib/greeting";
import { useWorkspace } from "@/lib/workspace/store";
import { ws } from "@/components/workspace/WorkspaceUI";
import { useClientState } from "@/lib/hooks/use-client-state";

const WELCOME_KEY = "saessak.welcome";

export default function HomePage() {
  const { data, error } = useWorkspace();
  const tasks = TODAY_TASKS.map((task) =>
    task.id === "records"
      ? {
          ...task,
          count: data.observations.length,
          description: "교사가 남긴 실제 관찰 기록을 확인해 주세요.",
          href: "/records",
        }
      : task.id === "drafts"
        ? {
            ...task,
            count: data.documents.filter((d) => d.status === "draft").length,
            href: "/documents",
          }
        : {
            ...task,
            title: "평가제·증빙 점검",
            description: "문서의 항목과 증빙 연결을 확인해 주세요.",
            count: data.documents.filter((d) => d.status === "confirmed").length,
            href: "/evaluation",
            cta: "증빙 점검",
          },
  );
  const recentRecords = data.observations
    .slice(0, 4)
    .map((r) => ({ id: r.id, childName: r.childName, text: r.fact, status: "review" as const }));
  const [now] = useState(() => new Date());
  // 온보딩 직후 1회만 보이는 완료 안내 (sessionStorage 플래그)
  const [welcome, setWelcome] = useClientState(() => {
    try {
      return sessionStorage.getItem(WELCOME_KEY) === "1";
    } catch {
      return false;
    }
  }, false);
  const [totalChildren, setTotalChildren] = useState<number | null>(null);

  useEffect(() => {
    const refresh = () => setTotalChildren(totalChildrenFor(loadClassSettings()));
    refresh();
    window.addEventListener(CLASS_SETTINGS_CHANGED, refresh);
    window.addEventListener("storage", refresh);
    window.addEventListener("focus", refresh);
    return () => {
      window.removeEventListener(CLASS_SETTINGS_CHANGED, refresh);
      window.removeEventListener("storage", refresh);
      window.removeEventListener("focus", refresh);
    };
  }, []);

  function closeWelcome() {
    setWelcome(false);
    try {
      sessionStorage.removeItem(WELCOME_KEY);
    } catch {
      /* noop */
    }
  }

  return (
    <>
      <AppHeader
        title={greetingFor(now)}
        badge={<StatusBadge>등원 준비 완료</StatusBadge>}
        tools={<HeaderTools />}
        date={now}
      />

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_352px] xl:grid-cols-[minmax(0,1fr)_352px] min-h-[calc(100vh-110px)]">
        {/* 중앙 */}
        <section className="min-w-0 flex flex-col gap-[18px] px-4 pt-[18px] pb-2 lg:px-10 lg:pt-[26px] lg:pb-12">
          {welcome && (
            <div className="flex items-center gap-3 rounded-[18px] border border-line bg-sage-tint px-4 py-3 text-[13.5px] text-ink">
              <span aria-hidden="true">🌱</span>
              <span>
                <b className="text-sage-ink">우리 반 설정이 완료되었어요.</b> 계획안 생성 화면에 반
                정보와 연령이 기본값으로 적용돼요.
              </span>
              <button
                type="button"
                onClick={closeWelcome}
                className="ml-auto min-h-9 px-2.5 rounded-full text-[12.5px] text-ink-soft hover:bg-paper hover:text-ink"
              >
                닫기
              </button>
            </div>
          )}
          <div>
            <div className="font-mono text-[11px] tracking-[.12em] text-ink-soft">
              TODAY&apos;S FOCUS
            </div>
            <div className="flex items-baseline justify-between gap-3 mt-1">
              <h2 className="font-display text-[20px] text-ink">
                오늘의 기록과 문서
                <span className="font-mono text-[14px] text-ink-soft ml-1.5">
                  {tasks.reduce((n, t) => n + t.count, 0)}
                </span>
              </h2>
              <Link href="/documents" className="text-[13px] text-ink-soft hover:text-sage-ink">
                문서 보기 →
              </Link>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {tasks.map((t) => (
              <DashboardTaskCard key={t.id} task={t} />
            ))}
          </div>
          {error && (
            <p role="alert" className={ws.error}>
              {error}
            </p>
          )}
          <section className={ws.hero}>
            <div>
              <div className={ws.eyebrow}>쓱싹요정 · 선생님의 하루를 잇다</div>
              <h2>
                관찰에서 계획으로,
                <br />
                기록에서 다음 지원으로.
              </h2>
              <p>우리 원 양식과 새로운 놀이 아이디어를 연결해보세요.</p>
            </div>
          </section>
          <div className={ws.cards}>
            {[
              ["/templates", "▤", "원 양식 분석", "기존 문서의 구조와 문체를 계획안에 활용해요."],
              [
                "/plans/annual/new",
                "▦",
                "연간·월간·주간 계획안",
                "우리 반에 맞는 놀이 흐름을 준비해요.",
              ],
              ["/trends", "✳", "트렌드봇", "공식 교육 자료에서 다음 놀이의 힌트를 찾아요."],
              ["/compare", "↗", "기록 간 비교", "아동의 이전과 현재 기록을 나란히 살펴봐요."],
            ].map(([href, icon, title, description]) => (
              <Link key={href} href={href} className={ws.card}>
                <span className={ws.badge}>{icon}</span>
                <h3 style={{ marginTop: 15 }}>{title}</h3>
                <p className={ws.muted}>{description}</p>
                <span className={ws.source}>시작하기 →</span>
              </Link>
            ))}
          </div>
        </section>

        {/* 우측 패널 — 모바일에서는 등원 → 최근 기록 → 달력 순 */}
        <aside className="min-w-0 flex flex-col gap-[22px] bg-paper border-t lg:border-t-0 lg:border-l border-line px-4 pt-5 pb-7 lg:px-[26px] lg:pt-[26px] lg:pb-10">
          <div className="order-1">
            {totalChildren === null ? (
              <p role="status" className={ws.hint}>
                원아 수를 불러오는 중이에요.
              </p>
            ) : (
              <AttendanceSummary
                data={{ total: totalChildren, present: totalChildren, absent: 0 }}
              />
            )}
          </div>
          <div className="hidden lg:block h-px bg-line order-2" />
          <div className="order-3 lg:order-3">
            <CalendarCard today={now} />
          </div>
          <div className="hidden lg:block h-px bg-line order-4" />
          <div className="order-2 lg:order-5">
            <RecentRecordList records={recentRecords} />
            {!recentRecords.length && (
              <p className={ws.hint}>첫 관찰 기록을 남기면 여기에 표시돼요.</p>
            )}
          </div>
        </aside>
      </div>
    </>
  );
}
