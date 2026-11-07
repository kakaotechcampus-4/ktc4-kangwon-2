"use client";
import { useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import Link from "next/link";
import { downloadAnnualHwpx } from "@/lib/api/plans";
import type { ExportFormat } from "@/lib/api/export";
import type { AnnualPlanResponse } from "@/lib/api/types";
import { useHwpxDownload } from "@/lib/hooks/use-hwpx-download";
import { stepPlaySheetZoom, type SheetZoom } from "./playProjectPagination";
import { Tape } from "@/components/workspace/WorkspaceUI";

/** ⑤ · ⑥ 공통 모양 (디자인 넘김 result-preview · done-preview). */
const CHIP = {
  MONTHLY_THEME: ["월별 주제형", "bg-[#e8f1ea] text-[#3b5441]"],
  PLAY_PROJECT: ["놀이 중심형", "bg-[#eee4f4] text-[#5e4b96]"],
} as const;
export const BUTTON = {
  quiet: "min-h-[44px] rounded-md px-3 text-sm text-[#5c5243] disabled:opacity-40",
  outline:
    "min-h-[44px] rounded-md border border-line bg-paper px-4 text-sm font-bold text-[#5e4b96] transition-transform active:translate-x-[2px] active:translate-y-[3px] active:shadow-none disabled:opacity-40",
  primary:
    "min-h-[44px] rounded-md bg-primary hover:bg-primary-hover px-5 text-sm font-bold text-white disabled:bg-[#ddd6ca] disabled:text-ink-soft transition-transform active:translate-x-[2px] active:translate-y-[3px] active:shadow-none",
  /** 패널 아래 가벼운 글자 버튼(「지우고 다시 만들기」). */
  plain: "min-h-[44px] text-sm text-[#5c5243] underline underline-offset-2 disabled:opacity-40",
};
export const tabClass = (active: boolean) =>
  `min-h-[44px] border-b-2 px-1 text-[15px] font-bold ${active ? "border-[#7053a0] text-[#2b2826]" : "border-transparent text-ink-soft"}`;
/** 문서 위 쪽 · 구간 버튼. */
export const pageClass = (active: boolean) =>
  `min-h-[34px] min-w-[52px] rounded-lg px-3 text-sm ${active ? "bg-[#efe8f7] font-bold text-[#5e4b96]" : "text-[#5c5243] hover:bg-[#f3efe8]"}`;

/** 제목 옆 「←」 돌아가기 — 만들기 · 편집 화면이 같이 쓴다. 갈 곳 이름은 aria-label · title 로. */
export const BACK_BUTTON =
  "flex h-11 w-11 shrink-0 items-center justify-center rounded-md border border-line bg-paper transition-transform active:translate-x-[1px] active:translate-y-[2px] active:shadow-none text-[#2b2826] no-underline hover:bg-[#f7f4ee] disabled:opacity-40";
export const BACK_ICON = (
  <svg
    viewBox="0 0 24 24"
    width="22"
    height="22"
    fill="none"
    stroke="currentColor"
    strokeWidth="2.4"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <path d="M19 12H5" />
    <path d="m12 19-7-7 7-7" />
  </svg>
);

type Format = AnnualPlanResponse["format"];
export const chip = (format: Format) => (
  <span className={`rounded-full px-3 py-1 text-[13px] font-bold ${CHIP[format][1]}`}>
    {CHIP[format][0]}
  </span>
);

/** ⑤ · Ⓜ3 결과 · 다듬기. 왼쪽 380px 패널(`aside`) · 오른쪽 문서(머리줄에 배율 · 크게 보기). 연간 · 월간이 같이 쓴다. */
export default function AnnualFrame({
  title,
  format,
  lead,
  saved,
  status,
  actions,
  notice,
  aside,
  docLabel,
  docHint,
  children,
}: {
  /** 예: 「2026 연간계획안」 · 「11월 월간계획안」. */
  title: string;
  format: Format;
  /** 제목 앞 (월간의 「←」 돌아가기). */
  lead?: ReactNode;
  /** 저장 상태(「저장 중…」 · 「저장됨」) — 연간 · 월간 · 주간 모두 형식 표시(「놀이 중심형」) 바로 옆. */
  saved?: ReactNode;
  /** 제목 아래 작은 줄(요청 사항 등). */
  status: ReactNode;
  actions: ReactNode;
  notice?: ReactNode;
  aside: ReactNode | null;
  /** 문서 머리줄 왼쪽 · 오른쪽 (놀이형은 계절 탭 · 확대 도구). */
  docLabel: ReactNode;
  docHint: ReactNode;
  children: ReactNode;
}) {
  return (
    <main className="flex w-full flex-col gap-4 px-4 pb-6 pt-[26px] text-[#2b2826] lg:h-[calc(calc(100*var(--app-vh))-60px)] lg:px-10">
      {/* 안내가 없으면 높이 0 — 연간 · 월간 · 주간 문서 틀이 같은 높이에서 시작한다. */}
      <div className="flex flex-col">
        {/* 제목 줄은 「무엇」(제목 · 형식 · 저장 상태)과 「할 일」(확정) — 요청 사항은 제목 아래 작은 줄로. */}
        <div className="flex min-h-[48px] flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            {lead}
            <div className="flex min-w-0 flex-col">
              <div className="flex flex-wrap items-center gap-3">
                <h1 className="m-0 font-display text-[34px] font-bold leading-[1.15] text-ink">
                  {title}
                </h1>
                {chip(format)}
                <span role="status" className="text-[13px] text-ink-soft">
                  {saved}
                </span>
              </div>
              {/* 빈 상태에도 높이를 잡아 둔다 — 요청 사항이 뜰 때 제목이 흔들리지 않게. */}
              <span className="min-h-[20px] text-[13px] leading-[20px] text-ink-soft">
                {status}
              </span>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">{actions}</div>
        </div>
        {notice}
      </div>
      {/* lg 미만은 세로로 쌓는다 — 고정 폭 패널이 문서를 밀거나 짓누르지 않게. */}
      <div className="flex min-h-0 flex-1 flex-col gap-4 lg:flex-row">
        {/* 편집 패널에는 장식(테이프)을 두지 않는다 — 훑어 읽기를 방해하지 않게. 완료 화면에만. */}
        {aside && (
          <aside className="relative flex w-full shrink-0 flex-col border border-line bg-paper rounded-md lg:w-[380px]">
            {aside}
          </aside>
        )}
        <section
          aria-label="문서 미리보기"
          className="flex h-[calc(80*var(--app-vh))] min-w-0 flex-1 flex-col overflow-hidden border border-shell-line bg-shell-hover shadow-[inset_0_1px_4px_rgba(52,49,47,0.08)] lg:h-auto"
        >
          {/* 도구는 따로 띠를 두지 않고 책상(문서 바탕) 위에 얹는다 — 문서가 한 줄 더 위에서 시작한다. */}
          <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-3 text-sm">
            <div className="font-bold">{docLabel}</div>
            <div className="ml-auto text-[#5c5243]">{docHint}</div>
          </div>
          <div className="min-h-0 flex-1 overflow-auto px-6 pb-8 pt-4">{children}</div>
        </section>
      </div>
    </main>
  );
}

const ZOOM_BUTTON =
  "flex min-h-[34px] min-w-[34px] items-center justify-center rounded-lg px-2 text-sm text-[#5c5243] hover:bg-[#f3efe8] disabled:opacity-35 disabled:hover:bg-transparent";
/** 문서 머리줄(편집 바)의 한 묶음 — 되돌리기 · 배율을 테두리로 나눈다. */
const TOOL_GROUP = "flex items-center gap-0.5 rounded-md border border-line bg-paper p-0.5";

const UNDO_ICON = (
  <svg
    viewBox="0 0 24 24"
    width="18"
    height="18"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <path d="M9 14 4 9l5-5" />
    <path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11" />
  </svg>
);

/** 편집 바의 되돌리기 · 다시 하기 — 글자 없이 아이콘(이름은 마우스를 올리면 · 화면 읽기). 다시 하기가 없는 화면은 `onRedo` 를 비운다. */
export function UndoRedo({
  onUndo,
  canUndo,
  onRedo,
  canRedo = false,
  disabled = false,
}: {
  onUndo: () => void;
  canUndo: boolean;
  onRedo?: () => void;
  canRedo?: boolean;
  disabled?: boolean;
}) {
  return (
    <div role="group" aria-label="되돌리기 · 다시 하기" className={TOOL_GROUP}>
      <button
        type="button"
        title="되돌리기"
        className={ZOOM_BUTTON}
        disabled={disabled || !canUndo}
        onClick={onUndo}
      >
        {UNDO_ICON}
        <span className="sr-only">되돌리기</span>
      </button>
      {onRedo && (
        <button
          type="button"
          title="다시 하기"
          className={ZOOM_BUTTON}
          disabled={disabled || !canRedo}
          onClick={onRedo}
        >
          <span className="flex -scale-x-100">{UNDO_ICON}</span>
          <span className="sr-only">다시 하기</span>
        </button>
      )}
    </div>
  );
}

/**
 * 문서 배율 — 기본은 100%(칸이 좁으면 그만큼만 줄임), 「맞춤」은 칸 폭에 맞춰 키우거나 줄임,
 * −/+ 는 그 배율로 고정. `box` 는 문서를 감싼 칸(그 폭을 잰다), `percent` 로 문서를 줄인다. 연간 · 월간이 같이 쓴다.
 */
export function useSheetZoom(
  box: RefObject<HTMLElement | null>,
  width: number,
  remeasure?: unknown,
) {
  const [zoom, setZoom] = useState<SheetZoom>({ mode: "auto", percent: 100 });
  const [fit, setFit] = useState(100);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const update = () => setFit(Math.min(150, (el.clientWidth / width) * 100));
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, [box, width, remeasure]);
  const percent =
    zoom.mode === "fit" ? fit : zoom.mode === "auto" ? Math.min(100, fit) : zoom.percent;
  const tools = (
    <div role="group" aria-label="문서 배율" className={TOOL_GROUP}>
      <button
        type="button"
        className={ZOOM_BUTTON}
        aria-label="문서 축소"
        onClick={() => setZoom({ mode: "manual", percent: stepPlaySheetZoom(percent, -1) })}
      >
        −
      </button>
      <output className="min-w-[64px] text-center text-[13px]">
        {zoom.mode === "fit" && "맞춤 "}
        {Math.round(percent)}%
      </output>
      <button
        type="button"
        className={ZOOM_BUTTON}
        aria-label="문서 확대"
        onClick={() => setZoom({ mode: "manual", percent: stepPlaySheetZoom(percent, 1) })}
      >
        +
      </button>
      <button
        type="button"
        className={ZOOM_BUTTON}
        aria-pressed={zoom.mode === "fit"}
        onClick={() => setZoom({ ...zoom, mode: zoom.mode === "fit" ? "auto" : "fit" })}
      >
        맞춤
      </button>
    </div>
  );
  return { percent, tools };
}

