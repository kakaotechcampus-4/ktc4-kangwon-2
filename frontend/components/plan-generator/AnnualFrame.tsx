"use client";
import { useState, type ReactNode } from "react";
import Link from "next/link";
import { downloadAnnualHwpx, unconfirmAnnualPlan } from "@/lib/api/plans";
import type { AnnualPlanResponse } from "@/lib/api/types";
import { useHwpxDownload } from "@/lib/hooks/use-hwpx-download";
import UnconfirmButton from "./UnconfirmButton";

/** ⑤ · ⑥ 공통 모양 (디자인 넘김 result-preview · done-preview). */
const CHIP = {
  MONTHLY_THEME: ["월별 주제형", "bg-[#e8f1ea] text-[#3b5441]"],
  PLAY_PROJECT: ["놀이 중심형", "bg-[#eee4f4] text-[#5e4b96]"],
} as const;
export const BUTTON = {
  quiet: "min-h-[44px] rounded-xl px-3 text-sm text-[#5c5243] disabled:opacity-40",
  outline:
    "min-h-[44px] rounded-xl border border-[#ddd6ca] bg-white px-4 text-sm font-bold text-[#5e4b96] disabled:opacity-40",
  primary:
    "min-h-[44px] rounded-xl bg-[#7053a0] px-5 text-sm font-bold text-white disabled:opacity-40",
};
export const tabClass = (active: boolean) =>
  `min-h-[44px] border-b-2 px-1 text-[15px] font-bold ${active ? "border-[#7053a0] text-[#2b2826]" : "border-transparent text-[#8a8178]"}`;
/** 문서 위 쪽 · 구간 버튼. */
export const pageClass = (active: boolean) =>
  `min-h-[36px] min-w-[52px] rounded-lg border px-3 text-sm ${active ? "border-[#7053a0] bg-white font-bold text-[#5e4b96]" : "border-transparent text-[#5c5243] hover:bg-white/60"}`;

const chip = (format: AnnualPlanResponse["format"]) => (
  <span className={`rounded-full px-3 py-1 text-[13px] font-bold ${CHIP[format][1]}`}>
    {CHIP[format][0]}
  </span>
);

