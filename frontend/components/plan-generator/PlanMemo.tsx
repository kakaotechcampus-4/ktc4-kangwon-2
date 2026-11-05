"use client";

/**
 * 생성 전 「요청 사항」(ADR-060) — 연간 · 월간 · 주간 만들기의 입력 칸과, 결과 화면의 표시 한 줄.
 * 서버는 앞뒤 공백을 떼고 300자까지 받는다. 반영한 칸은 근거 패널에 「요청 사항」으로 뜬다.
 */

import { ApiError } from "@/lib/api/client";
import type { MemoNotice, PlanMemo } from "@/lib/api/types";

export const MEMO_MAX = 300;

const REASON: Record<MemoNotice["reason"], string> = {
  OUT_OF_RANGE: "참고자료 밖이에요",
  RULE_CONFLICT: "안전교육 · 기준과 맞지 않아요",
  FIXED_CELL: "위 계획안에서 가져오는 칸이에요",
};

/** 메모 때문에 막힌 422 면 입력 아래에 띄울 문구. 아니면 null — 화면의 원래 오류 처리로 간다. */
export function memoError(e: unknown): string | null {
  if (!(e instanceof ApiError) || e.status !== 422) return null;
  const fields = (e.body as { error?: { fields?: unknown } } | null)?.error?.fields;
  return Array.isArray(fields) && fields.includes("memo")
    ? "아이 이름을 빼고 다시 적어 주세요."
    : null;
}

export function PlanMemoField(props: {
  value: string;
  onChange: (value: string) => void;
  chips: string[];
  placeholder: string;
  error?: string | null;
}) {
  const { value, onChange } = props;
  const add = (chip: string) => {
    const next = value.trim() ? `${value.trim()}, ${chip}` : chip;
    if (next.length <= MEMO_MAX) onChange(next);
  };
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between">
        <label
          htmlFor="plan-memo"
          className="m-0 font-display text-[24px] font-bold leading-tight text-ink"
        >
          요청 사항
        </label>
        <span className="text-[13px] text-ink-soft">
          {value.length}/{MEMO_MAX}자
        </span>
      </div>
      <textarea
        id="plan-memo"
        value={value}
        maxLength={MEMO_MAX}
        onChange={(e) => onChange(e.target.value)}
        placeholder={props.placeholder}
        aria-invalid={!!props.error}
        aria-describedby={props.error ? "plan-memo-error" : undefined}
        className="min-h-[96px] resize-none rounded-md border border-[#ddd6ca] px-4 py-3 text-[15px] placeholder:text-ink-hint"
      />
      {props.error && (
        <p id="plan-memo-error" role="alert" className="m-0 text-sm text-[#8a2f2f]">
          {props.error}
        </p>
      )}
      <div className="flex flex-wrap gap-1.5">
        {props.chips.map((c) => (
          <button
            key={c}
            type="button"
            onClick={() => add(c)}
            className="min-h-[34px] rounded-full border border-[#ddd6ca] bg-white px-3 text-sm text-[#5c5243]"
          >
            + {c}
          </button>
        ))}
      </div>
    </div>
  );
}

/**
 * 결과 화면 상태 줄의 「요청 사항 있음」. 누르면 원문과 반영하지 못한 요청을 펼친다.
 * 메모 없이 만들었으면 아무것도 그리지 않는다.
 */
export function PlanMemoNote({ plan }: { plan: PlanMemo }) {
  const memo = plan.memo?.trim();
  const notices = plan.memo_notices ?? [];
  if (!memo) return null;
  return (
    <details className="relative">
      <summary className="cursor-pointer font-bold text-[#5e4b96]">
        요청 사항 있음{notices.length > 0 && ` · 반영 못한 요청 ${notices.length}`}
      </summary>
      {/* 제목 아래 상태 줄(화면 왼쪽)에 놓인다 — 왼쪽 끝에 맞춰 오른쪽으로 펼친다. 오른쪽 끝에 맞추면 화면 왼쪽 밖으로 잘린다. */}
      <div className="absolute left-0 z-20 mt-2 flex w-[min(360px,80vw)] flex-col gap-2 rounded-md border border-[#e8e2d8] bg-white px-4 py-3 text-left text-sm font-normal text-[#2b2826] shadow-[0_8px_24px_-12px_rgba(43,40,38,0.35)]">
        <p className="m-0 whitespace-pre-wrap">{memo}</p>
        {notices.length > 0 && (
          <div className="flex flex-col gap-1 border-t border-[#efe9df] pt-2">
            <b className="text-[#8a5a00]">반영하지 못한 요청</b>
            <ul className="m-0 flex list-disc flex-col gap-0.5 pl-5 text-[#5c5243]">
              {notices.map((n, i) => (
                <li key={i}>
                  {n.summary} — {REASON[n.reason]}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </details>
  );
}
