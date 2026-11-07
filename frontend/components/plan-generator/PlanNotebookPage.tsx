"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { listAnnualPlans } from "@/lib/api/plans";
import { listMonthlyPlans } from "@/lib/api/monthly";
import { listPlayMonthly } from "@/lib/api/playMonthly";
import { listWeeklyPlans } from "@/lib/api/weekly";
import type {
  AnnualPlanSummary,
  MonthlyPlanSummary,
  PlayMonthlySummary,
  WeeklyPlanSummary,
} from "@/lib/api/types";
import AnnualImport from "./AnnualImport";
import { Tape } from "@/components/workspace/WorkspaceUI";

/**
 * 계획안 첫 화면 — 방식(월별 주제형 · 놀이 중심형)을 고르고, 확정 안 한 초안을 이어서 쓴다.
 * 확정한 계획안은 문서 보관함(/documents)에서 본다.
 */

const MODE = { MONTHLY_THEME: "월별 주제형", PLAY_PROJECT: "놀이 중심형" } as const;

export type DraftCard = {
  key: string;
  date: string;
  created: string;
  mode: string;
  /** 위 방식 칸의 흐름 쪽지(연간 › 월간 › 주간) 중 어느 단계인지 — 무엇이 다시 열리는지 미리 보인다. */
  step: "연간" | "월간" | "주간";
  title: string;
  href: string;
};

/** 「이어서 하기」 카드. 확정 안 한 연간 · 월간 · 주간 초안만, 최근 만든 것부터. */
export function draftCards(
  annual: AnnualPlanSummary[],
  monthly: MonthlyPlanSummary[],
  play: PlayMonthlySummary[],
  weekly: WeeklyPlanSummary[] = [],
): DraftCard[] {
  const cards = [
    ...annual
      .filter((p) => p.status === "DRAFT")
      .map((p) => ({
        key: "annual-" + p.id,
        created: p.created_at,
        mode: MODE[p.format],
        step: "연간" as const,
        title: `${p.school_year} 연간계획안`,
        href: `/plans/annual/${p.id}`,
      })),
    ...monthly
      .filter((p) => p.status === "DRAFT")
      .map((p) => ({
        key: "monthly-" + p.id,
        created: p.created_at,
        mode: MODE.MONTHLY_THEME,
        step: "월간" as const,
        title: `${p.month}월 월간계획안`,
        href: `/plans/monthly?plan_id=${p.id}&class_id=${p.class_id}&month=${p.month}`,
      })),
    ...play
      .filter((p) => p.status === "DRAFT")
      .map((p) => ({
        key: "play-" + p.id,
        created: p.created_at,
        mode: MODE.PLAY_PROJECT,
        step: "월간" as const,
        title: `${p.month}월 월간계획안`,
        href: `/plans/monthly/play/${p.id}`,
      })),
    ...weekly
      .filter((p) => p.status === "DRAFT")
      .map((p) => ({
        key: "weekly-" + p.id,
        created: p.created_at,
        mode: MODE.MONTHLY_THEME,
        step: "주간" as const,
        title: `${weekTitle(p.week_id)} 주간계획안`,
        href: `/plans/weekly?plan_id=${p.id}&class_id=${p.class_id}&week_id=${p.week_id}`,
      })),
  ];
  return cards
    .sort((a, b) => b.created.localeCompare(a.created))
    .map((c) => ({ ...c, date: shortDate(c.created) }));
}

/**
 * 월간을 바로 만들 수 있는 연간 — 월간 만들기 화면(`/plans/monthly`)처럼 **가장 최근 연간**을 보고,
 * 그게 확정됐을 때만 돌려준다. 그 방식 칸의 「연간부터 시작하기」가 「월간계획안 만들기」로 바뀐다.
 */
// ponytail: 첫 화면은 반을 가리지 않고 가장 최근 연간을 본다. 반이 여럿이면 월간 화면이 고른 반과 다를 수 있다 — 그때는 고른 반 id 로 거른다.
export function readyAnnual(annual: AnnualPlanSummary[]) {
  const latest = [...annual].sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
  return latest?.status === "CONFIRMED" ? latest : null;
}

/**
 * 주간을 바로 만들 수 있는 월간 — 확정한 연간과 같은 반 · 학년도에서 **가장 최근에 확정한** 월간.
 * 있으면 월별 주제형 칸에 [주간계획안 만들기] 가 따로 붙고, 주간 화면이 그 달을 먼저 연다.
 */