/** ⑤ 결과 · 다듬기. 왼쪽 380px 패널(`aside`, 전체 보기면 null) · 오른쪽 문서. */
export default function AnnualFrame({
  plan,
  status,
  actions,
  notice,
  aside,
  docLabel,
  docHint,
  children,
}: {
  plan: AnnualPlanResponse;
  status: ReactNode;
  actions: ReactNode;
  notice?: ReactNode;
  aside: ReactNode | null;
  docLabel: string;
  docHint: string;
  children: ReactNode;
}) {
  return (
    <main className="flex h-[calc(100vh-60px)] w-full flex-col gap-4 px-7 pb-6 pt-5 text-[#2b2826]">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="m-0 text-[22px] font-bold tracking-[-0.5px]">
            {plan.school_year} 연간계획안
          </h1>
          {chip(plan.format)}
          <span className="text-sm text-[#5c5243]">{status}</span>
        </div>
        <div className="flex flex-wrap items-center gap-2">{actions}</div>
      </div>
      {notice}
      <div className="flex min-h-0 flex-1 gap-4">
        {aside && (
          <aside className="flex w-[380px] shrink-0 flex-col rounded-[20px] border border-[#e8e2d8] bg-white">
            {aside}
          </aside>
        )}
        <section
          aria-label="문서 미리보기"
          className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-[20px] border border-[#e8e2d8] bg-[#f3efe8]"
        >
          <div className="flex items-center justify-between gap-3 border-b border-[#e8e2d8] bg-white px-5 py-2.5 text-sm">
            <span className="font-bold">{docLabel}</span>
            <span className="text-[#5c5243]">{docHint}</span>
          </div>
          <div className="min-h-0 flex-1 overflow-auto p-6">{children}</div>
        </section>
      </div>
    </main>
  );
}

/** 왼쪽 패널 안 「지금 고른 칸」 줄. */
export function AsideStrip({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-center gap-2 border-b border-[#efeae2] bg-[#fbf9f5] px-6 py-2.5 text-[13px] text-[#5c5243]">
      <span className="h-2 w-2 rounded-full bg-[#7053a0]" aria-hidden="true" />
      {children}
    </div>
  );
}

/**
 * ⑥ 확정 후. 문서 전체(읽기 전용) · 한글 내보내기(PDF 는 서버에 없어 숨김) · 월간 만들기 · 홈 · 확정 취소.
 * 월간 진입은 두 형식 다 `/plans/monthly` 다 — 놀이 중심형은 그 화면이 놀이 월간 만들기로 가른다.
 */
export function AnnualDone({
  plan,
  pages,
  onUnconfirmed,
  onConflict,
}: {
  plan: AnnualPlanResponse;
  pages: ReactNode[];
  onUnconfirmed: (plan: AnnualPlanResponse) => void;
  onConflict: () => void | Promise<void>;
}) {
  const [page, setPage] = useState(0);
  const [exportMessage, setExportMessage] = useState("");
  const hwpx = useHwpxDownload(setExportMessage);
  return (
    <main className="flex h-[calc(100vh-60px)] w-full flex-col gap-4 px-7 pb-6 pt-5 text-[#2b2826]">
      <div className="flex flex-wrap items-center gap-3">
        <span
          aria-hidden="true"
          className="flex h-8 w-8 items-center justify-center rounded-full bg-[#3b5441] text-base font-bold text-white"
        >
          ✓
        </span>
        <h1 className="m-0 text-[22px] font-bold tracking-[-0.5px]">
          {plan.school_year} 연간계획안을 확정했어요
        </h1>
        {chip(plan.format)}
      </div>
      <div className="flex min-h-0 flex-1 gap-4">
        <section
          aria-label="확정된 연간계획안"
          className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-[20px] border border-[#e8e2d8] bg-[#f1ede6]"
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
                  {i + 1}쪽
                </button>
              ))}
            </div>
          )}
          <div className="flex min-h-0 flex-1 items-start justify-center overflow-auto px-6 pb-6 pt-4">
            {pages[page]}
          </div>
        </section>
        <aside className="flex w-[280px] shrink-0 flex-col gap-3">
          <div className="flex flex-col gap-2 rounded-[20px] border border-[#e8e2d8] bg-white p-5">
            <h2 className="m-0 mb-1 text-[15px] font-bold text-[#5c5243]">내보내기</h2>
            <button
              type="button"
              disabled={hwpx.exporting}
              onClick={() => void hwpx.download(() => downloadAnnualHwpx(plan.id))}
              className="flex min-h-[52px] items-center gap-3 rounded-xl border border-[#ddd6ca] bg-white px-4 text-left text-[15px] font-bold hover:bg-[#f7f4ee] disabled:opacity-50"
            >
              <span className="flex h-8 w-10 items-center justify-center rounded-md bg-[#2f6db5] text-[11px] font-bold text-white">
                HWP
              </span>
              {hwpx.exporting ? "내려받는 중…" : "한글로 내보내기"}
            </button>
            {exportMessage && (
              <p role="status" className="m-0 text-[13px] text-[#5c5243]">
                {exportMessage}
              </p>
            )}
          </div>
          <div className="flex flex-col gap-2 rounded-[20px] border border-[#e8e2d8] bg-white p-5">
            <h2 className="m-0 mb-1 text-[15px] font-bold text-[#5c5243]">다음 단계</h2>
            <Link
              href="/plans/monthly"
              className="flex min-h-[56px] items-center justify-center rounded-xl bg-[#7053a0] text-[16px] font-bold text-white"
            >
              월간계획안 만들기 →
            </Link>
            <span className="text-[13px] text-[#8a8178]">이 연간계획안을 바탕으로 만들어요</span>
          </div>
          <Link
            href="/"
            className="flex min-h-[52px] items-center justify-center gap-2 rounded-xl border border-[#ddd6ca] bg-white text-[15px] font-bold text-[#2b2826] hover:bg-[#f7f4ee]"
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
          <div className="flex flex-col gap-2 text-[13px] text-[#5c5243]">
            <UnconfirmButton
              message="확정을 풀면 다시 고칠 수 있어요. 이미 만든 월간계획안은 그대로예요."
              className="min-h-[44px] self-start rounded-xl px-3 text-sm text-[#5c5243] underline"
              run={() =>
                unconfirmAnnualPlan(
                  plan.id,
                  plan.format === "PLAY_PROJECT" ? plan.revision : undefined,
                )
              }
              onDone={onUnconfirmed}
              onConflict={onConflict}
            />
          </div>
        </aside>
      </div>
    </main>
  );
}
