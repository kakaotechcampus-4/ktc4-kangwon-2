"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listAnnualPlans } from "@/lib/api/plans";
import { listMonthlyPlans } from "@/lib/api/monthly";
import { listPlayMonthly } from "@/lib/api/playMonthly";
import type { AnnualPlanSummary, MonthlyPlanSummary, PlayMonthlySummary } from "@/lib/api/types";
import { localDate } from "@/lib/workspace/model";
import AnnualImport from "./AnnualImport";

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
  title: string;
  href: string;
};

/** 「이어서 하기」 카드. 확정 안 한 연간 · 월간 초안만, 최근 만든 것부터. */
export function draftCards(
  annual: AnnualPlanSummary[],
  monthly: MonthlyPlanSummary[],
  play: PlayMonthlySummary[],
): DraftCard[] {
  const cards = [
    ...annual
      .filter((p) => p.status === "DRAFT")
      .map((p) => ({
        key: "annual-" + p.id,
        created: p.created_at,
        mode: MODE[p.format],
        title: `${p.school_year} 연간계획안`,
        href: `/plans/annual/${p.id}`,
      })),
    ...monthly
      .filter((p) => p.status === "DRAFT")
      .map((p) => ({
        key: "monthly-" + p.id,
        created: p.created_at,
        mode: MODE.MONTHLY_THEME,
        title: `${p.month}월 월간계획안`,
        href: `/plans/monthly?plan_id=${p.id}&class_id=${p.class_id}&month=${p.month}`,
      })),
    ...play
      .filter((p) => p.status === "DRAFT")
      .map((p) => ({
        key: "play-" + p.id,
        created: p.created_at,
        mode: MODE.PLAY_PROJECT,
        title: `${p.month}월 월간계획안`,
        href: `/plans/monthly/play/${p.id}`,
      })),
  ];
  return cards
    .sort((a, b) => b.created.localeCompare(a.created))
    .map((c) => ({ ...c, date: localDate(c.created) }));
}

export default function PlanNotebookPage() {
  // 월간부터 시작: 파일을 골랐거나(File) 직접 입력(null)으로 가져오기 화면을 띄운다.
  const [importing, setImporting] = useState<{ file: File | null } | null>(null);
  const [skip, setSkip] = useState(false);
  const [drafts, setDrafts] = useState<DraftCard[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const abort = new AbortController();
    Promise.allSettled([
      listAnnualPlans(undefined, abort.signal),
      listMonthlyPlans(undefined, abort.signal),
      listPlayMonthly(undefined, abort.signal),
    ]).then(([annual, monthly, play]) => {
      if (abort.signal.aborted) return;
      const items = <T,>(r: PromiseSettledResult<{ items: T[] }>) =>
        r.status === "fulfilled" ? r.value.items : [];
      // 하나만 실패해도 나머지는 보여 준다 — 없는 초안을 없다고 말하지 않도록 알린다.
      if ([annual, monthly, play].some((r) => r.status === "rejected"))
        setError("계획안 일부를 불러오지 못했어요. 새로고침해 주세요.");
      setDrafts(draftCards(items(annual), items(monthly), items(play)));
    });
    return () => abort.abort();
  }, []);

  if (importing) return <AnnualImport file={importing.file} onCancel={() => setImporting(null)} />;

  return (
    <div className="flex w-full flex-col gap-5 px-7 pb-8 pt-6 text-[#2b2826]">
      <h1 className="m-0 text-[24px] font-bold tracking-[-0.5px]">어떤 계획안을 만들까요?</h1>
      <div
        className="grid gap-4"
        style={{ gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 380px), 1fr))" }}
      >
        <Panel
          format="MONTHLY_THEME"
          skip={skip}
          onSkip={setSkip}
          onImport={(file) => setImporting({ file })}
        />
        <Panel format="PLAY_PROJECT" skip={false} onSkip={setSkip} onImport={() => {}} />
      </div>

      <section className="mt-6 flex flex-col gap-[14px] border-t border-[#e3ddd2] pt-6">
        <div className="flex items-baseline gap-3">
          <h2 className="m-0 text-lg font-bold">이어서 하기</h2>
          <span className="text-sm text-[#5c5243]">확정하지 않은 계획안이에요</span>
        </div>
        {error && (
          <p role="alert" className="m-0 text-sm text-[#a0453a]">
            {error}
          </p>
        )}
        <div
          className="grid gap-4"
          style={{ gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 260px), 1fr))" }}
        >
          {/* 목록을 받기 전에는 「없어요」라고 말하지 않는다. */}
          {drafts === null && (
            <p role="status" className="m-0 text-sm text-[#5c5243]">
              불러오는 중…
            </p>
          )}
          {drafts?.length === 0 && (
            <p className="m-0 text-sm text-[#5c5243]">쓰다 만 계획안이 없어요.</p>
          )}
          {drafts?.map((card) => (
            <PlanCard key={card.key} card={card} />
          ))}
          <Link
            href="/documents"
            className="flex flex-col items-center justify-center gap-1 rounded-2xl border border-dashed border-[#d7d0c7] px-5 py-[18px] text-center text-[#5e4b96] no-underline"
          >
            <span className="text-[15px] font-bold">문서 보관함에서 모두 보기 →</span>
            <span className="text-[13px] text-[#5c5243]">확정한 계획안도 여기 있어요</span>
          </Link>
        </div>
      </section>
    </div>
  );
}

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
 */