export function readyMonthly(annual: AnnualPlanSummary | null, monthly: MonthlyPlanSummary[]) {
  if (!annual) return null;
  const done = monthly.filter(
    (p) =>
      p.status === "CONFIRMED" &&
      p.class_id === annual.class_id &&
      p.school_year === annual.school_year,
  );
  return (
    done.sort((a, b) =>
      (b.confirmed_at ?? b.created_at).localeCompare(a.confirmed_at ?? a.created_at),
    )[0] ?? null
  );
}

/** `YYYY-MM-Wn` → 「11월 1주」. 서버가 준 주차를 읽기만 한다. 모양이 다르면 그대로. */
function weekTitle(weekId: string) {
  const m = /^\d{4}-(\d{2})-W(\d+)$/.exec(weekId);
  return m ? `${Number(m[1])}월 ${Number(m[2])}주` : weekId;
}

// 카드 날짜는 정답지처럼 「10월 30일」. 문서 보관함은 localDate(2026.10.30) 그대로.
function shortDate(iso: string) {
  const at = new Date(iso);
  return Number.isNaN(at.getTime()) ? "" : `${at.getMonth() + 1}월 ${at.getDate()}일`;
}

export default function PlanNotebookPage() {
  // 월간부터 시작: 파일을 골랐거나(File) 직접 입력(null)으로 가져오기 화면을 띄운다.
  const [importing, setImporting] = useState<{ file: File | null } | null>(null);
  const [skip, setSkip] = useState(false);
  const [drafts, setDrafts] = useState<DraftCard[] | null>(null);
  const [ready, setReady] = useState<AnnualPlanSummary | null>(null);
  const [weekly, setWeekly] = useState<MonthlyPlanSummary | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const abort = new AbortController();
    Promise.allSettled([
      listAnnualPlans(undefined, abort.signal),
      listMonthlyPlans(undefined, abort.signal),
      listPlayMonthly(undefined, abort.signal),
      listWeeklyPlans(undefined, undefined, abort.signal),
    ]).then(([annual, monthly, play, weekly]) => {
      if (abort.signal.aborted) return;
      const items = <T,>(r: PromiseSettledResult<{ items: T[] }>) =>
        r.status === "fulfilled" ? r.value.items : [];
      // 하나만 실패해도 나머지는 보여 준다 — 없는 초안을 없다고 말하지 않도록 알린다.
      if ([annual, monthly, play, weekly].some((r) => r.status === "rejected"))
        setError("계획안 일부를 불러오지 못했어요. 새로고침해 주세요.");
      setDrafts(draftCards(items(annual), items(monthly), items(play), items(weekly)));
      const annualReady = readyAnnual(items(annual));
      setReady(annualReady);
      setWeekly(
        annualReady?.format === "MONTHLY_THEME" ? readyMonthly(annualReady, items(monthly)) : null,
      );
    });
    return () => abort.abort();
  }, []);

  // 메모지 줄은 마우스 휠(위아래)로도 옆으로 넘긴다. 줄 끝에 닿으면 휠은 다시 페이지 몫.
  const row = useRef<HTMLUListElement>(null);
  useEffect(() => {
    const el = row.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (Math.abs(e.deltaX) >= Math.abs(e.deltaY)) return; // 트랙패드 가로 밀기는 그대로
      const end = el.scrollWidth - el.clientWidth - 1;
      if ((e.deltaY < 0 && el.scrollLeft <= 0) || (e.deltaY > 0 && el.scrollLeft >= end)) return;
      e.preventDefault();
      el.scrollLeft += e.deltaY * (e.deltaMode === 1 ? 40 : 1); // 줄 단위 휠(Firefox)은 픽셀로
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [drafts, importing]);

  if (importing) return <AnnualImport file={importing.file} onCancel={() => setImporting(null)} />;

  // 화면 높이에 맞춘다 — 페이지는 굴러가지 않고, 초안이 많으면 「이어서 하기」 카드만 안에서 굴린다.
  // 낮은 화면(높이 800 이하)에서는 여백을 줄여 카드 한 줄이 다 보이게 한다.
  return (
    <div className="flex w-full flex-col gap-5 px-10 pb-12 pt-[26px] text-[#2b2826] lg:h-[calc(calc(100*var(--app-vh))-60px)] lg:pb-6 [@media(max-height:800px)]:gap-4 [@media(max-height:800px)]:pt-4">
      <h1 className="penMark m-0 font-display text-[34px] font-bold leading-[1.2] text-ink lg:text-[44px] [@media(max-height:800px)]:lg:text-[36px]">
        어떤 계획안을 만들까요?
      </h1>
      <div
        className="grid gap-4"
        style={{ gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 380px), 1fr))" }}
      >
        <Panel
          format="MONTHLY_THEME"
          ready={ready?.format === "MONTHLY_THEME" ? ready : null}
          weekly={weekly}
          skip={skip}
          onSkip={setSkip}
          onImport={(file) => setImporting({ file })}
        />
        <Panel
          format="PLAY_PROJECT"
          ready={ready?.format === "PLAY_PROJECT" ? ready : null}
          skip={false}
          onSkip={setSkip}
          onImport={() => {}}
        />
      </div>

      {/* 이어서 하기 — 초안 하나가 메모지 한 장(홈 칠판 쪽지와 같은 종이 · 테이프 · 기울기).
          한 줄로 늘어놓고 넘치면 가로로 넘긴다 — 페이지는 화면 높이에 맞춘 채 그대로. */}
      <section data-tour="plans-continue" className="mt-4 flex min-h-0 flex-col gap-3">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="m-0 min-w-0 font-display text-[28px] font-bold leading-tight text-ink">
            <CrayonMark>이어서 하기</CrayonMark>
          </h2>
        </div>
        {error && (
          <p role="alert" className="m-0 text-sm text-[#a0453a]">
            {error}
          </p>
        )}
        {/* 목록을 받기 전에는 「없어요」라고 말하지 않는다. */}
        {drafts === null && (
          <p role="status" className="m-0 py-6 text-sm text-ink-soft">
            불러오는 중…
          </p>
        )}
        {/* 노끈 한 줄에 메모지를 집게로 건다. 맨 끝은 글 없는 점선 빈자리 하나
            (초안이 없으면 그 빈자리만). 노끈은 칸마다 한 구간씩 그려 한 줄로 이어진다.
            pb 는 기울기 · 그림자가 굴림 칸에 잘리지 않게. */}
        {drafts && (
          <ul
            ref={row}
            className="-mx-2 flex list-none gap-5 overflow-x-auto overflow-y-hidden px-2 pb-4"
          >
            {drafts.map((card, i) => (
              <li key={card.key} className="relative w-[240px] shrink-0 pt-5">
                <Cord i={i} />
                <DraftNote card={card} tilt={TILT[i % TILT.length]} />
              </li>
            ))}
            <li aria-hidden="true" className="relative w-[240px] shrink-0 pt-5">
              <Cord i={drafts.length} />
              <span className={`block ${NOTE_H} border-2 border-dashed border-[#cfc6b9]`} />
            </li>
          </ul>
        )}
      </section>
    </div>
  );
}