/** 확정하기 바로 아래에 뜨는 확인 상자 자리 — 감싸는 쪽은 `relative`. 연간 · 월간이 같이 쓴다. */
export const POPOVER = "absolute right-0 top-full z-20 mt-2 w-[380px]";

/**
 * 문서 크게 보기 — 따로 뜨는 읽기 전용 창. 쪽이 여럿이면 쪽을 골라 본다. Esc 로도 닫힌다.
 * 닫혀 있으면 문서를 그리지 않는다. 연간 · 월간 · 주간이 같이 쓴다.
 * 문서 배율(− · + · 맞춤)은 「닫고 편집 계속하기」 옆에 둔다 — 화면마다 같은 자리(하민 2026-11-06).
 */
export function BigView({
  pages,
  labels,
  width,
  render,
  dialog,
}: {
  pages: number;
  /** 쪽 탭 이름. 없으면 「1쪽 · 2쪽」. */
  labels?: string[];
  /** 문서 기준 폭(px) — 배율 「맞춤」이 이 폭을 창 폭에 맞춘다. */
  width: number;
  render: (page: number) => ReactNode;
  /** 바깥에서 닫을 때(확정 실패로 패널을 열 때). */
  dialog?: RefObject<HTMLDialogElement | null>;
}) {
  const own = useRef<HTMLDialogElement>(null);
  const ref = dialog ?? own;
  const [page, setPage] = useState<number | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const zoom = useSheetZoom(box, width, page);
  return (
    <>
      <button
        type="button"
        className="min-h-[38px] rounded-md border border-line bg-paper transition-transform active:translate-x-[1px] active:translate-y-[2px] active:shadow-none px-3 text-sm font-bold text-[#5e4b96] hover:bg-[#f6f1fb]"
        aria-haspopup="dialog"
        onClick={() => {
          setPage(0);
          ref.current?.showModal();
        }}
      >
        ⤢ 크게 보기
      </button>
      <dialog
        ref={ref}
        aria-labelledby="big-view-title"
        onClose={() => setPage(null)}
        className="m-auto h-[calc(94*var(--app-vh))] max-h-[calc(94*var(--app-vh))] w-[min(1100px,calc(96*var(--app-vw)))] max-w-none overflow-hidden rounded-[20px] bg-[#f3efe8] p-0 text-[#2b2826] backdrop:bg-black/40"
      >
        {page !== null && (
          <div className="flex h-full flex-col">
            <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[#e8e2d8] bg-white px-6 py-4">
              <div className="flex flex-wrap items-center gap-3">
                <strong id="big-view-title" className="text-[15px]">
                  문서 크게 보기
                </strong>
                <span className="rounded-full bg-[#efeae2] px-2.5 py-0.5 text-xs font-bold text-[#5c5243]">
                  읽기 전용
                </span>
                {pages > 1 && (
                  <div role="tablist" aria-label="쪽" className="flex gap-1.5">
                    {Array.from({ length: pages }, (_, i) => (
                      <button
                        key={i}
                        type="button"
                        role="tab"
                        aria-selected={page === i}
                        aria-controls="big-view-page"
                        className={pageClass(page === i)}
                        onClick={() => setPage(i)}
                      >
                        {labels?.[i] ?? `${i + 1}쪽`}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-3">
                {zoom.tools}
                <button
                  type="button"
                  className={BUTTON.outline}
                  onClick={() => ref.current?.close()}
                >
                  닫고 편집 계속하기 ×
                </button>
              </div>
            </header>
            <div id="big-view-page" className="min-h-0 flex-1 overflow-auto p-7">
              <div ref={box}>
                <div style={{ zoom: zoom.percent / 100, width }} className="mx-auto">
                  {render(page)}
                </div>
              </div>
            </div>
          </div>
        )}
      </dialog>
    </>
  );
}

/** 왼쪽 패널 안 「지금 고른 칸」 줄. */
/**
 * ⑥ 확정 후. 문서 전체(읽기 전용) · PDF · 한글 내보내기 · 월간 만들기 · 홈.
 * 확정 취소는 없다 — 고치려면 문서 보관함에서 지우고 다시 만든다(ADR-064).
 * 월간 진입은 두 형식 다 `/plans/monthly` 다 — 놀이 중심형은 그 화면이 놀이 월간 만들기로 가른다.
 */
export function AnnualDone({
  plan,
  pages,
  pageLabels,
}: {
  plan: AnnualPlanResponse;
  pages: ReactNode[];
  pageLabels?: string[];
}) {
  return (
    <PlanDone
      title={`${plan.school_year} 연간계획안을 확정했어요`}
      docLabel="확정된 연간계획안"
      format={plan.format}
      pages={pages}
      pageLabels={pageLabels}
      download={(format) => downloadAnnualHwpx(plan.id, format)}
      next={{
        href: "/plans/monthly",
        label: "월간계획안 만들기 →",
        hint: "이 연간 계획안과 연계돼요!",
      }}
    />
  );
}

/** 내보내기 버튼 — 로고만 보이고 이름은 aria-label · title. */
export const EXPORTS: Record<ExportFormat, { label: string; done: string; color: string }> = {
  pdf: { label: "PDF로 내려받기", done: "PDF로 내려받았어요.", color: "bg-[#d4483b]" },
  hwpx: {
    label: "한글 파일(hwpx)로 내려받기",
    done: "한글 파일(hwpx)로 내려받았어요.",
    color: "bg-[#2f6db5]",
  },
  hwp: {
    label: "한글 파일(hwp)로 내려받기",
    done: "한글 파일(hwp)로 내려받았어요.",
    color: "bg-[#1f4e8c]",
  },
};

/** 접힌 귀퉁이가 있는 문서 모양 + 형식 이름 띠. 받는 중이면 띠가 「…」. */
export function FileLogo({ format, busy }: { format: ExportFormat; busy: boolean }) {
  return (
    <span aria-hidden="true" className="relative block h-12 w-10">
      <svg viewBox="0 0 40 48" className="absolute inset-0 h-full w-full">
        <path
          d="M5 1h21l13 13v29a4 4 0 0 1-4 4H5a4 4 0 0 1-4-4V5a4 4 0 0 1 4-4z"
          fill="#fff"
          stroke="#cfc7ba"
          strokeWidth="2"
        />
        <path d="M26 1v9a4 4 0 0 0 4 4h9" fill="#ece6dc" stroke="#cfc7ba" strokeWidth="2" />
      </svg>
      <span
        className={`absolute -left-1.5 bottom-2 rounded px-1 py-px text-[10px] font-extrabold leading-tight tracking-tight text-white ${EXPORTS[format].color}`}
      >
        {busy ? "…" : format.toUpperCase()}
      </span>
    </span>
  );
}

/** ⑥ · Ⓜ4 확정 후 틀 — 왼쪽 확정 문서(쪽이 여럿이면 쪽 번호) · 오른쪽 280px 내보내기 · 다음 단계 · 홈 · 안내. */
export function PlanDone({
  title,
  docLabel,
  format,
  pages,
  pageLabels,
  download,
  next,
  notes,
}: {
  title: string;
  docLabel: string;
  format: Format;
  pages: ReactNode[];
  /** 쪽 탭 이름(놀이 중심형 「봄·여름 · 가을·겨울」). 없으면 「1쪽 · 2쪽」. */
  pageLabels?: string[];
  /** 파일 받기(확정본만) — PDF · HWPX · HWP. 서버 경로가 없으면 빼고, 내보내기 칸을 숨긴다. */
  download?: (format: ExportFormat) => Promise<void>;
  /** `onClick` 이 있으면 주소로 가지 않고 그것을 부른다(같은 주소 안에서 화면만 바꿀 때). */
  next: { href: string; label: string; hint: string; onClick?: () => void };
  /** 홈 아래 안내 줄(저장 · 오류 · 상위 계획안 바뀜). */
  notes?: ReactNode;
}) {
  const [page, setPage] = useState(0);
  const [exportMessage, setExportMessage] = useState("");
  const hwpx = useHwpxDownload(setExportMessage);
  const [busy, setBusy] = useState<ExportFormat | null>(null);
  const save = async (format: ExportFormat) => {
    setBusy(format);
    await hwpx.download(() => download!(format), EXPORTS[format].done);
    setBusy(null);
  };
  return (
    <main className="flex w-full flex-col gap-4 px-4 pb-6 pt-[26px] text-[#2b2826] lg:h-[calc(calc(100*var(--app-vh))-60px)] lg:px-10">
      <div className="flex flex-wrap items-center gap-3">
        <span
          aria-hidden="true"
          className="flex h-8 w-8 items-center justify-center rounded-full bg-[#3b5441] text-base font-bold text-white"
        >
          ✓
        </span>
        <h1 className="m-0 font-display text-[34px] font-bold leading-[1.2] text-ink">{title}</h1>
        {chip(format)}
      </div>
      {/* lg 미만은 세로로 쌓는다 — 고정 폭 패널이 문서를 밀거나 짓누르지 않게. */}
      <div className="flex min-h-0 flex-1 flex-col gap-4 lg:flex-row">
        <section
          aria-label={docLabel}
          className="flex h-[calc(80*var(--app-vh))] min-w-0 flex-1 flex-col overflow-hidden border border-shell-line bg-shell-hover shadow-[inset_0_1px_4px_rgba(52,49,47,0.08)] lg:h-auto"
        >
          {pages.length > 1 && (
            <div role="tablist" aria-label="쪽" className="flex gap-1.5 px-6 pt-4">
              {pages.map((_, i) => (
                <button
                  key={i}
                  type="button"
                  role="tab"
                  aria-selected={i === page}
                  className={pageClass(i === page)}
                  onClick={() => setPage(i)}
                >
                  {pageLabels?.[i] ?? `${i + 1}쪽`}
                </button>
              ))}
            </div>
          )}
          <div className="flex min-h-0 flex-1 items-start overflow-auto px-6 pb-6 pt-4 [justify-content:safe_center]">
            {pages[page]}
          </div>
        </section>
        <aside className="relative flex w-full shrink-0 flex-col gap-3 lg:w-[280px]">
          <Tape />
          {download && (
            <div className="flex flex-col gap-2 border border-line bg-paper rounded-md p-5">
              <h2 className="m-0 mb-1 text-[15px] font-bold text-[#5c5243]">내보내기</h2>
              <div className="grid grid-cols-3 gap-2">
                {(Object.keys(EXPORTS) as ExportFormat[]).map((format) => (
                  <button
                    key={format}
                    type="button"
                    aria-label={EXPORTS[format].label}
                    title={EXPORTS[format].label}
                    disabled={hwpx.exporting}
                    onClick={() => void save(format)}
                    className="flex aspect-square items-center justify-center rounded-md border border-[#ddd6ca] bg-white hover:border-[#c5b7dd] hover:bg-[#f7f4ee] disabled:opacity-50"
                  >
                    <FileLogo format={format} busy={busy === format} />
                  </button>
                ))}
              </div>
              {exportMessage && (
                <p role="status" className="m-0 text-[13px] text-[#5c5243]">
                  {exportMessage}
                </p>
              )}
            </div>
          )}
          <div className="flex flex-col gap-2 border border-line bg-paper rounded-md p-5">
            <h2 className="m-0 mb-1 text-[15px] font-bold text-[#5c5243]">다음 단계</h2>
            <Link
              href={next.href}
              onClick={
                next.onClick &&
                ((e) => {
                  e.preventDefault();
                  next.onClick?.();
                })
              }
              className="flex min-h-[56px] items-center justify-center rounded-md bg-primary hover:bg-primary-hover text-[16px] font-bold text-white transition-transform active:translate-x-[2px] active:translate-y-[3px] active:shadow-none"
            >
              {next.label}
            </Link>
            <span className="font-display text-[16px] font-bold text-ink-soft">{next.hint}</span>
          </div>
          <Link
            href="/"
            className="flex min-h-[52px] items-center justify-center gap-2 rounded-md border border-[#ddd6ca] bg-white text-[15px] font-bold text-[#2b2826] hover:bg-[#f7f4ee]"
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
              <path d="M3 11l9-7 9 7" />
              <path d="M5 10v10h14V10" />
            </svg>
            홈으로 가기
          </Link>
          <div className="flex flex-col gap-2 text-[13px] text-[#5c5243]">{notes}</div>
        </aside>
      </div>
    </main>
  );
}