function Panel({
  format,
  skip,
  onSkip,
  onImport,
}: {
  format: keyof typeof MODE;
  skip: boolean;
  onSkip: (skip: boolean) => void;
  onImport: (file: File | null) => void;
}) {
  const v1 = format === "MONTHLY_THEME";
  const chip = v1 ? "bg-[#e8f1ea] text-[#3b5441]" : "bg-[#eee4f4] text-[#5e4b96]";
  const steps = v1 ? ["연간", "월간", "주간"] : ["연간", "월간"];
  return (
    <section className="flex min-h-[340px] flex-col justify-between gap-5 rounded-[20px] border border-[#e8e2d8] bg-white px-8 py-7">
      <div className="flex flex-col gap-2">
        <span className={`text-sm font-bold ${v1 ? "text-[#49654f]" : "text-[#5e4b96]"}`}>
          {v1 ? "생활주제 따라" : "아이들 놀이 따라"}
        </span>
        <h2 className="m-0 text-[28px] font-bold tracking-[-0.5px]">{MODE[format]}</h2>
        <p className="m-0 text-base leading-relaxed text-[#5c5243]">
          {v1
            ? "연간에서 월간, 월간에서 주간으로 차근차근 내려가요."
            : "놀이에서 출발해 프로젝트로 이어가요. 주간은 없어요."}
        </p>
      </div>
      <div className="flex items-center gap-[10px]">
        {steps.map((s, i) => (
          <span key={s} className="contents">
            {i > 0 && <Chevron />}
            <span className={`flex-1 rounded-xl py-4 text-center text-base font-bold ${chip}`}>
              {s}
            </span>
          </span>
        ))}
        {!v1 && (
          <span className="contents">
            <span aria-hidden="true" className="w-[18px]" />
            <span className="flex-1 rounded-xl border border-dashed border-[#d7d0c7] py-[15px] text-center text-[15px] text-[#8a8178]">
              주간 없음
            </span>
          </span>
        )}
      </div>
      {skip ? (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-3">
            {/* 파일 고르기는 브라우저 기본 창을 쓴다. 고르는 순간 가져오기 화면으로 넘어간다. */}
            <label className="flex min-h-[54px] flex-[2] cursor-pointer items-center justify-center gap-2 rounded-xl border-2 border-dashed border-[#7053a0] bg-[#f6f1fb] text-base font-bold text-[#5e4b96] focus-within:outline focus-within:outline-2 focus-within:outline-[#7053a0]">
              연간계획안 파일 올리기
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
              className="min-h-[54px] flex-1 rounded-xl border border-[#ddd6ca] bg-white text-[15px] font-bold text-[#5e4b96]"
            >
              파일 없이 직접 입력
            </button>
            <button
              type="button"
              onClick={() => onSkip(false)}
              className="min-h-[54px] px-3 text-[15px] text-[#5c5243]"
            >
              취소
            </button>
          </div>
          <p className="m-0 text-right text-[13px] text-[#5c5243]">HWP · HWPX · DOCX · PDF</p>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-3">
            <Link
              href={`/plans/annual/new?format=${format}`}
              className="flex min-h-[54px] flex-1 items-center justify-center rounded-xl bg-[#7053a0] text-base font-bold text-white no-underline"
            >
              연간부터 시작하기
            </Link>
            <button
              type="button"
              onClick={() => onSkip(true)}
              disabled={!v1}
              className="min-h-[54px] flex-1 rounded-xl border border-[#ddd6ca] bg-white text-base font-bold text-[#5e4b96] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {v1 ? "월간부터 시작하기" : "월간부터 시작하기 (준비 중)"}
            </button>
          </div>
          <p className="m-0 text-right text-[13px] text-[#5c5243]">
            {v1
              ? "월간부터 시작하면 우리 원 연간계획안을 먼저 넣어요"
              : "놀이 중심형은 연간부터 시작해요"}
          </p>
        </div>
      )}
    </section>
  );
}

function PlanCard({ card }: { card: DraftCard }) {
  return (
    <Link
      href={card.href}
      className="flex flex-col gap-3 rounded-2xl border border-[#e8e2d8] bg-white px-5 py-[18px] text-[#2b2826] no-underline"
    >
      <span className="flex items-center justify-between">
        <span className="rounded-full bg-[#f7edce] px-[10px] py-[3px] text-[13px] font-bold text-[#705936]">
          작성 중
        </span>
        <span className="text-[13px] text-[#5c5243]">{card.date}</span>
      </span>
      <span className="flex flex-col gap-0.5">
        <span className="text-[13px] text-[#5c5243]">{card.mode}</span>
        <span className="text-[17px] font-bold">{card.title}</span>
      </span>
      <span className="text-sm font-bold text-[#5e4b96]">이어서 쓰기 →</span>
    </Link>
  );
}