/** 단계마다 메모지 색 — 연간 빨강(홈 칠판 쪽지의 clay) · 월간 초록 · 주간 노랑(홈 사이드바 메모지).
 *  줄은 종이 테두리 색. */
const NOTE: Record<DraftCard["step"], string> = {
  연간: "border-clay-line bg-clay [--pg-line:var(--pg-clay-line)]",
  월간: "border-sage-line bg-sage [--pg-line:var(--pg-sage-line)]",
  주간: "border-note-line bg-note [--pg-line:var(--pg-note-line)]",
};
/** 메모지 높이 — 줄 5칸(+ 아래 여백). 높이 880 이하에서는 4칸 — 페이지가 화면에 맞춰 줄면 메모지 아래가 잘린다. 마지막 줄이 늘 줄 위에 앉도록 34의 배수. */
const NOTE_H = "h-[190px] [@media(max-height:880px)]:h-[156px]";
/** 기울기 — 홈 쪽지처럼 번갈아. 같은 각도가 줄줄이 붙으면 한 장으로 보인다. */
const TILT = ["-rotate-2", "rotate-2", "-rotate-1", "rotate-1"];
/** 빨간 색연필 표시 — 펜을 떼지 않은 한 획: 글자를 동그라미로 감고, 아랫부분이 그대로 밑줄처럼
 *  오른쪽으로 빠져 돼지꼬리로 한 바퀴 말린 뒤 별을 그리고 끝난다. 결은 잡음으로 획 가장자리를 흔들고
 *  군데군데 비워 색연필로 종이를 긁은 느낌. 글자(「이어서 하기」 28px)가 그림의 x 16 · y 8 에 오게 놓는다. */
