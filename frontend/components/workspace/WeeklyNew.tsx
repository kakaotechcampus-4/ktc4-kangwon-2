"use client";

/**
 * 주간계획안 만들기(Ⓦ1) — 월간과 같은 틀. 달 12칸(월간을 확정한 달만 열림), 그 달의 주
 * (확정한 주는 잠김, 작성 중인 주는 누르면 그 초안으로), 월간에서 이어받는 그 주 내용,
 * 오른쪽 주간 양식 미리보기. 만드는 동안은 원형 화면(Ⓦ2). 놀이 중심형은 주간이 없다.
 */

import { useEffect, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { ApiError } from "@/lib/api/client";
import { existingAfterConflict } from "@/lib/api/conflict";
import { memoError, PlanMemoField } from "@/components/plan-generator/PlanMemo";
import { getMonthlyPlan, listMonthlyPlans } from "@/lib/api/monthly";
import { listAnnualPlans } from "@/lib/api/plans";
import { newRunId } from "@/lib/api/generationRuns";
import { createWeeklyPlan, listWeeklyPlans } from "@/lib/api/weekly";
import { syncClass } from "@/lib/api/onboarding";
import type { MonthlyPlan, WeeklyPlanSummary } from "@/lib/api/types";
import { isPlayAnnual } from "@/lib/monthly/play-entry";
import { sectionName } from "@/lib/monthly/section-labels";
import { chosenClassFor, loadClassSettings } from "@/lib/onboarding/settings";
import { MONTH_ORDER, planClassLine } from "@/lib/onboarding/types";
import { useClientState } from "@/lib/hooks/use-client-state";
import { topicMemo } from "@/lib/api/trends";
import GenerationRing, { ringFinished, STOPPED_NOTE } from "@/components/plan-ui/GenerationRing";
import { useCompactShell } from "@/components/app/compact-shell";
import { BACK_BUTTON, BACK_ICON } from "@/components/plan-generator/AnnualFrame";
import { Tape, useClasses } from "./WorkspaceUI";
import WeeklySheet, { BLANK_SECTIONS } from "./WeeklySheet";

type Monthlies = Record<number, { id: number; status: "DRAFT" | "CONFIRMED" }>;
type Week = MonthlyPlan["weeks"][number];
export type Opened = { id: number; classId: number; month: number; weekId: string };

/** 처음 고를 달: 주소의 달 → 이번 달(월간 확정) → 학년도 순서로 마지막 확정 달 → 이번 달. */
export function firstWeeklyMonth(now: number, monthlies: Monthlies, asked?: number | null) {
  if (asked && asked >= 1 && asked <= 12) return asked;
  if (monthlies[now]?.status === "CONFIRMED") return now;
  return MONTH_ORDER.filter((m) => monthlies[m]?.status === "CONFIRMED").at(-1) ?? now;
}

/** 처음 고를 주: 아직 계획안이 없는 첫 주, 다 있으면 첫 주. */
export function firstOpenWeek(weeks: Week[], plans: WeeklyPlanSummary[]) {
  return (weeks.find((w) => !plans.some((p) => p.week_id === w.week_id)) ?? weeks[0])?.week_id;
}

/** 월간에서 그 주로 이어받는 것 — 생활주제(주별 아닌 첫 칸) + 그 주 칸들(빈 칸 빼고). */
export function inheritWeek(monthly: MonthlyPlan, weekId: string) {
  const sections = monthly.sections
    .filter((s) => s.visible && s.role === "CONTENT")
    .sort((a, b) => a.order - b.order);
  const theme = sections.find((s) => s.section_key === "theme")?.cells[0]?.value ?? "";
  const rows = sections
    .filter((s) => s.repeat_by === "WEEK")
    .flatMap((s) => {
      // 후보 방식 안전교육은 칸이 비어 있고 서버가 그 주 표시값을 준다 — 주간 Core 도 이 값을 복사한다.
      const placed =
        s.section_key === "safety_education"
          ? monthly.safety_weeks?.find((w) => w.week_id === weekId)?.display_value
          : undefined;
      const value = placed?.trim()
        ? placed
        : (s.cells.find((c) => c.week_id === weekId)?.value ?? "");
      return value.trim() ? [{ name: sectionName(s.section_key, s.label), value }] : [];
    });
  return { theme, rows };
}

const md = (iso: string) => `${Number(iso.slice(5, 7))}.${Number(iso.slice(8, 10))}`;

type Loaded = { classId: number; play: boolean; monthlies: Monthlies };
type MonthData = { month: number; monthly: MonthlyPlan | null; plans: WeeklyPlanSummary[] };

export default function WeeklyNew({ onOpen }: { onOpen: (plan: Opened) => void }) {
  const [problem, setProblem] = useState("");
  const [stopped, setStopped] = useState(false);
  // 트렌드 화면 [계획안에 활용하기] 가 `?topic` 으로 넘긴 글을 요청 사항 첫 값으로 둔다(ADR-072).
  const [memo, setMemo] = useClientState(
    () => topicMemo(typeof window === "undefined" ? "" : window.location.search),
    "",
  );
  const [memoProblem, setMemoProblem] = useState<string | null>(null);
  const classes = useClasses(setProblem);
  const [chosen] = useClientState(() => chosenClassFor(loadClassSettings())?.id ?? "", "");
  // 계획안 첫 화면 단추로 들어왔으면(`?from=plans`) 「←」는 첫 화면으로 돌아간다.
  const [fromPlans] = useClientState(
    () =>
      typeof window !== "undefined" &&
      new URLSearchParams(window.location.search).get("from") === "plans",
    false,
  );
  const local = classes.find((c) => c.id === chosen) ?? classes[0];
  const [data, setData] = useState<Loaded | null>(null);
  const [month, setMonth] = useState<number | null>(null);
  const [detail, setDetail] = useState<MonthData | null>(null);
  const [weekId, setWeekId] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  // 이번 생성 POST 의 헤더와 링이 같은 값을 쓴다 — 요청마다 새로 만든다(api-spec §9-8).
  const [runId, setRunId] = useState<string>();
  const controller = useRef<AbortController | null>(null);
  useCompactShell(busy);
  useEffect(() => () => controller.current?.abort(), []);

  useEffect(() => {
    let alive = true;
    (async () => {
      const settings = loadClassSettings();
      if (!settings || !local) return;
      try {
        const classId = await syncClass(settings, local);
        const [annual, list] = await Promise.all([
          listAnnualPlans(classId).catch(() => null),
          listMonthlyPlans(classId),
        ]);
        const monthlies: Monthlies = Object.fromEntries(
          list.items.map((p) => [p.month, { id: p.id, status: p.status }]),
        );
        if (!alive) return;
        setData({ classId, play: isPlayAnnual(annual), monthlies });
        const asked = Number(new URLSearchParams(window.location.search).get("month"));
        setMonth((m) => m ?? firstWeeklyMonth(new Date().getMonth() + 1, monthlies, asked));
      } catch (e) {
        if (alive) setProblem(e instanceof Error ? e.message : "불러오지 못했어요.");
      }
    })();
    return () => {
      alive = false;
    };
  }, [local]);

  // 고른 달의 확정 월간 · 그 달 주간 목록.
  useEffect(() => {
    if (!data || month === null) return;
    const found = data.monthlies[month];
    let alive = true;
    (async () => {
      try {
        const [monthly, list] = await Promise.all([
          found?.status === "CONFIRMED" ? getMonthlyPlan(found.id) : null,
          listWeeklyPlans(data.classId, month),
        ]);
        if (!alive) return;
        setDetail({ month, monthly, plans: list.items });
        const weeks = monthly?.weeks.filter((w) => w.active) ?? [];
        setWeekId(firstOpenWeek(weeks, list.items) ?? "");
      } catch (e) {
        if (alive) setProblem(e instanceof Error ? e.message : "불러오지 못했어요.");
      }
    })();
    return () => {
      alive = false;
    };
  }, [data, month]);

  if (!data || month === null)
    return problem ? (
      <p role="alert" className="m-7">
        {problem}
      </p>
    ) : (
      <p role="status" className="m-7">
        주간계획안을 불러오는 중…
      </p>
    );

  const { classId, monthlies } = data;
  const ready = detail?.month === month ? detail : null;
  const monthly = ready?.monthly ?? null;
  const plans = ready?.plans ?? [];
  const weeks = monthly?.weeks.filter((w) => w.active) ?? [];
  const week = weeks.find((w) => w.week_id === weekId);
  const mine = plans.find((p) => p.week_id === weekId);
  const inherit = monthly && week ? inheritWeek(monthly, week.week_id) : null;
  const open = (id: number, w: string) => onOpen({ id, classId, month, weekId: w });
  const draft = monthlies[month];

  const blocked: ReactNode = data.play ? (
    <>
      놀이 중심형은 주간계획안 없이 월간계획안으로 운영해요.{" "}
      <Link href={memo ? `/plans/monthly?topic=${encodeURIComponent(memo)}` : "/plans/monthly"}>
        월간계획안으로 가기
      </Link>
    </>
  ) : !ready ? (
    "불러오는 중…"
  ) : !monthly ? (
    <>
      {month}월 월간계획안을 확정해야 주간을 만들 수 있어요.{" "}
      <Link
        href={
          draft
            ? `/plans/monthly?plan_id=${draft.id}&class_id=${classId}&month=${month}`
            : "/plans/monthly"
        }
        className="font-bold text-[#5e4b96]"
      >
        {draft ? `${month}월 월간계획안 열기` : "월간계획안 만들기"}
      </Link>
    </>
  ) : !week ? (
    "만들 주를 골라 주세요."
  ) : mine?.status === "CONFIRMED" ? (
    "이 주는 확정했어요. 문서 보관함에서 볼 수 있어요."
  ) : null;

  async function create() {
    if (busy || !week) return;
    if (mine) return open(mine.id, week.week_id);
    controller.current?.abort();
    const ctl = new AbortController();
    controller.current = ctl;
    const id = newRunId();
    setRunId(id);
    setBusy(true);
    setDone(false);
    setProblem("");
    setStopped(false);
    setMemoProblem(null);
    try {
      const plan = await createWeeklyPlan(
        {
          class_id: classId,
          week_id: week.week_id,
          activity_candidates: true,
          indoor_play_candidates: true,
          ...(memo.trim() ? { memo: memo.trim() } : {}),
        },
        ctl.signal,
        id,
      );
      if (ctl.signal.aborted) return;
      setDone(true);
      await ringFinished();
      open(plan.id, week.week_id);
    } catch (e) {
      // 취소했거나 새 요청이 시작됐으면 이 요청은 화면을 바꾸지 않는다(새 요청의 busy 도 풀지 않는다).
      const stale = () => ctl.signal.aborted || controller.current !== ctl;
      if (stale()) return;
      // 그 주가 이미 있으면(409) 목록을 다시 읽어 그 초안으로 간다 — 읽는 동안 화면은 잠근 채로 둔다.
      if (e instanceof ApiError && e.status === 409) {
        const found = await existingAfterConflict(
          () => listWeeklyPlans(classId, month!),
          (p) => p.week_id === week.week_id,
          stale,
        );
        if (stale()) return;
        if (found !== null) return open(found, week.week_id);
      }
      setBusy(false);
      const memoMessage = memoError(e);
      if (memoMessage) setMemoProblem(memoMessage);
      else setProblem(e instanceof Error ? e.message : "주간계획안을 만들지 못했어요.");
    }
  }

  // 주 이름은 「11월 4주」처럼 달까지 붙어 온다.
  const label = week ? week.label : `${month}월`;

  if (busy)
    return (
      <div className="flex min-h-[calc(calc(100*var(--app-vh))-60px)]">
        <GenerationRing
          title={`${label} 주간계획안을 만들고 있어요`}
          runId={runId}
          done={done}
          steps={[
            ["prepare", `${label} 놀이 이어받기`],
            ["generate", "요일별 활동 나누기"],
            ["check", "살펴보고 다듬기"],
            ["save", "문서로 정리하기"],
          ]}
          onCancel={() => {
            controller.current?.abort();
            setBusy(false);
            setStopped(true);
          }}
        />
      </div>
    );

  return (
    <div className="flex w-full flex-col gap-4 px-10 pb-6 pt-[26px] text-[#2b2826] lg:h-[calc(calc(100*var(--app-vh))-60px)]">
      <div className="relative grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
        <Tape />
        <section className="flex min-h-0 min-w-0 flex-col gap-5 overflow-y-auto bg-paper shadow-pg p-7">
          {/* 왼쪽 판 맨 위: 제목 앞 「←」 돌아가기(편집 화면과 같은 버튼) · 방식. */}
          <div className="flex shrink-0 flex-col">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <Link
                href={
                  fromPlans
                    ? "/plans"
                    : draft
                      ? `/plans/monthly?plan_id=${draft.id}&class_id=${classId}&month=${month}`
                      : "/plans/monthly"
                }
                aria-label={`돌아가기: ${fromPlans ? "계획안" : `${month}월 월간계획안`}`}
                title={fromPlans ? "계획안" : `${month}월 월간계획안`}
                className={BACK_BUTTON}
              >
                {BACK_ICON}
              </Link>
              <h1 className="penMark m-0 font-display text-[34px] font-bold leading-[1.2] text-ink">
                주간계획안 만들기
              </h1>
              <span className="-rotate-2 border border-black/10 bg-[#e8f1ea] px-3 py-0.5 font-display text-[18px] font-bold text-[#3b5441] shadow-pg-card">
                월별 주제형
              </span>
            </div>
          </div>

          <div className="flex shrink-0 flex-col gap-2.5">
            <h2 className="m-0 font-display text-[24px] font-bold leading-tight text-ink">
              어느 달의 주간을 만들까요?
            </h2>
            <div role="radiogroup" aria-label="달" className="grid grid-cols-6 gap-1.5">
              {MONTH_ORDER.map((m) => {
                const done = monthlies[m]?.status === "CONFIRMED";
                const sel = m === month;
                return (
                  <button
                    key={m}
                    type="button"
                    role="radio"
                    aria-checked={sel}
                    onClick={() => setMonth(m)}
                    className={`flex min-h-[46px] flex-col items-center justify-center rounded-md border text-[15px] leading-tight ${
                      sel
                        ? "border-[#7053a0] bg-[#f6f1fb] font-bold text-[#4a3780]"
                        : done
                          ? "border-[#e8e2d8] hover:border-[#c5b7dd]"
                          : "border-transparent bg-[#f3efe8] text-[#8a8178]"
                    }`}
                  >
                    {m}월
                    {done && (
                      <span className="text-[11px] font-bold text-[#3b5441]">월간 확정</span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {weeks.length > 0 && (
            <div className="flex shrink-0 flex-col gap-2.5">
              <h2 className="m-0 font-display text-[24px] font-bold leading-tight text-ink">
                어느 주를 만들까요?
              </h2>
              <div role="radiogroup" aria-label="주" className="grid grid-cols-2 gap-1.5">
                {weeks.map((w) => {
                  const p = plans.find((x) => x.week_id === w.week_id);
                  const sel = w.week_id === weekId;
                  return (
                    <button
                      key={w.week_id}
                      type="button"
                      role="radio"
                      aria-checked={sel}
                      disabled={p?.status === "CONFIRMED"}
                      onClick={() => (p ? open(p.id, w.week_id) : setWeekId(w.week_id))}
                      className={`flex min-h-[52px] items-center justify-between gap-2 rounded-md border px-4 text-left text-[15px] ${
                        sel
                          ? "border-[#7053a0] bg-[#f6f1fb] font-bold text-[#4a3780]"
                          : p?.status === "CONFIRMED"
                            ? "border-transparent bg-[#f3efe8] text-[#8a8178]"
                            : "border-[#e8e2d8] hover:border-[#c5b7dd]"
                      }`}
                    >
                      <span>
                        {w.label}
                        <span className="ml-2 text-[13px] font-normal text-[#5c5243]">
                          {md(w.start_date)} ~ {md(w.end_date)}
                        </span>
                      </span>
                      {p?.status === "CONFIRMED" && (
                        <span className="text-[11px] font-bold text-[#3b5441]">✓ 확정</span>
                      )}
                      {p?.status === "DRAFT" && (
                        <span className="text-[11px] font-bold text-[#7053a0]">작성 중</span>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {inherit && week && (
            <div className="flex shrink-0 flex-col gap-2.5">
              <div className="flex items-baseline justify-between">
                <h2 className="m-0 font-display text-[24px] font-bold leading-tight text-ink">
                  월간에서 이어받아요
                </h2>
              </div>
              <div className="rounded-md bg-[#f7f4ee] px-4 py-3">
                <div className="text-[17px] font-bold">{inherit.theme || "생활주제 없음"}</div>
                <dl className="m-0 mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[14px]">
                  {inherit.rows.map((r) => (
                    <div key={r.name} className="contents">
                      <dt className="text-xs font-bold leading-6 text-[#3b5441]">{r.name}</dt>
                      <dd className="m-0 whitespace-pre-line">{r.value}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            </div>
          )}

          {!mine && (
            <PlanMemoField
              value={memo}
              onChange={setMemo}
              error={memoProblem}
              chips={["바깥놀이 많이", "비 오는 날 대체활동", "요일별 활동 고르게"]}
              placeholder="예) 수요일은 견학이 있어 오전 활동을 짧게"
            />
          )}

          {stopped && STOPPED_NOTE}
          {problem && (
            <p
              role="alert"
              className="m-0 rounded-md bg-[#fbeaea] px-4 py-3 text-sm text-[#8a2f2f]"
            >
              {problem}
            </p>
          )}

          {/* 만들기 단추는 화면 아래에 붙여 둔다 — 낮은 화면(1440×900)에서도 스크롤 없이 보이게.
              카드 아래 여백(p-7)까지 덮고 위를 흐리게 해, 뒤에 지나가는 글이 단추 아래로 비치지 않는다. */}
          <div className="sticky -bottom-7 z-10 -mb-7 mt-auto flex shrink-0 flex-col gap-2 bg-paper pb-7 pt-3 before:pointer-events-none before:absolute before:inset-x-0 before:-top-6 before:h-6 before:bg-gradient-to-b before:from-transparent before:to-paper">
            <button
              type="button"
              onClick={() => void create()}
              disabled={!!blocked}
              className="min-h-[54px] rounded-md bg-primary hover:bg-primary-hover text-[17px] font-bold text-white disabled:cursor-not-allowed disabled:bg-[#ddd6ca] disabled:text-ink-soft transition-transform active:translate-x-[2px] active:translate-y-[3px] active:shadow-none"
            >
              {mine ? `${label} 주간계획안 열기` : `${label} 주간계획안 만들기`}
            </button>
            {blocked && <p className="m-0 text-sm text-[#5c5243]">{blocked}</p>}
          </div>
        </section>

        <section
          aria-label="양식 미리보기"
          className="flex min-h-[420px] min-w-0 flex-col border border-shell-line bg-shell-hover shadow-[inset_0_1px_4px_rgba(52,49,47,0.08)] p-3"
        >
          <div className="min-h-0 flex-1 overflow-y-auto">
            <WeeklySheet
              title={`${month ? month + "월 " : ""}${week?.label ?? "1주"} 주간놀이계획안`}
              sub={local ? planClassLine(local) : ""}
              start={week?.start_date ?? ""}
              end={week?.end_date ?? ""}
              days={["MON", "TUE", "WED", "THU", "FRI"]}
              sections={BLANK_SECTIONS}
              at={{ selected: null }}
            />
          </div>
        </section>
      </div>
    </div>
  );
}
