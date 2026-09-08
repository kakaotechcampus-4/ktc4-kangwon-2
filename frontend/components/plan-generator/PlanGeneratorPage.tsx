"use client";

/**
 * 새싹플랜 · 계획안 생성 메인 화면
 * ---------------------------------------------------------------------
 * 입력 패널(연령 / 계획안 종류 / 기간 / 메모 / 생성 버튼) +
 * 결과 스테이지(대기 / 생성 중 / 완료 3단 상태)로 구성됩니다.
 *
 * 반응형: 하나의 코드베이스에서 Tailwind `lg`(1024px) 브레이크포인트를 기준으로
 *  - 데스크톱(≥1024px): 왼쪽 입력 · 오른쪽 결과의 2단 그리드
 *  - 모바일(<1024px, 360~430px 검증): 입력 → 생성 버튼 → 결과가 이어지는 1단 세로 흐름,
 *    터치 타깃 44px 이상, 입력 폰트 16px, 결과 카드 세로 리스트, 생성 시 결과 영역으로 자동 스크롤
 *
 * 연동 전까지는 "생성 중" 단계를 useEffect 타이머로 시뮬레이션합니다.
 * 실제 API가 준비되면 해당 useEffect를 fetch + 진행률 이벤트로 교체하세요.
 *
 * 필요한 사전 설정:
 *  1) styles/plan-generator-tokens.css 의 내용을 app/globals.css 에 추가
 *  2) tailwind.config.additions.ts 의 theme.extend 내용을 tailwind.config 에 병합
 * --------------------------------------------------------------------- */

import { useEffect, useMemo, useRef, useState } from "react";
import { fontClassName } from "@/lib/fonts";
import AppHeader, { OrgChip } from "@/components/app/AppHeader";
import {
  AGE_LABEL,
  GENERATION_STEPS,
  PLAN_TYPE_HELP,
  PLAN_TYPE_LABEL,
  type AgeGroup,
  type GenerationPhase,
  type PeriodState,
  type PlanType,
} from "@/lib/plan-generator/types";
import { loadClassSettings, primaryClassFor } from "@/lib/onboarding/settings";


const PLAN_TYPES: PlanType[] = ["monthly", "weekly", "daily"];
const ACCENT: Record<PlanType, { text: string; tint: string; ink: string }> = {
  monthly: { text: "text-sage-ink", tint: "bg-sage-tint", ink: "text-sage-ink" },
  weekly: { text: "text-mint-strong", tint: "bg-mint-tint", ink: "text-mint-ink" },
  daily: { text: "text-peach-strong", tint: "bg-peach-tint", ink: "text-peach-ink" },
};

const SUGGESTIONS = [
  { emoji: "🍂", label: "가을 자연물 놀이", text: "가을 자연물(낙엽, 열매)을 활용한 놀이 활동을 중심으로 작성해주세요.", tone: "peach" as const },
  { emoji: "🎨", label: "실외+미술 활동", text: "실외활동과 미술활동을 포함해주세요.", tone: "mint" as const },
];

/**
 * @param embedded  true 면 AppLayout(사이드바) 안에서 렌더된다는 뜻.
 *                  자체 브랜드 헤더 대신 공통 AppHeader(페이지 제목)를 쓰고, 나머지 레이아웃/디자인은 그대로.
 */