function CrayonMark({ children }: { children: ReactNode }) {
  return (
    <span className="relative inline-block">
      {children}
      <svg
        aria-hidden="true"
        viewBox="0 0 320 56"
        className="pointer-events-none absolute -left-4 -top-2 h-[56px] w-[320px] overflow-visible text-alert-strong"
      >
        <defs>
          <filter
            id="plans-crayon"
            filterUnits="userSpaceOnUse"
            x="-20"
            y="-20"
            width="380"
            height="100"
          >
            <feTurbulence
              type="fractalNoise"
              baseFrequency="0.85"
              numOctaves="2"
              seed="7"
              result="n"
            />
            <feDisplacementMap in="SourceGraphic" in2="n" scale="2.2" result="d" />
            <feColorMatrix
              in="n"
              type="matrix"
              values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 -2.2 1.9"
              result="grain"
            />
            <feComposite in="d" in2="grain" operator="in" />
          </filter>
        </defs>
        <path
          d={[
            "M150 36 C156 22 136 6 92 5 C46 4 10 12 10 27 C10 41 44 48 82 47", // 동그라미: 오른쪽 → 위 → 왼쪽 → 아래
            "C118 46 146 43 160 35 C162 34.5 164 36.5 166 37", // 시작점 옆을 지나 닫히고, 아랫부분이 밑줄처럼 오른쪽으로
            "C173.5 35.5 179.5 30.25 176.5 25 C173.5 19.75 166.75 22 168.25 28 C169.75 34 179.5 35.5 188.5 32.5", // 돼지꼬리 한 바퀴
            "C192 31 196 28.5 199.6 26.7 L213.6 8.7 L212.8 31.5 L200 12.6 L221.5 20.4 L199.6 26.7", // 별(20° 기울임) — 꼬리가 별의 왼쪽 아래 꼭짓점으로 들어간다
          ].join(" ")}
          fill="none"
          stroke="currentColor"
          strokeWidth={3}
          strokeLinecap="round"
          strokeLinejoin="round"
          filter="url(#plans-crayon)"
        />
      </svg>
    </span>
  );
}

/** 노끈이 처지는 깊이 · 가장 처진 자리(구간 260 기준) — 칸마다 조금씩 달라 손으로 건 끈처럼. */
const SAG = [
  [3, 122],
  [5, 140],
  [2, 126],
  [4, 136],
  [2.5, 118],
  [4.5, 132],
];
/** 노끈 한 구간 — 칸 양옆 gap 가운데에서 집게 근처로 살짝 처진다. 구간 끝은 늘 같은 높이라
 *  칸 폭 + gap(20px)마다 이웃 칸 끈과 매끄럽게 이어진다. */
function Cord({ i }: { i: number }) {
  const [sag, x] = SAG[i % SAG.length];
  const y = 8 + sag;
  const d = `M0 8C${x / 2} 8 ${x / 2} ${y} ${x} ${y}C${(x + 260) / 2} ${y} ${(x + 260) / 2} 8 260 8`;
  const path = { d, fill: "none", vectorEffect: "non-scaling-stroke" as const };
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 260 24"
      preserveAspectRatio="none"
      className="pointer-events-none absolute -left-2.5 top-0 h-6 w-[calc(100%+20px)] overflow-visible"
    >
      <path {...path} stroke="#a98b5f" strokeWidth={3} strokeLinecap="round" />
      <path {...path} stroke="#d2b98d" strokeWidth={1.2} strokeDasharray="3 4" />
    </svg>
  );
}

/** 가까운 날은 「오늘 · 어제」로, 그 밖은 「11월 3일」. 정확한 날짜는 `<time>` 과 마우스 올림에 남긴다. */
function madeLabel(iso: string, now = new Date()) {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return "";
  const day = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const diff = Math.round((day(now) - day(at)) / 86_400_000);
  return diff === 0 ? "오늘" : diff === 1 ? "어제" : shortDate(iso);
}

/** 방식 꼬리표(월별 주제형 · 놀이 중심형) — 단계는 메모지 색과 제목이 말한다. 글자는 읽기 쉬운 본문 글꼴. */
function ModeBadge({ card }: { card: DraftCard }) {
  return (
    // 바탕만 왼쪽으로 내밀어(-ml) 꼬리표 글자가 아래 제목 글자와 같은 세로줄에 선다.
    <span className="-ml-2 inline-flex h-6 shrink-0 items-center rounded bg-white/75 px-2 text-[13px] font-bold text-ink">
      {card.mode}
    </span>
  );
}

