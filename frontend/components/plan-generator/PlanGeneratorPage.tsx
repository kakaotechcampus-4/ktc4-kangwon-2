"use client";

/** 기관 양식과 입력 조건으로 계획안을 생성하고, 로딩·편집·저장 흐름을 연결합니다. */

import { useRouter } from "next/navigation";
import { selectedAgesFor, ageSelectionLabel, type SelectedAge } from "@/lib/onboarding/types";
import { saveAnnualContext } from "@/lib/plan-generator/context";
import { useEffect, useMemo, useRef, useState } from "react";
import { fontClassName } from "@/lib/fonts";
import AppHeader from "@/components/app/AppHeader";
import { createAnnualPlan } from "@/lib/api/plans";
import { syncClass } from "@/lib/api/onboarding";
import GenerationFlow from "./GenerationFlow";
import { useWorkspace } from "@/lib/workspace/store";
import { requestAI } from "@/lib/workspace/ai-client";
import { templatePlan, type PlanContent } from "@/lib/workspace/plans";
import { today, type Section } from "@/lib/workspace/model";
import { useAIStatus, ws } from "@/components/workspace/WorkspaceUI";
import {
  PLAN_TYPE_HELP,
  PLAN_TYPE_LABEL,
  type AgeGroup,
  type GenerationPhase,
  type PeriodState,
  type PlanType,
} from "@/lib/plan-generator/types";
import { loadClassSettings, primaryClassFor } from "@/lib/onboarding/settings";
import { isValidDate } from "@/lib/plan-generator/date";

const PLAN_TYPES: PlanType[] = ["annual", "monthly", "weekly", "daily"];
const ACCENT: Record<PlanType, { text: string; tint: string; ink: string }> = {
  annual: { text: "text-sage-ink", tint: "bg-sage-tint", ink: "text-sage-ink" },
  monthly: { text: "text-sage-ink", tint: "bg-sage-tint", ink: "text-sage-ink" },
  weekly: { text: "text-mint-strong", tint: "bg-mint-tint", ink: "text-mint-ink" },
  daily: { text: "text-peach-strong", tint: "bg-peach-tint", ink: "text-peach-ink" },
};

const SUGGESTIONS = [
  {
    emoji: "🍂",
    label: "가을 자연물 놀이",
    text: "가을 자연물(낙엽, 열매)을 활용한 놀이 활동을 중심으로 작성해주세요.",
    tone: "peach" as const,
  },
  {
    emoji: "🎨",
    label: "실외+미술 활동",
    text: "실외활동과 미술활동을 포함해주세요.",
    tone: "mint" as const,
  },
];

/**
 * @param embedded  true 면 AppLayout(사이드바) 안에서 렌더된다는 뜻.
 *                  자체 브랜드 헤더 대신 공통 AppHeader(페이지 제목)를 쓰고, 나머지 레이아웃/디자인은 그대로.
 */
/** URL 쿼리와 온보딩에 저장된 반 설정 — 마운트 시 한 번만 읽는다(서버 렌더에서는 빈 값). */
function readStartup() {
  if (typeof window === "undefined")
    return { memo: "", templateId: "", ages: [] as SelectedAge[], className: "", classId: "" };
  const params = new URLSearchParams(window.location.search);
  const primary = primaryClassFor(loadClassSettings());
  return {
    memo: params.get("topic")?.slice(0, 5000) ?? "",
    templateId: params.get("template") ?? "",
    ages: primary ? selectedAgesFor(primary) : [],
    className: primary?.className ?? "",
    classId: primary?.id ?? "",
  };
}