export default function PlanGeneratorPage({ embedded = false }: { embedded?: boolean } = {}) {
  const [age, setAge] = useState<AgeGroup | "">("");
  const [planTypes, setPlanTypes] = useState<Set<PlanType>>(new Set());
  const [period, setPeriod] = useState<PeriodState>({
    monthly: { month: 9 },
    weekly: { month: 9, week: 3 },
    daily: { date: "2026-09-15" },
  });
  const [memo, setMemo] = useState("");
  const [phase, setPhase] = useState<GenerationPhase>("idle");
  const [stepIndex, setStepIndex] = useState(0);
  const [className, setClassName] = useState<string>("");

  // 온보딩(/onboarding)에서 저장한 반 설정을 기본값으로 반영:
  //  - 대상 연령을 자동 선택, 담당 반 이름을 헤더에 표시.
  //  - 성품인사는 생성 요청 시 characterMessageFor(settings, month)로 함께 보낼 수 있다.
  useEffect(() => {
    const saved = loadClassSettings();
    const primary = primaryClassFor(saved);
    if (!primary) return;
    if (primary.ageGroup) setAge((prev) => (prev === "" ? (primary.ageGroup as AgeGroup) : prev));
    if (primary.className) setClassName(primary.className);
  }, []);

  const canGenerate = age !== "" && planTypes.size > 0;
  const selectedTypes = useMemo(() => PLAN_TYPES.filter((t) => planTypes.has(t)), [planTypes]);

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const stageRef = useRef<HTMLElement | null>(null);

  // 모바일(1단 레이아웃)에서는 결과 영역이 생성 버튼 아래에 있으므로 자동으로 스크롤해 보여준다.
  function scrollToStageOnMobile() {
    if (typeof window === "undefined" || !window.matchMedia("(max-width: 1023px)").matches) return;
    const el = stageRef.current;
    if (!el) return;
    const top = el.getBoundingClientRect().top + window.scrollY - 12;
    window.scrollTo({ top, behavior: "smooth" });
  }

  function toggleType(t: PlanType) {
    setPlanTypes((prev) => {
      const next = new Set(prev);
      next.has(t) ? next.delete(t) : next.add(t);
      return next;
    });
  }

  function updatePeriod<K extends keyof PeriodState>(key: K, value: PeriodState[K]) {
    setPeriod((prev) => ({ ...prev, [key]: value }));
  }

  function handleGenerate() {
    if (!canGenerate) return;
    setPhase("generating");
    setStepIndex(0);
    requestAnimationFrame(scrollToStageOnMobile);
  }

  // 생성 중 단계 시뮬레이션. 실제 연동 시 이 useEffect를 API 호출 + 진행률 이벤트로 교체하세요.
  useEffect(() => {
    if (phase !== "generating") return;
    if (stepIndex >= GENERATION_STEPS.length) {
      timerRef.current = setTimeout(() => { setPhase("done"); requestAnimationFrame(scrollToStageOnMobile); }, 500);
      return () => { if (timerRef.current) clearTimeout(timerRef.current); };
    }
    timerRef.current = setTimeout(() => setStepIndex((i) => i + 1), 850);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [phase, stepIndex]);

  function handleRegenerate() {
    setPhase("idle");
  }

  return (
    <div className={`${embedded ? "" : `${fontClassName} min-h-screen`} font-body`} style={{ background: "var(--pg-cream)", color: "var(--pg-ink)" }}>
      {embedded ? (
        <AppHeader
          title="계획안 생성"
          description="조건을 선택하고 요청사항을 입력하면 AI가 계획안 초안을 만들어요."
          divider={false}
          tools={<OrgChip>🌼 햇살어린이집 · 김민지 선생님{className ? ` · ${className}` : ""}</OrgChip>}
        />
      ) : (
      <header className="flex items-center justify-between px-4 py-3.5 lg:px-8 lg:py-5 border-b" style={{ borderColor: "var(--pg-line)" }}>
        <div className="flex items-center gap-2.5 min-w-0">
          <svg width="30" height="30" viewBox="0 0 30 30" aria-hidden="true" className="shrink-0">
            <circle cx="12" cy="15" r="9" className="fill-sage" />
            <circle cx="20" cy="10" r="6" className="fill-sage-ink" />
          </svg>
          <span className="font-display text-xl">새싹플랜</span>
          <span className="hidden lg:inline text-sm ml-1 text-ink-soft">· 계획안 생성</span>
        </div>
        {/* 기관명/이름은 가입 시 설정된 값을 그대로 표시 — 이 화면에서 입력받지 않음 */}
        <span className="text-sm px-3 py-1.5 rounded-full border bg-paper text-ink-soft max-w-[52vw] lg:max-w-none truncate" style={{ borderColor: "var(--pg-line)" }}>
          🌼 햇살어린이집 · 김민지 선생님{className ? ` · ${className}` : ""}
        </span>
      </header>
      )}

      {/* Shell: 입력 패널 + 결과 스테이지 */}
      <main className={`grid grid-cols-1 gap-4 p-4 lg:gap-6 lg:grid-cols-[400px_minmax(0,1fr)] ${embedded ? "lg:px-10 lg:pt-2 lg:pb-12 pt-1" : "lg:p-8"}`}>
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

        <section ref={stageRef} className="relative overflow-hidden rounded-[24px] border px-5 py-7 lg:p-10 min-h-[380px] lg:min-h-[640px] flex items-center justify-center bg-paper shadow-pg" style={{ borderColor: "var(--pg-line)" }}>
          <svg className="absolute -left-8 -top-8 opacity-20 lg:opacity-30 scale-[.6] lg:scale-100 pg-float" style={{ animation: "pg-float 5s ease-in-out infinite" }} width="110" height="110" viewBox="0 0 110 110" aria-hidden="true">
            <circle cx="55" cy="55" r="42" className="fill-sage" />
          </svg>
          <svg className="absolute -right-10 -bottom-10 opacity-20 lg:opacity-30 scale-[.6] lg:scale-100" style={{ animation: "pg-float 5s ease-in-out infinite -2.5s" }} width="140" height="140" viewBox="0 0 140 140" aria-hidden="true">
            <circle cx="70" cy="70" r="55" className="fill-mint" />
          </svg>

          {phase === "idle" && <IdleState onSuggestion={setMemo} />}
          {phase === "generating" && <GeneratingState stepIndex={stepIndex} />}
          {phase === "done" && (
            <DoneState age={age as AgeGroup} selectedTypes={selectedTypes} period={period} onRegenerate={handleRegenerate} />
          )}
        </section>
      </main>
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
  const { age, onAgeChange, planTypes, onToggleType, period, onPeriodChange, memo, onMemoChange, canGenerate, onGenerate } = props;

  return (
    <aside className="rounded-[24px] border p-5 lg:p-6 flex flex-col gap-6 lg:gap-7 h-fit bg-paper shadow-pg" style={{ borderColor: "var(--pg-line)" }}>
      {/* 1. 대상 연령 */}
      <section className="flex flex-col gap-2.5">
        <label htmlFor="age" className="font-display text-[15px]">대상 연령</label>
        <select
          id="age"
          value={age}
          onChange={(e) => onAgeChange(e.target.value as AgeGroup | "")}
          className="w-full rounded-2xl px-4 py-3 min-h-[48px] text-base lg:text-[15px] border bg-paper appearance-none"
          style={{ borderColor: "var(--pg-line)", backgroundImage: CHEVRON_BG, backgroundRepeat: "no-repeat", backgroundPosition: "right 12px center", backgroundSize: "15px", paddingRight: 34 }}
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
        <div className="grid grid-cols-[repeat(auto-fit,minmax(96px,1fr))] gap-2.5">
          {PLAN_TYPES.map((t) => (
            <PlanTypeCard key={t} type={t} selected={planTypes.has(t)} onToggle={() => onToggleType(t)} />
          ))}
        </div>
      </section>

      {/* 3. 기간 선택 (선택한 계획안 종류에 따라 동적으로 표시) */}
      <section className="flex flex-col gap-2.5">
        <label className="font-display text-[15px]">기간 선택</label>
        {planTypes.size === 0 ? (
          <div className="text-[12.5px] rounded-xl px-3.5 py-3 border border-dashed text-ink-soft" style={{ borderColor: "var(--pg-line)", background: "var(--pg-sage-tint)" }}>
            계획안 종류를 먼저 선택해주세요
          </div>
        ) : (
          <div className="flex flex-col gap-2.5">
            {planTypes.has("monthly") && (
              <PeriodBlock type="monthly" label="몇 월인가요?">
                <MonthSelect value={period.monthly.month} onChange={(month) => onPeriodChange("monthly", { month })} />
              </PeriodBlock>
            )}
            {planTypes.has("weekly") && (
              <PeriodBlock type="weekly" label="몇 월 몇 주차인가요?">
                <MonthSelect value={period.weekly.month} onChange={(month) => onPeriodChange("weekly", { ...period.weekly, month })} />
                <WeekSelect value={period.weekly.week} onChange={(week) => onPeriodChange("weekly", { ...period.weekly, week })} />
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
        <label htmlFor="memo" className="font-display text-[15px]">추가 요청사항 / 메모</label>
        <textarea
          id="memo"
          rows={5}
          value={memo}
          onChange={(e) => onMemoChange(e.target.value)}
          placeholder={"예) 가을 자연물을 활용한 놀이 활동을 중심으로 작성해주세요.\n예) 실외활동과 미술활동을 포함해주세요."}
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
                s.tone === "peach" ? "text-peach-ink bg-peach-tint border-peach-tint" : "text-mint-ink bg-mint-tint border-mint-tint"
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
          {canGenerate ? "입력한 내용을 바탕으로 계획안을 생성해요" : "연령과 계획안 종류를 선택하면 생성할 수 있어요"}
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
      style={{ borderColor: "var(--pg-line)", backgroundImage: CHEVRON_BG, backgroundRepeat: "no-repeat", backgroundPosition: "right 8px center", backgroundSize: "13px", paddingRight: 26 }}
    >
      {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
        <option key={m} value={m}>{m}월</option>
      ))}
    </select>
  );
}

function WeekSelect({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(Number(e.target.value))}
      className="flex-1 lg:flex-none rounded-xl px-3 py-1.5 min-h-[44px] lg:min-h-0 text-base lg:text-[13px] border bg-paper appearance-none"
      style={{ borderColor: "var(--pg-line)", backgroundImage: CHEVRON_BG, backgroundRepeat: "no-repeat", backgroundPosition: "right 8px center", backgroundSize: "13px", paddingRight: 26 }}
    >
      {Array.from({ length: 5 }, (_, i) => i + 1).map((w) => (
        <option key={w} value={w}>{w}주차</option>
      ))}
    </select>
  );
}

function PeriodBlock({ type, label, children }: { type: PlanType; label: string; children: React.ReactNode }) {
  const a = ACCENT[type];
  return (
    <div className={`rounded-xl p-3.5 flex items-center gap-2 flex-wrap border ${a.tint}`} style={{ borderColor: "var(--pg-line)" }}>
      <span className={`text-[11px] font-mono px-2 py-1 rounded-full text-ink ${type === "monthly" ? "bg-sage" : type === "weekly" ? "bg-mint" : "bg-peach"}`}>
        {PLAN_TYPE_LABEL[type]}
      </span>
      <span className="text-[13px] text-ink-soft">{label}</span>
      <div className="w-full lg:w-auto lg:ml-auto flex items-center gap-2">{children}</div>
    </div>
  );
}

function PlanTypeCard({ type, selected, onToggle }: { type: PlanType; selected: boolean; onToggle: () => void }) {
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
        <span className={`absolute top-1.5 right-1.5 flex items-center justify-center rounded-full ${type === "monthly" ? "bg-sage" : type === "weekly" ? "bg-mint" : "bg-peach"}`} style={{ width: 14, height: 14 }}>
          <svg width="9" height="9" viewBox="0 0 24 24"><path d="M4 12.5L9.5 18L20 6" stroke="var(--pg-ink)" strokeWidth={3} fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </span>
      )}
    </button>
  );
}