const Made = ({ card }: { card: DraftCard }) => (
  <time dateTime={card.created} title={`${card.date}에 시작`}>
    {madeLabel(card.created)}
  </time>
);

/** 이어 쓸 초안 메모지 한 장(단계 색종이 · 「지금, 한 줄」 줄 종이, 노끈에 나무 집게로 걸림) — 메모지 전체가 그 초안으로 가는 길.
 *  집게에 매달렸으니 위 가운데를 축으로 기울고, 마우스를 올리면 똑바로 선다.
 *  `ruledPaper` 는 34px 마다 줄 — 글 줄도 34px 칸이라 글자가 줄 위에 앉는다. 방식 꼬리표 · 날짜 / 제목 / 화살표. */
function DraftNote({ card, tilt }: { card: DraftCard; tilt: string }) {
  const router = useRouter();
  // 누르면 집게가 튕겨 빠지고 메모지가 아래로 떨어진 뒤 그 초안으로 간다.
  // 굴림 칸(overflow)에 잘리지 않게 메모지를 화면 위 고정 층에 복제해 떨어뜨린다.
  // 새 탭 · 수정키 클릭과 「움직임 줄이기」는 보통 링크 그대로.
  function drop(e: React.MouseEvent<HTMLAnchorElement>) {
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    e.preventDefault();
    const note = e.currentTarget;
    const box = note.getBoundingClientRect();
    const tiltM = getComputedStyle(note).transform;
    const base = tiltM === "none" ? "" : tiltM;
    const ghost = note.cloneNode(true) as HTMLElement;
    Object.assign(ghost.style, {
      position: "fixed",
      zIndex: "60",
      margin: "0",
      width: `${note.offsetWidth}px`,
      left: `${box.left + box.width / 2 - note.offsetWidth / 2}px`,
      top: `${box.top + box.height / 2 - note.offsetHeight / 2}px`,
      transformOrigin: "center",
      transform: base,
      pointerEvents: "none",
    });
    document.body.append(ghost);
    note.style.visibility = "hidden";
    const clip = ghost.querySelector<HTMLElement>("[data-clip]");
    if (clip) {
      const c = getComputedStyle(clip).transform;
      clip.animate(
        [
          { transform: c, opacity: 1 },
          { transform: `${c} translateY(-18px) rotate(-30deg)`, opacity: 0 },
        ],
        { duration: 200, easing: "ease-out", fill: "forwards" },
      );
    }
    ghost
      .animate(
        [
          { transform: `${base} translateY(0) rotate(0deg)` },
          { transform: `${base} translateY(-6px) rotate(0deg)`, offset: 0.15 },
          { transform: `${base} translateY(${innerHeight - box.top + 40}px) rotate(9deg)` },
        ],
        { duration: 560, delay: 120, easing: "cubic-bezier(.5,0,.9,.6)", fill: "forwards" },
      )
      .finished.then(() => {
        ghost.remove();
        router.push(card.href);
      });
  }
  return (
    <Link
      href={card.href}
      onClick={drop}
      aria-label={`${card.title} 이어서 쓰기 (${card.mode}, ${card.date} 시작)`}
      className={`ruledPaper group relative flex ${NOTE_H} origin-top flex-col border px-5 pb-5 text-ink no-underline shadow-pg-card transition-transform hover:rotate-0 motion-reduce:transition-none ${NOTE[card.step]} ${tilt}`}
    >
      {/* 나무 빨래집게 — 가운데 쇠 용수철 한 줄. */}
      <span
        aria-hidden="true"
        data-clip=""
        className="pointer-events-none absolute -top-[19px] left-1/2 h-[30px] w-[11px] -translate-x-1/2 rounded-[2px] border border-[#a2804f] bg-[#dcbb88] shadow-[0_1px_2px_rgba(0,0,0,.25)]"
      >
        <span className="absolute -inset-x-px top-[10px] h-[3px] bg-[#8a8c90]" />
      </span>
      <span className={`${LINE} justify-between gap-2 text-sm text-[#6b6158]`}>
        <ModeBadge card={card} />
        <Made card={card} />
      </span>
      <span className={`${LINE} font-display text-[23px] font-bold`}>
        {/* 손글씨체는 글자가 줄보다 떠 보여 살짝 내려 앉힌다. */}
        <span className="translate-y-[6px] truncate">{card.title}</span>
      </span>
      {/* 메모지 전체가 링크라 화살표만 둔다 — 이름은 aria-label 이 읽어 준다. */}
      <span className={`${LINE} mt-auto self-end text-primary`}>
        <Arrow />
      </span>
    </Link>
  );
}