export default function PlanGeneratorPage({ embedded = false }: { embedded?: boolean } = {}) {
  const router = useRouter();
  const [startup] = useState(readStartup);
  const [age, setAge] = useState<AgeGroup | "">(
    startup.ages.length === 1
      ? (String(startup.ages[0]) as AgeGroup)
      : startup.ages.length
        ? "mixed"
        : "",
  );
  // 온보딩에서 읽은 실제 연령([3,5] 등)은 표시용으로 보존한다. 화면 UI는 기존 드롭다운 그대로.
  const onboardingAges = useRef<SelectedAge[]>(startup.ages);
  const [planTypes, setPlanTypes] = useState<Set<PlanType>>(new Set());
  const [period, setPeriod] = useState<PeriodState>({
    annual: { year: new Date().getFullYear() },
    monthly: { month: new Date().getMonth() + 1 },
    weekly: { month: new Date().getMonth() + 1, week: 1 },
    daily: { date: today() },
  });
  const [memo, setMemo] = useState(startup.memo);
  const [phase, setPhase] = useState<GenerationPhase>("idle");
  const [stepIndex, setStepIndex] = useState(0);
  const className = startup.className;
  const classId = startup.classId;
  const [templateId, setTemplateId] = useState(startup.templateId);
  const [error, setError] = useState("");
  const [contents, setContents] = useState<Partial<Record<PlanType, PlanContent>>>({});
  const { data: workspace, error: storageError } = useWorkspace();
  const available = useAIStatus();
  const controllerRef = useRef<AbortController | null>(null);
  const [generated, setGenerated] = useState<{
    age: AgeGroup;
    selectedTypes: PlanType[];
    period: PeriodState;
    memo: string;
  } | null>(null);

  useEffect(() => () => controllerRef.current?.abort(), []);

  const canGenerate =
    available !== null &&
    phase !== "generating" &&
    age !== "" &&
    planTypes.size > 0 &&
    Number.isInteger(period.annual.year) &&
    period.annual.year >= 2000 &&
    period.annual.year <= 2100 &&
    (!planTypes.has("daily") || isValidDate(period.daily.date));
  const selectedTypes = useMemo(() => PLAN_TYPES.filter((t) => planTypes.has(t)), [planTypes]);

  const stageRef = useRef<HTMLElement | null>(null);

  function toggleType(t: PlanType) {
    setPlanTypes((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });
  }

  function updatePeriod<K extends keyof PeriodState>(key: K, value: PeriodState[K]) {
    setPeriod((prev) => {
      const next = { ...prev, [key]: value };
      const maxWeeks = Math.ceil(new Date(next.annual.year, next.weekly.month, 0).getDate() / 7);
      return { ...next, weekly: { ...next.weekly, week: Math.min(next.weekly.week, maxWeeks) } };
    });
  }

  async function handleGenerate() {
    if (!canGenerate) return;
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    // [3,5]처럼 비연속 선택은 "mixed" 한 값으로 줄이면 4세가 섞인 것으로 읽힌다.
    // 드롭다운 값(age)은 그대로 두고 실제 선택 연령을 함께 넘긴다.
    const exactAges =
      age === "mixed" && onboardingAges.current.length > 1 ? [...onboardingAges.current] : null;
    const request = {
      age,
      ageLabel: exactAges ? ageSelectionLabel(exactAges) : undefined,
      selectedTypes: [...selectedTypes],
      period: structuredClone(period),
      memo,
    };
    setGenerated(request);
    setContents({});
    setError("");
    setPhase("generating");
    setStepIndex(0);
    window.scrollTo({ top: 0, behavior: "smooth" });
    try {
      const results: Partial<Record<PlanType, PlanContent>> = {};
      const template = workspace.templates.find((t) => t.id === templateId);
      setStepIndex(1);
      for (const type of selectedTypes) {
        if (type === "annual") {
          const settings = loadClassSettings(),
            primary = primaryClassFor(settings);
          if (!settings || !primary) throw new Error("반 정보를 먼저 저장해주세요.");
          // 계획안 조건으로 저장된 반/아동 연결을 변경하지 않는다.
          const serverClassId = await syncClass(settings, primary);
          const plan = await createAnnualPlan(
            {
              class_id: serverClassId,
              school_year: period.annual.year,
              source: "FROM_SCRATCH",
              upload_id: null,
            },
            controller.signal,
          );
          results.annual = {
            annualPlanId: plan.id,
            origin: plan.months.some((m) => m.source_type === "AI") ? "ai" : "template",
            notes: [
              "연간계획안은 서버에 초안으로 저장됩니다. 추가 요청사항은 메모로 보존되며 활동에 반영하려면 내용을 수정해주세요.",
            ],
            rows: plan.months.map((m) => ({
              label: m.month + "월",
              title: m.theme,
              detail: m.sub_themes.join("\n"),
            })),
          };
        } else if (available) {
          const result = await requestAI<{ sections: Section[]; notes: string[] }>(
            "plan",
            {
              type,
              age,
              ...(exactAges ? { ages: exactAges } : {}),
              period,
              memo,
              template: template ? { headings: template.headings, style: template.style } : null,
            },
            controller.signal,
          );
          if (!result.sections.length)
            throw new Error("계획안 항목을 완성하지 못했어요. 다시 생성해주세요.");
          results[type] = {
            origin: "ai",
            notes: result.notes,
            rows: result.sections.map((s, i) => ({
              label: String(i + 1),
              title: s.heading,
              detail: s.body,
            })),
          };
        } else {
          results[type] = templatePlan(type, age, period, memo, template, request.ageLabel);
        }
        if (controller.signal.aborted) return;
        setStepIndex(2);
      }
      if (!available) await new Promise((resolve) => setTimeout(resolve, 700));
      if (controller.signal.aborted) return;
      if (results.annual?.annualPlanId) {
        const { annual, ...companions } = results;
        try {
          saveAnnualContext(annual.annualPlanId!, { request, classId, className, companions });
        } catch (e) {
          console.warn("계획안 표시 정보 캐시 저장 실패", e);
        }
        router.replace("/plans/annual/" + annual.annualPlanId);
        return;
      }
      setContents(results);
      setStepIndex(4);
      setPhase("done");
    } catch (e) {
      if (controller.signal.aborted) return;
      setError(e instanceof Error ? e.message : "계획안을 생성하지 못했어요.");
      setPhase("idle");
    }
  }

  function handleRegenerate() {
    controllerRef.current?.abort();
    setPhase("idle");
  }

  return (
    <div
      className={`${embedded ? "" : `${fontClassName} min-h-screen`} font-body`}
      style={{ background: "var(--pg-cream)", color: "var(--pg-ink)" }}
    >
      {embedded ? (
        <AppHeader
          title="계획안 생성"
          description="조건을 선택하고 요청사항을 입력하면 AI가 계획안 초안을 만들어요."
          divider={false}
        />
      ) : (
        <header
          className="flex items-center justify-between px-4 py-3.5 lg:px-8 lg:py-5 border-b"
          style={{ borderColor: "var(--pg-line)" }}
        >
          <div className="flex items-center gap-2.5 min-w-0">
            <svg width="30" height="30" viewBox="0 0 30 30" aria-hidden="true" className="shrink-0">
              <circle cx="12" cy="15" r="9" className="fill-sage" />
              <circle cx="20" cy="10" r="6" className="fill-sage-ink" />
            </svg>
            <span className="font-display text-xl">쓱싹요정</span>
            <span className="hidden lg:inline text-sm ml-1 text-ink-soft">· 계획안 생성</span>
          </div>
        </header>
      )}

      <div className="px-4 lg:px-10">
        {(error || storageError) && (
          <p className={ws.error} role="alert">
            {error || storageError}
          </p>
        )}
        {phase === "idle" && (
          <div className={ws.row} style={{ marginBottom: 20 }}>
            <label className={ws.field}>
              사용할 기관 양식
              <select value={templateId} onChange={(e) => setTemplateId(e.target.value)}>
                <option value="">쓱싹요정 기본 양식</option>
                {workspace.templates.map((t) => (
                  <option value={t.id} key={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </label>
            <p className={ws.hint}>
              {available
                ? "AI 연결됨 · 입력 조건과 기관 양식으로 생성해요."
                : "기본 양식 모드 · AI 연결 전에는 수정 가능한 기본 초안을 만들어요."}
            </p>
          </div>
        )}
      </div>
      {phase !== "idle" && generated ? (
        <GenerationFlow
          key={phase}
          phase={phase}
          stepIndex={stepIndex}
          request={generated}
          contents={contents}
          classId={classId}
          className={className}
          onBack={handleRegenerate}
          onRetry={handleGenerate}
        />
      ) : (
        <main
          className={`grid grid-cols-1 gap-4 p-4 lg:gap-6 lg:grid-cols-[400px_minmax(0,1fr)] ${embedded ? "lg:px-10 lg:pt-2 lg:pb-12 pt-1" : "lg:p-8"}`}
        >
          <InputPanel
            age={age}
            onAgeChange={setAge}
            planTypes={planTypes}
            onToggleType={toggleType}
            period={period}
            onPeriodChange={updatePeriod}
            memo={memo}
            onMemoChange={setMemo}
            canGenerate={canGenerate}
            onGenerate={handleGenerate}
          />

          <section
            ref={stageRef}
            className="relative overflow-hidden rounded-[24px] border px-5 py-7 lg:p-10 min-h-[380px] lg:min-h-[640px] flex items-center justify-center bg-paper shadow-pg"
            style={{ borderColor: "var(--pg-line)" }}
          >
            <svg
              className="absolute -left-8 -top-8 opacity-20 lg:opacity-30 scale-[.6] lg:scale-100 pg-float"
              style={{ animation: "pg-float 5s ease-in-out infinite" }}
              width="110"
              height="110"
              viewBox="0 0 110 110"
              aria-hidden="true"
            >
              <circle cx="55" cy="55" r="42" className="fill-sage" />
            </svg>
            <svg
              className="absolute -right-10 -bottom-10 opacity-20 lg:opacity-30 scale-[.6] lg:scale-100"
              style={{ animation: "pg-float 5s ease-in-out infinite -2.5s" }}
              width="140"
              height="140"
              viewBox="0 0 140 140"
              aria-hidden="true"
            >
              <circle cx="70" cy="70" r="55" className="fill-mint" />
            </svg>

            {phase === "idle" && <IdleState />}
          </section>
        </main>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------
// 왼쪽 입력 패널
// ---------------------------------------------------------------------

function InputPanel(props: {
  age: AgeGroup | "";
  onAgeChange: (v: AgeGroup | "") => void;
  planTypes: Set<PlanType>;
  onToggleType: (t: PlanType) => void;
  period: PeriodState;
  onPeriodChange: <K extends keyof PeriodState>(key: K, value: PeriodState[K]) => void;
  memo: string;
  onMemoChange: (v: string) => void;
  canGenerate: boolean;
  onGenerate: () => void;
}) {
  const {
    age,
    onAgeChange,
    planTypes,
    onToggleType,
    period,
    onPeriodChange,
    memo,
    onMemoChange,
    canGenerate,
    onGenerate,
  } = props;

  return (
    <aside
      className="rounded-[24px] border p-5 lg:p-6 flex flex-col gap-6 lg:gap-7 h-fit bg-paper shadow-pg"
      style={{ borderColor: "var(--pg-line)" }}
    >
      {/* 1. 대상 연령 */}
      <section className="flex flex-col gap-2.5">
        <label htmlFor="age" className="font-display text-[15px]">
          대상 연령
        </label>
        <select
          id="age"
          value={age}
          onChange={(e) => onAgeChange(e.target.value as AgeGroup | "")}
          className="w-full rounded-2xl px-4 py-3 min-h-[48px] text-base lg:text-[15px] border bg-paper appearance-none"
          style={{
            borderColor: "var(--pg-line)",
            backgroundImage: CHEVRON_BG,
            backgroundRepeat: "no-repeat",
            backgroundPosition: "right 12px center",
            backgroundSize: "15px",
            paddingRight: 34,
          }}
        >
          <option value="">연령을 선택해주세요</option>
          <option value="3">만 3세</option>
          <option value="4">만 4세</option>
          <option value="5">만 5세</option>
          <option value="mixed">혼합반</option>
        </select>
      </section>

      {/* 2. 생성할 계획안 */}
      <section className="flex flex-col gap-2.5">
        <div>
          <label className="font-display text-[15px]">생성할 계획안</label>
          <p className="text-[12.5px] mt-0.5 text-ink-soft">여러 개를 함께 선택할 수 있어요</p>
        </div>
        <div className="grid grid-cols-2 gap-2.5">
          {PLAN_TYPES.map((t) => (
            <PlanTypeCard
              key={t}
              type={t}
              selected={planTypes.has(t)}
              onToggle={() => onToggleType(t)}
            />
          ))}
        </div>
      </section>

      {/* 3. 기간 선택 (선택한 계획안 종류에 따라 동적으로 표시) */}
      <section className="flex flex-col gap-2.5">
        <label className="font-display text-[15px]">기간 선택</label>
        <label className={ws.field}>
          기준 연도
          <input
            aria-label="기준 연도"
            type="number"
            min={2000}
            max={2100}
            value={period.annual.year}
            onChange={(e) => onPeriodChange("annual", { year: Number(e.target.value) })}
          />
        </label>
        {planTypes.has("annual") && (
          <p className="text-xs text-ink-soft">
            연간: {period.annual.year}년 3월 ~ {period.annual.year + 1}년 2월
          </p>
        )}
        {planTypes.has("weekly") && (
          <p className="text-xs text-ink-soft">주차는 1~7일, 8~14일 등 월 안의 7일 단위예요.</p>
        )}
        {planTypes.size === 0 ? (
          <div
            className="text-[12.5px] rounded-xl px-3.5 py-3 border border-dashed text-ink-soft"
            style={{ borderColor: "var(--pg-line)", background: "var(--pg-sage-tint)" }}
          >
            계획안 종류를 먼저 선택해주세요
          </div>
        ) : (
          <div className="flex flex-col gap-2.5">
            {planTypes.has("monthly") && (
              <PeriodBlock type="monthly" label="몇 월인가요?">
                <MonthSelect
                  value={period.monthly.month}
                  onChange={(month) => onPeriodChange("monthly", { month })}
                />
              </PeriodBlock>
            )}
            {planTypes.has("weekly") && (
              <PeriodBlock type="weekly" label="몇 월 몇 주차인가요?">
                <MonthSelect
                  value={period.weekly.month}
                  onChange={(month) => onPeriodChange("weekly", { ...period.weekly, month })}
                />
                <WeekSelect
                  maxWeeks={Math.ceil(
                    new Date(period.annual.year, period.weekly.month, 0).getDate() / 7,
                  )}
                  value={period.weekly.week}
                  onChange={(week) => onPeriodChange("weekly", { ...period.weekly, week })}
                />
              </PeriodBlock>
            )}
            {planTypes.has("daily") && (
              <PeriodBlock type="daily" label="날짜를 선택해주세요">
                <input
                  type="date"
                  value={period.daily.date}
                  onChange={(e) => onPeriodChange("daily", { date: e.target.value })}
                  className="flex-1 lg:flex-none rounded-xl px-3 py-1.5 min-h-[44px] lg:min-h-0 text-base lg:text-[13px] border bg-paper"
                  style={{ borderColor: "var(--pg-line)" }}
                />
              </PeriodBlock>
            )}
          </div>
        )}
      </section>

      {/* 4. 추가 요청사항 / 메모 */}
      <section className="flex flex-col gap-2.5">
        <label htmlFor="memo" className="font-display text-[15px]">
          추가 요청사항 / 메모
        </label>
        <textarea
          id="memo"
          rows={5}
          value={memo}
          onChange={(e) => onMemoChange(e.target.value)}
          placeholder={
            "예) 가을 자연물을 활용한 놀이 활동을 중심으로 작성해주세요.\n예) 실외활동과 미술활동을 포함해주세요."
          }
          className="w-full rounded-2xl px-4 py-3 min-h-[140px] text-base lg:text-[14px] leading-relaxed resize-none border bg-paper placeholder:text-ink-soft"
          style={{ borderColor: "var(--pg-line)" }}
        />
        <div className="flex flex-wrap gap-1.5">
          {SUGGESTIONS.map((s) => (
            <button
              key={s.label}
              type="button"
              onClick={() => onMemoChange(s.text)}
              className={`text-[11.5px] min-h-[36px] rounded-full px-3 py-1.5 border transition-[filter] hover:brightness-95 ${
                s.tone === "peach"
                  ? "text-peach-ink bg-peach-tint border-peach-tint"
                  : "text-mint-ink bg-mint-tint border-mint-tint"
              }`}
            >
              {s.emoji} {s.label}
            </button>
          ))}
        </div>
      </section>

      {/* 5. 생성 버튼 */}
      <section className="flex flex-col gap-2">
        <button
          type="button"
          disabled={!canGenerate}
          onClick={onGenerate}
          className={`rounded-2xl py-3.5 min-h-[54px] lg:min-h-0 font-display text-[17px] lg:text-[16px] transition-colors active:translate-y-px disabled:cursor-not-allowed ${
            canGenerate ? "bg-sage text-ink hover:bg-sage-ink" : "bg-line text-ink-soft"
          }`}
        >
          계획안 생성하기
        </button>
        <p className="text-[12px] text-center text-ink-soft">
          {canGenerate
            ? "입력한 내용을 바탕으로 계획안을 생성해요"
            : "연령·계획안 종류·날짜를 확인해주세요. 생성 중에는 잠시 기다려주세요"}
        </p>
      </section>
    </aside>
  );
}

const CHEVRON_BG =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24'%3E%3Cpath d='M5 9l7 7 7-7' fill='none' stroke='%236B7280' stroke-width='2.3' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E\")";

function MonthSelect({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(Number(e.target.value))}
      className="flex-1 lg:flex-none rounded-xl px-3 py-1.5 min-h-[44px] lg:min-h-0 text-base lg:text-[13px] border bg-paper appearance-none"
      style={{
        borderColor: "var(--pg-line)",
        backgroundImage: CHEVRON_BG,
        backgroundRepeat: "no-repeat",
        backgroundPosition: "right 8px center",
        backgroundSize: "13px",
        paddingRight: 26,
      }}
    >
      {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
        <option key={m} value={m}>
          {m}월
        </option>
      ))}
    </select>
  );
}

function WeekSelect({
  value,
  onChange,
  maxWeeks,
}: {
  value: number;
  onChange: (v: number) => void;
  maxWeeks: number;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(Number(e.target.value))}
      className="flex-1 lg:flex-none rounded-xl px-3 py-1.5 min-h-[44px] lg:min-h-0 text-base lg:text-[13px] border bg-paper appearance-none"
      style={{
        borderColor: "var(--pg-line)",
        backgroundImage: CHEVRON_BG,
        backgroundRepeat: "no-repeat",
        backgroundPosition: "right 8px center",
        backgroundSize: "13px",
        paddingRight: 26,
      }}
    >
      {Array.from({ length: maxWeeks }, (_, i) => i + 1).map((w) => (
        <option key={w} value={w}>
          {w}주차
        </option>
      ))}
    </select>
  );
}

function PeriodBlock({
  type,
  label,
  children,
}: {
  type: PlanType;
  label: string;
  children: React.ReactNode;
}) {
  const a = ACCENT[type];
  return (
    <div
      className={`rounded-xl p-3.5 flex items-center gap-2 flex-wrap border ${a.tint}`}
      style={{ borderColor: "var(--pg-line)" }}
    >
      <span
        className={`text-[11px] font-mono px-2 py-1 rounded-full text-ink ${type === "monthly" || type === "annual" ? "bg-sage" : type === "weekly" ? "bg-mint" : "bg-peach"}`}
      >
        {PLAN_TYPE_LABEL[type]}
      </span>
      <span className="text-[13px] text-ink-soft">{label}</span>
      <div className="w-full lg:w-auto lg:ml-auto flex items-center gap-2">{children}</div>
    </div>
  );
}

function PlanTypeCard({
  type,
  selected,
  onToggle,
}: {
  type: PlanType;
  selected: boolean;
  onToggle: () => void;
}) {
  const a = ACCENT[type];
  return (
    <button
      type="button"
      role="button"
      aria-pressed={selected}
      onClick={onToggle}
      className={`relative p-3.5 flex flex-col items-center gap-1.5 text-center rounded-[18px] border-[1.5px] transition-colors hover:-translate-y-px ${
        selected ? `border-current ${a.tint} ${a.text}` : "bg-paper"
      }`}
      style={{ borderColor: selected ? undefined : "var(--pg-line)" }}
    >
      <PlanTypeIcon type={type} className={selected ? a.text : "text-ink-soft"} />
      <span className="text-[13.5px] font-bold text-ink">{PLAN_TYPE_LABEL[type]}</span>
      <span className="text-[11px] leading-snug text-ink-soft">{PLAN_TYPE_HELP[type]}</span>
      {selected && (
        <span
          className={`absolute top-1.5 right-1.5 flex items-center justify-center rounded-full ${type === "monthly" || type === "annual" ? "bg-sage" : type === "weekly" ? "bg-mint" : "bg-peach"}`}
          style={{ width: 14, height: 14 }}
        >
          <svg width="9" height="9" viewBox="0 0 24 24">
            <path
              d="M4 12.5L9.5 18L20 6"
              stroke="var(--pg-ink)"
              strokeWidth={3}
              fill="none"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
      )}
    </button>
  );
}

function PlanTypeIcon({ type, className }: { type: PlanType; className?: string }) {
  if (type === "monthly" || type === "annual") {
    return (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" className={className}>
        <rect x="3.5" y="5" width="17" height="15" rx="3" stroke="currentColor" strokeWidth="1.6" />
        <path d="M3.5 9.5H20.5" stroke="currentColor" strokeWidth="1.6" />
        <path d="M8 3V6.2M16 3V6.2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    );
  }
  if (type === "weekly") {
    return (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" className={className}>
        <rect x="3.5" y="5" width="17" height="15" rx="3" stroke="currentColor" strokeWidth="1.6" />
        <path d="M3.5 9.5H20.5" stroke="currentColor" strokeWidth="1.6" />
        <path
          d="M8 12H8.01M12 12H12.01M16 12H16.01M8 15.5H8.01M12 15.5H12.01"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </svg>
    );
  }
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" className={className}>
      <rect x="3.5" y="5" width="17" height="15" rx="3" stroke="currentColor" strokeWidth="1.6" />
      <path d="M3.5 9.5H20.5" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="12" cy="14.5" r="2.6" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

// ---------------------------------------------------------------------
// 오른쪽 스테이지: 상태별 화면
// ---------------------------------------------------------------------

function IdleState() {
  return (
    <div
      className="relative z-10 flex flex-col items-center text-center gap-5 max-w-md"
      style={{ animation: "pg-fade-up .35s ease both" }}
    >
      <svg
        width="132"
        height="90"
        viewBox="0 0 132 90"
        aria-hidden="true"
        style={{ animation: "pg-float 5s ease-in-out infinite" }}
      >
        <circle cx="40" cy="52" r="34" className="fill-sage" />
        <circle cx="30" cy="44" r="3.2" fill="#fff" />
        <circle cx="30" cy="44" r="1.6" fill="var(--pg-ink)" />
        <circle cx="46" cy="44" r="3.2" fill="#fff" />
        <circle cx="46" cy="44" r="1.6" fill="var(--pg-ink)" />
        <path
          d="M30 60Q38 67 47 59"
          stroke="var(--pg-ink)"
          strokeWidth="2.2"
          fill="none"
          strokeLinecap="round"
        />
        <circle cx="98" cy="38" r="24" className="fill-mint" />
        <circle cx="90" cy="33" r="2.6" fill="#fff" />
        <circle cx="90" cy="33" r="1.3" fill="var(--pg-ink)" />
        <circle cx="103" cy="33" r="2.6" fill="#fff" />
        <circle cx="103" cy="33" r="1.3" fill="var(--pg-ink)" />
        <path
          d="M91 44Q98 49 106 43"
          stroke="var(--pg-ink)"
          strokeWidth="2"
          fill="none"
          strokeLinecap="round"
        />
      </svg>
      <div>
        <h2 className="font-display text-2xl">계획안을 만들어볼까요?</h2>
        <p className="mt-2.5 text-[14.5px] leading-relaxed text-ink-soft">
          연령과 계획안 종류를 선택하고 요청사항을 입력하면
          <br className="hidden sm:inline" />
          AI가 계획안을 생성해드려요.
        </p>
      </div>
      <p
        className="font-mono text-[11px] px-3 py-1 rounded-full border text-ink-soft"
        style={{ background: "var(--pg-sage-tint)", borderColor: "var(--pg-line)" }}
      >
        TIP · 추천 태그를 누르면 메모가 빠르게 채워져요
      </p>
    </div>
  );
}