function PlanTypeIcon({ type, className }: { type: PlanType; className?: string }) {
  if (type === "monthly") {
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
        <path d="M8 12H8.01M12 12H12.01M16 12H16.01M8 15.5H8.01M12 15.5H12.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
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

function IdleState({ onSuggestion }: { onSuggestion: (text: string) => void }) {
  return (
    <div className="relative z-10 flex flex-col items-center text-center gap-5 max-w-md" style={{ animation: "pg-fade-up .35s ease both" }}>
      <svg width="132" height="90" viewBox="0 0 132 90" aria-hidden="true" style={{ animation: "pg-float 5s ease-in-out infinite" }}>
        <circle cx="40" cy="52" r="34" className="fill-sage" />
        <circle cx="30" cy="44" r="3.2" fill="#fff" /><circle cx="30" cy="44" r="1.6" fill="var(--pg-ink)" />
        <circle cx="46" cy="44" r="3.2" fill="#fff" /><circle cx="46" cy="44" r="1.6" fill="var(--pg-ink)" />
        <path d="M30 60Q38 67 47 59" stroke="var(--pg-ink)" strokeWidth="2.2" fill="none" strokeLinecap="round" />
        <circle cx="98" cy="38" r="24" className="fill-mint" />
        <circle cx="90" cy="33" r="2.6" fill="#fff" /><circle cx="90" cy="33" r="1.3" fill="var(--pg-ink)" />
        <circle cx="103" cy="33" r="2.6" fill="#fff" /><circle cx="103" cy="33" r="1.3" fill="var(--pg-ink)" />
        <path d="M91 44Q98 49 106 43" stroke="var(--pg-ink)" strokeWidth="2" fill="none" strokeLinecap="round" />
      </svg>
      <div>
        <h2 className="font-display text-2xl">계획안을 만들어볼까요?</h2>
        <p className="mt-2.5 text-[14.5px] leading-relaxed text-ink-soft">
          연령과 계획안 종류를 선택하고 요청사항을 입력하면<br className="hidden sm:inline" />AI가 계획안을 생성해드려요.
        </p>
      </div>
      <p className="font-mono text-[11px] px-3 py-1 rounded-full border text-ink-soft" style={{ background: "var(--pg-sage-tint)", borderColor: "var(--pg-line)" }}>
        TIP · 추천 태그를 누르면 메모가 빠르게 채워져요
      </p>
    </div>
  );
}

function GeneratingState({ stepIndex }: { stepIndex: number }) {
  const progressPct = Math.min(100, Math.round(((stepIndex + (stepIndex >= GENERATION_STEPS.length ? 0 : 1)) / GENERATION_STEPS.length) * 100));
  return (
    <div className="relative z-10 flex flex-col items-center text-center gap-6 w-full max-w-sm">
      <div style={{ animation: "pg-float 5s ease-in-out infinite" }}>
        <svg width="72" height="72" viewBox="0 0 72 72" aria-hidden="true">
          <circle cx="36" cy="36" r="30" className="fill-sage-tint" />
          <circle
            cx="36" cy="36" r="30" fill="none" stroke="var(--pg-sage-ink)" strokeWidth="3" strokeDasharray="14 10" strokeLinecap="round"
            className="pg-spin" style={{ transformOrigin: "36px 36px", animation: "pg-spin 0.9s linear infinite" }}
          />
          <circle cx="29" cy="34" r="2.4" fill="var(--pg-ink)" /><circle cx="43" cy="34" r="2.4" fill="var(--pg-ink)" />
          <path d="M29 44Q36 49 43 44" stroke="var(--pg-ink)" strokeWidth="2" fill="none" strokeLinecap="round" />
        </svg>
      </div>
      <h2 className="font-display text-xl">계획안을 생성하고 있습니다</h2>
      <div className="w-full h-1.5 rounded-full overflow-hidden" style={{ background: "var(--pg-line)" }}>
        <div className="h-full transition-[width] duration-500" style={{ width: `${progressPct}%`, background: "var(--pg-sage-ink)" }} />
      </div>
      <ul className="w-full flex flex-col gap-2.5 text-left">
        {GENERATION_STEPS.map((s, i) => {
          const state = i < stepIndex ? "done" : i === stepIndex ? "current" : "pending";
          return (
            <li key={s} className={`flex items-center gap-2.5 text-[13.5px] ${state === "pending" ? "text-ink-soft" : "text-ink font-bold"}`}>
              <span
                className="inline-flex items-center justify-center rounded-full shrink-0 border-[1.5px]"
                style={{
                  width: 20, height: 20,
                  borderColor: state === "pending" ? "var(--pg-line)" : state === "current" ? "var(--pg-sage-ink)" : "var(--pg-success)",
                  background: state === "done" ? "var(--pg-success)" : state === "current" ? "var(--pg-sage-ink)" : "transparent",
                }}
              >
                {state === "done" && (
                  <svg width="11" height="11" viewBox="0 0 24 24"><path d="M4 12.5L9.5 18L20 6" stroke="white" strokeWidth={3} fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
                )}
              </span>
              <span>{s}</span>
            </li>
          );
        })}
      </ul>
      <p className="text-[12.5px] leading-relaxed text-ink-soft">
        선생님이 입력한 내용 안에서만 계획안을 구성하고 있어요. 조금만 기다려주세요.
      </p>
    </div>
  );
}

function DoneState({
  age, selectedTypes, period, onRegenerate,
}: {
  age: AgeGroup; selectedTypes: PlanType[]; period: PeriodState; onRegenerate: () => void;
}) {
  return (
    <div className="relative z-10 w-full">
      <div className="flex flex-col items-start lg:flex-row lg:items-center justify-between mb-5 gap-3">
        <div>
          <h2 className="font-display text-xl">계획안이 완성됐어요</h2>
          <p className="text-[13px] mt-1 text-ink-soft">
            {AGE_LABEL[age]} · {selectedTypes.map((t) => PLAN_TYPE_LABEL[t]).join("+")}
          </p>
        </div>
        <button type="button" onClick={onRegenerate} className="text-[13px] min-h-[44px] lg:min-h-0 rounded-full px-4 py-2 border text-ink-soft" style={{ borderColor: "var(--pg-line)" }}>
          ↺ 다시 생성하기
        </button>
      </div>
      <div className="grid gap-4 grid-cols-1 lg:grid-cols-[repeat(var(--cols),minmax(0,1fr))]" style={{ ["--cols" as string]: selectedTypes.length }}>
        {selectedTypes.map((t) => (
          <PreviewCard key={t} type={t} period={period} />
        ))}
      </div>
    </div>
  );
}

function PreviewCard({ type, period }: { type: PlanType; period: PeriodState }) {
  const badgeClass = type === "monthly" ? "bg-sage" : type === "weekly" ? "bg-mint" : "bg-peach";

  return (
    <div className="rounded-2xl p-5 border bg-paper" style={{ borderColor: "var(--pg-line)", animation: "pg-fade-up .35s ease both" }}>
      <div className="flex items-center justify-between mb-3">
        <span className={`text-[11px] font-mono px-2 py-1 rounded-full text-ink ${badgeClass}`}>{PLAN_TYPE_LABEL[type]}</span>
        <span className="text-[11.5px] text-ink-soft font-mono">
          {type === "monthly" && `${period.monthly.month}월`}
          {type === "weekly" && `${period.weekly.month}월 ${period.weekly.week}주차`}
          {type === "daily" && formatDateLabel(period.daily.date)}
        </span>
      </div>

      {type === "monthly" && (
        <>
          <h3 className="font-display text-[15px] mb-1">{period.monthly.month}월 월간 보육계획안</h3>
          <p className="text-[12px] mb-3 text-ink-soft">이달의 놀이주제 · <b className="text-sage-ink">가을과 자연</b></p>
          <ul className="text-[12.5px] flex flex-col gap-1.5 text-ink-soft">
            <li>1주 · 가을 열매와 곤충 관찰하기</li>
            <li>2주 · 낙엽·나뭇가지로 자연물 놀이</li>
            <li>3주 · 가을 자연물 콜라주 만들기</li>
            <li className="opacity-60">4주 · …</li>
          </ul>
        </>
      )}

      {type === "weekly" && (
        <>
          <h3 className="font-display text-[15px] mb-3">{period.weekly.month}월 {period.weekly.week}주차 주간계획안</h3>
          <div className="grid grid-cols-5 gap-1.5 text-center">
            {["월", "화", "수", "목", "금"].map((d, idx) => (
              <div key={d} className="rounded-lg p-1.5 bg-mint-tint">
                <div className="text-[10.5px] font-bold text-mint-ink">{d}</div>
                <div className="text-[10px] mt-1 leading-tight text-ink-soft">
                  {["자연물 관찰", "낙엽 콜라주", "바깥 놀이", "가을 노래", "정리 평가"][idx]}
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {type === "daily" && (
        <>
          <h3 className="font-display text-[15px] mb-3">{formatDateLabel(period.daily.date)} 일일계획안</h3>
          <ul className="text-[12.5px] flex flex-col gap-1.5 text-ink-soft">
            <li><span className="font-mono text-peach-ink">09:00</span> 등원 및 자유놀이</li>
            <li><span className="font-mono text-peach-ink">10:00</span> 가을 자연물 탐색 활동</li>
            <li><span className="font-mono text-peach-ink">11:00</span> 실외 놀이터 활동</li>
            <li className="opacity-60"><span className="font-mono">13:00</span> 낮잠 · 하원 준비 …</li>
          </ul>
        </>
      )}

      <button type="button" className="mt-4 text-[12px] w-full lg:w-auto min-h-[44px] lg:min-h-0 rounded-full px-3 py-1.5 border text-ink-soft" style={{ borderColor: "var(--pg-line)" }}>
        전체 보기
      </button>
    </div>
  );
}

function formatDateLabel(dateStr: string) {
  const d = new Date(dateStr);
  return `${d.getMonth() + 1}월 ${d.getDate()}일`;
}