/** 메모지 한 줄 — 줄 간격(34px) 한 칸, 글자 아래가 줄 바로 위. */
const LINE = "flex h-[34px] min-w-0 items-end pb-1";

/** 방식 칸 아래 두 단추 — 아래 그림자가 깔리고 누르면 들어간다(계획안 화면 다른 단추와 같은 손맛). */
const PRIMARY =
  "flex min-h-[54px] flex-1 items-center justify-center gap-2 rounded-md bg-primary text-base font-bold text-white no-underline shadow-[0_3px_0_#59416e] transition-transform hover:bg-primary-hover active:translate-y-[3px] active:shadow-none motion-reduce:transition-none";
const SECONDARY =
  "flex min-h-[54px] flex-1 items-center justify-center gap-2 rounded-md border-2 border-[#c5b7dd] bg-white text-base font-bold text-[#5e4b96] shadow-[0_2px_0_#c5b7dd] transition-transform hover:bg-[#f6f1fb] active:translate-y-[2px] active:shadow-none motion-reduce:transition-none";

const Arrow = () => (
  <svg
    aria-hidden="true"
    width="18"
    height="18"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2.2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M5 12h14" />
    <path d="m13 6 6 6-6 6" />
  </svg>
);

const Chevron = () => (
  <svg
    aria-hidden="true"
    width="18"
    height="18"
    viewBox="0 0 24 24"
    fill="none"
    stroke="#8a8178"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M9 6l6 6-6 6" />
  </svg>
);

/**
 * 방식 하나. 월별 주제형의 [월간부터 시작하기]는 연간계획안 가져오기로 들어간다.
 * 놀이 중심형 가져오기는 아직 없다 — 단추를 잠가 둔다.
 * `ready`(이 방식 연간을 확정함)면 흐름 쪽지 「연간」에 체크가 붙고, 단추는
 * [월간계획안 만들기] 로 바뀐다 — 연간을 또 만들러 가지 않게. 확정한 연간은 문서 보관함에서 연다.
 * 만들기 단추는 `?from=plans` 를 붙여 그 화면의 「←」가 이 첫 화면으로 돌아오게 한다.
 * `weekly`(월별 주제형 월간을 확정함)면 「월간」에도 체크가 붙고 [주간계획안 만들기] 가 따로 붙는다.
 */
function Panel({
  format,
  ready,
  weekly = null,
  skip,
  onSkip,
  onImport,
}: {
  format: keyof typeof MODE;
  ready: AnnualPlanSummary | null;
  weekly?: MonthlyPlanSummary | null;
  skip: boolean;
  onSkip: (skip: boolean) => void;
  onImport: (file: File | null) => void;
}) {
  const v1 = format === "MONTHLY_THEME";
  const chip = v1 ? "bg-[#e8f1ea] text-[#3b5441]" : "bg-[#eee4f4] text-[#5e4b96]";
  const steps = v1 ? ["연간", "월간", "주간"] : ["연간", "월간"];
  return (
    <section
      data-tour={v1 ? "plans-theme" : "plans-play"}
      className="relative flex min-h-[340px] flex-col justify-between gap-5 bg-paper shadow-pg px-8 py-7 [@media(max-height:800px)]:min-h-0 [@media(max-height:800px)]:gap-4 [@media(max-height:800px)]:py-5"
    >
      <Tape />
      <div className="flex flex-col gap-2">
        <span className={`text-sm font-bold ${v1 ? "text-[#49654f]" : "text-[#5e4b96]"}`}>
          {v1 ? "생활주제 따라" : "아이들 놀이 따라"}
        </span>
        <h2 className="m-0 font-display text-[34px] font-bold leading-tight">{MODE[format]}</h2>
        <p className="m-0 text-base leading-relaxed text-[#5c5243]">
          {v1
            ? "달마다 생활주제를 정하고, 주제에 맞춰 놀이와 활동을 짜요."
            : "계절마다 놀이를 고르고, 아이들 흥미를 따라 한 달 놀이를 짜요."}
        </p>
      </div>
      <div className="flex items-center gap-[10px]">
        {steps.map((s, i) => (
          <span key={s} className="contents">
            {i > 0 && <Chevron />}
            <span
              className={`flex flex-1 items-center justify-center gap-1.5 py-2.5 font-display text-[19px] font-bold shadow-pg-card ${i % 2 ? "rotate-1" : "-rotate-1"} ${chip}`}
            >
              {s}
              {((ready && i === 0) || (weekly && i === 1)) && (
                <>
                  <svg
                    aria-hidden="true"
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="3"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="m4.5 12.5 5 5L20 6.5" />
                  </svg>
                  <span className="sr-only">확정함</span>
                </>
              )}
            </span>
          </span>
        ))}
        {!v1 && (
          <span className="contents">
            <span aria-hidden="true" className="w-[18px]" />
            {/* 주간 쪽지 자리 — 비어 있는 점선 쪽지에 「주간」을 줄 그어 지웠다. 「없음」은 화면 낭독에만. */}
            <span className="flex flex-1 rotate-1 items-center justify-center border-2 border-dashed border-[#d7d0c7] py-[7px] text-center">
              <span className="font-display text-[19px] font-bold text-[#b1a89c] line-through decoration-[#c98a7e] decoration-2">
                주간
              </span>
              <span className="sr-only">없음</span>
            </span>
          </span>
        )}
      </div>
      {ready ? (
        // 월간 · 주간 만들기는 단추를 따로. 주간 달은 주간 화면에서 고른다(가장 최근 확정한 달이 먼저 열림).
        <div className="flex items-center gap-3">
          <Link href="/plans/monthly?from=plans" className={PRIMARY}>
            월간계획안 만들기
            <Arrow />
          </Link>
          {weekly && (
            <Link href={`/plans/weekly?month=${weekly.month}&from=plans`} className={PRIMARY}>
              주간계획안 만들기
              <Arrow />
            </Link>
          )}
        </div>
      ) : skip ? (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-stretch gap-3">
            {/* 파일 고르기는 브라우저 기본 창을 쓴다. 고르는 순간 가져오기 화면으로 넘어간다. */}
            <label className="flex min-h-[58px] flex-[2] cursor-pointer flex-col items-center justify-center rounded-md border-2 border-dashed border-[#7053a0] bg-[#f6f1fb] px-3 py-1.5 text-base font-bold text-[#5e4b96] hover:bg-[#efe6f8] focus-within:outline focus-within:outline-2 focus-within:outline-[#7053a0]">
              <span className="flex items-center gap-2">
                <svg
                  aria-hidden="true"
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M12 15V4" />
                  <path d="m7.5 8.5 4.5-4.5 4.5 4.5" />
                  <path d="M4 15v3.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V15" />
                </svg>
                연간계획안 파일 올리기
              </span>
              <span className="text-[12px] font-medium text-[#7a6aa0]">
                HWP · HWPX · DOCX · PDF
              </span>
              <input
                type="file"
                accept=".hwp,.hwpx,.docx,.pdf"
                className="sr-only"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) onImport(file);
                }}
              />
            </label>
            <button
              type="button"
              onClick={() => onImport(null)}
              className="flex min-h-[58px] shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-md border-2 border-[#c5b7dd] bg-white px-4 text-[15px] font-bold text-[#5e4b96] hover:bg-[#f6f1fb]"
            >
              <svg
                aria-hidden="true"
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M4 20h4L19 9l-4-4L4 16v4Z" />
                <path d="m13.5 6.5 4 4" />
              </svg>
              직접 작성하기
            </button>
            <button
              type="button"
              onClick={() => onSkip(false)}
              className="min-h-[58px] rounded-md px-4 text-[15px] font-bold text-ink-soft hover:bg-[#f7f4ee]"
            >
              취소
            </button>
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-3">
          <Link href={`/plans/annual/new?format=${format}`} className={PRIMARY}>
            연간부터 시작하기
            <Arrow />
          </Link>
          <button
            type="button"
            onClick={() => onSkip(true)}
            disabled={!v1}
            className={`${SECONDARY} disabled:cursor-not-allowed disabled:border-dashed disabled:border-[#d7d0c7] disabled:text-ink-soft disabled:shadow-none disabled:hover:bg-white disabled:active:translate-y-0`}
          >
            월간부터 시작하기
          </button>
        </div>
      )}
    </section>
  );
}
