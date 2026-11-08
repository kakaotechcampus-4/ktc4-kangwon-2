"use client";
/**
 * 놀이 고르기 (놀이 중심형, 생성 직후) — 3패널. 놀이 중심형 월간의 활동 고르기도 같은 판을 쓴다(ADR-065).
 * 홈 화면과 같은 말투: 왼쪽은 줄 친 공책, 가운데는 테이프로 붙인 종이, 오른쪽은 홈의 칠판에 쪽지를 붙인다.
 *
 * 상호작용
 * - 왼쪽 줄을 누르면 가운데에 그 놀이를 띄운다(보는 중 = 왼쪽 보라 띠). 고르지는 않는다.
 *   고른 줄은 세이지 바탕 + 손그림 체크 — 「보는 중」과 「고름」을 색 하나로 겹쳐 쓰지 않는다.
 * - 가운데 맨 아래: 안 고른 놀이는 보라 [+ 고르기], 고른 놀이는 빨간 [− 빼기] — 같은 크기 같은 자리.
 *   글자만 바뀌는 한 모양 단추는 지금 상태와 누르면 일어날 일이 헷갈려서, 색과 기호로 동작을 가른다.
 *   빼기는 칠판 쪽지의 [−]와 같은 빨간 모양이라 같은 동작으로 읽힌다. 고른 상태는 왼쪽 체크와 칠판이 보여 준다.
 * - 오른쪽 칠판: 칸 max 개가 고른 순서대로 쪽지로 채워진다. [−]로 빼기. 계절당 최대 5개(서버 규칙).
 *
 * 색은 뜻 하나에 하나: 보라 = 누르는 것 · 지금 보는 줄, 세이지 = 고름, 빨강 = 빼기, 노랑 = 형광펜 · 쪽지.
 *
 * 계절 탭(월간은 목록 탭)은 이 판 밖에 있다. 판은 지금 계절(목록) 하나만 그린다.
 */
import type { ReactNode } from "react";
import { Tape } from "@/components/workspace/WorkspaceUI";

export type PickCandidate = {
  key: string;
  name: string;
  /** 왼쪽 줄의 둘째 줄(월간: 설명). 없으면 이름만. */
  summary?: string;
  /** 가운데 「자세히 보기」의 항목들 — 이름표와 줄. */
  fields: { label: string; lines: string[] }[];
  /** 요청 사항을 반영한 후보 — 작은 표시만 단다. */
  memoApplied?: boolean;
  /** 트렌드봇 자료를 반영한 후보(ADR-072) — 같은 자리에 빨간 ✦ 만 단다. */
  trendApplied?: boolean;
};

/** 요청 사항을 반영한 후보의 작은 표시(Human Decision 2026-11-05). 글자 배지 대신 조용한 ✦. */
export function MemoMark() {
  // relative — 숨은 글자(sr-only, absolute)가 스크롤 상자를 빠져나가 페이지를 늘이지 않게.
  return (
    <span
      title="요청을 반영한 놀이"
      className="relative shrink-0 text-[13px] leading-none text-[#7053a0]"
    >
      <span aria-hidden="true">✦</span>
      <span className="sr-only">요청을 반영한 놀이</span>
    </span>
  );
}

/**
 * 트렌드봇 자료를 반영한 후보의 작은 표시(ADR-072, Human Decision 2026-11-08).
 * 요청 사항 ✦ 와 같은 모양 · 자리 · 크기, 빨간색만 다르다. 화면 · 글에 다른 표시는 두지 않는다.
 */
export function TrendMark() {
  return (
    <span
      title="트렌드를 반영한 놀이"
      className="relative shrink-0 text-[13px] leading-none text-[#b3261e]"
    >
      <span aria-hidden="true">✦</span>
      <span className="sr-only">트렌드를 반영한 놀이</span>
    </span>
  );
}

/** 칠판에 붙이는 쪽지 — 홈 칠판 쪽지와 같은 노란 한 색. 같은 모양이 한 장으로 붙어 보이지 않게 기울기만 번갈아. */
const NOTE = ["-rotate-1", "rotate-1", "-rotate-[0.6deg]", "rotate-[0.6deg]"];
const PAPER = "relative flex flex-col bg-paper shadow-pg";
/** 빼기 — 칠판 쪽지 [−]와 가운데 [빼기]가 같은 빨간 테두리를 쓴다. */
const REMOVE =
  "border-2 border-[#ecc8c2] bg-white text-[#b3261e] shadow-[0_2px_0_#ecc8c2] transition-transform hover:bg-[#fdf3f1] active:translate-y-[2px] active:shadow-none";

/** 고른 줄의 손그림 체크 도장. */
function CheckStamp() {
  return (
    <span
      aria-hidden="true"
      className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border-2 border-sage-line bg-sage-tint"
    >
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none">
        <path
          d="M4.5 12.8c1.6 1.4 3 2.9 4.3 4.7 2.6-4.6 6-8.4 10.4-11.3"
          stroke="#49654f"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  );
}

function Row({
  c,
  picked,
  focused,
  onFocus,
}: {
  c: PickCandidate;
  picked: boolean;
  focused: boolean;
  onFocus: () => void;
}) {
  return (
    // 공책 한 줄 — 칸마다 테두리 상자를 두지 않고 아래 줄 하나로 나눈다.
    <li className="border-b border-[#ece6dc] py-1 last:border-b-0">
      <button
        type="button"
        onClick={onFocus}
        aria-current={focused ? "true" : undefined}
        className={`flex min-h-[52px] w-full items-center gap-3 rounded-md px-3 py-2 text-left ${focused ? "bg-[#f3edf9] shadow-[inset_4px_0_0_#7053a0]" : picked ? "bg-[#eef5ef] hover:bg-[#e6f0e8]" : "hover:bg-[#f7f4ee]"}`}
      >
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span
            className={`line-clamp-2 text-[16.5px] leading-snug text-ink ${picked ? "font-bold" : ""}`}
          >
            {c.name}
          </span>
          {c.summary && <span className="truncate text-[14px] text-ink-soft">{c.summary}</span>}
        </span>
        {c.memoApplied && <MemoMark />}
        {c.trendApplied && <TrendMark />}
        {/* 고른 줄은 오른쪽 빈 자리에 체크 — 색만으로 고름을 알리지 않는다. */}
        {picked && <CheckStamp />}
        {picked && <span className="sr-only">(고름)</span>}
      </button>
    </li>
  );
}

/** 가운데 [고르기]/[빼기] — 같은 크기. 테두리 2px 도 같이 둬서 두 단추 상자가 똑같다. */
const ACTION =
  "flex h-[52px] w-[140px] items-center justify-center gap-2 rounded-md border-2 text-[15px] font-bold";

function Detail({
  c,
  picked,
  full,
  onToggle,
}: {
  c: PickCandidate;
  picked: boolean;
  full: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-9 pb-4 pt-9">
        <h3 className="m-0 pb-6 font-display text-[30px] font-bold leading-[1.25] text-ink">
          {c.name}
        </h3>
        {/* 항목 이름은 계획안 편집 화면의 「소주제」처럼 손글씨 + 노란 형광펜, 항목 사이는 점선. */}
        <dl className="m-0 flex max-w-[640px] flex-col">
          {c.fields.map((f) => (
            <div
              key={f.label}
              className="flex flex-col gap-2.5 border-t border-dashed border-[#d9cfbf] py-5"
            >
              <dt className="penMark self-start font-display text-[21px] font-bold leading-tight text-ink">
                {f.label}
              </dt>
              <dd className="m-0 flex flex-col gap-1 text-base leading-[1.75] text-ink">
                {f.lines.map((line, n) => (
                  <span key={n}>{line}</span>
                ))}
              </dd>
            </div>
          ))}
        </dl>
      </div>
      {/* 오른쪽 [다음] 버튼과 같은 줄 — 두 판 모두 아래 여백 16px · 버튼 높이 50px. */}
      <div className="flex min-h-[76px] items-center justify-end px-6 pb-6 pt-3">
        {picked ? (
          <button
            type="button"
            onClick={onToggle}
            aria-label={`${c.name} 빼기`}
            className={`${ACTION} ${REMOVE}`}
          >
            <span aria-hidden="true" className="pgMinus inline-block h-4 w-4" />
            빼기
          </button>
        ) : (
          // 다 골랐으면 단추 글자가 「다 골랐어요」로 바뀌고 흐려진다 — 따로 안내 글은 두지 않는다.
          <button
            type="button"
            onClick={onToggle}
            disabled={full}
            aria-label={full ? undefined : `${c.name} 고르기`}
            className={`${ACTION} border-transparent bg-primary text-white shadow-[0_3px_0_#59416e] transition-transform hover:bg-primary-hover active:translate-y-[3px] active:shadow-none disabled:opacity-40 disabled:shadow-none`}
          >
            {!full && <span aria-hidden="true" className="pgPlus inline-block h-4 w-4" />}
            {full ? "다 골랐어요" : "고르기"}
          </button>
        )}
      </div>
    </div>
  );
}

export default function PlayPickBoard({
  subject,
  icon,
  max,
  candidates,
  picked,
  focus,
  idPrefix,
  onFocus,
  onToggle,
  onRemove,
  onNext,
  nextLabel,
  onFinishEarly,
}: {
  /** 고르는 것의 이름 — 머리말에 쓴다. 예: "봄 놀이", "함께 하는 활동" */
  subject: string;
  /** 왼쪽 · 오른쪽 머리말 앞 그림(연간: 계절 아이콘). 없으면 기본 기호. */
  icon?: ReactNode;
  max: number;
  candidates: PickCandidate[];
  /** 고른 후보 key, 고른 순서 */
  picked: string[];
  /** 가운데에 띄울 후보. 없으면 첫 후보. */
  focus: string | null;
  /** 오른쪽 ✕ 와 머리말의 id 앞부분. 빼고 나면 부모가 이 id 로 포커스를 옮긴다. */
  idPrefix: string;
  onFocus: (key: string) => void;
  onToggle: (key: string) => void;
  onRemove: (key: string, slot: number) => void;
  onNext: () => void;
  nextLabel: string;
  /** 있으면 큰 버튼 아래 「지금까지 고른 것으로 문서 만들기」. */
  onFinishEarly?: () => void;
}) {
  const byKey = new Map(candidates.map((c) => [c.key, c]));
  const shown = (focus !== null && byKey.get(focus)) || candidates[0];
  const chosen = picked.map((k) => byKey.get(k)).filter((c): c is PickCandidate => !!c);
  const rest = candidates.filter((c) => !picked.includes(c.key));
  const full = picked.length >= max;
  const row = (c: PickCandidate) => (
    <Row
      key={c.key}
      c={c}
      picked={picked.includes(c.key)}
      focused={shown?.key === c.key}
      onFocus={() => onFocus(c.key)}
    />
  );

  return (
    <div className="flex w-full flex-col gap-5 text-ink lg:h-[calc(calc(100*var(--app-vh))-210px)] lg:min-h-[520px] lg:flex-row">
      <section
        aria-label={`${subject} 후보`}
        className={`max-h-[calc(60*var(--app-vh))] lg:max-h-none lg:w-[380px] lg:shrink-0 ${PAPER}`}
      >
        <Tape />
        <h2 className="m-0 flex items-center gap-2 px-6 pb-3 pt-7 font-display text-[24px] font-bold leading-tight text-ink">
          {icon}
          {subject} 후보
        </h2>
        <ul className="m-0 flex min-h-0 flex-1 list-none flex-col overflow-y-auto px-3 pb-3">
          {chosen.map(row)}
          {chosen.length > 0 && rest.length > 0 && (
            <li
              aria-hidden="true"
              className="mx-2 my-2 border-t-2 border-dashed border-[#d9cfbf]"
            />
          )}
          {rest.map(row)}
        </ul>
      </section>

      <section aria-label="놀이 자세히" className={`min-w-0 flex-1 ${PAPER}`}>
        <Tape />
        {shown && (
          <Detail
            c={shown}
            picked={picked.includes(shown.key)}
            full={full}
            onToggle={() => onToggle(shown.key)}
          />
        )}
      </section>

      {/* 홈 오른쪽 줄과 같은 칠판 — 고른 놀이를 쪽지로 붙인다. 단추는 판 아래(분필 받침 밑)에. */}
      <aside
        aria-label={`고른 ${subject}`}
        className="flex flex-col gap-6 lg:w-[300px] lg:shrink-0"
      >
        <div className="chalkboard flex min-h-0 flex-1 flex-col px-4 pb-5 pt-5">
          <h2
            id={`${idPrefix}-heading`}
            tabIndex={-1}
            className="m-0 flex items-baseline justify-between gap-2 px-1 font-display text-[22px] font-bold leading-tight text-board-ink"
          >
            고른 {subject}
            <span className="shrink-0 text-[26px]">
              {picked.length}
              <span className="text-board-ink-soft">/{max}</span>
            </span>
          </h2>
          <ol className="m-0 mt-4 flex min-h-0 flex-1 list-none flex-col gap-3.5 overflow-y-auto px-1 pb-1 pt-2">
            {/* 칸 max 개 — 빈 칸은 분필 점선, 고른 놀이는 쪽지. */}
            {Array.from({ length: max }, (_, n) => chosen[n]).map((c, n) =>
              !c ? (
                <li
                  key={"empty-" + n}
                  className="flex min-h-[52px] items-center gap-3 rounded-sm border-2 border-dashed border-[rgba(207,220,212,.5)] px-3"
                >
                  <span className="font-display text-[22px] font-bold leading-none text-board-ink-soft opacity-80">
                    {n + 1}
                  </span>
                  <span className="sr-only">빈 칸</span>
                </li>
              ) : (
                <li
                  key={c.key}
                  className={`relative flex min-h-[52px] items-center gap-2.5 border py-2 pl-3 pr-2 border-note-soft-line bg-note-soft shadow-[0_3px_7px_rgba(0,0,0,.3)] ${NOTE[n % NOTE.length]}`}
                >
                  <span
                    aria-hidden="true"
                    className="pointer-events-none absolute -top-2 left-1/2 h-4 w-11 -translate-x-1/2 -rotate-3 border-x border-white/60 bg-tape"
                  />
                  <span className="font-display text-[22px] font-bold leading-none text-ink">
                    {n + 1}
                  </span>
                  <span className="line-clamp-2 min-w-0 flex-1 text-[14.5px] font-bold leading-snug text-ink">
                    {c.name}
                  </span>
                  <button
                    type="button"
                    id={`${idPrefix}-remove-${n}`}
                    onClick={() => onRemove(c.key, n)}
                    aria-label={`${c.name} 빼기`}
                    title="빼기"
                    className={`pgMinus h-8 w-8 shrink-0 rounded-[10px] ${REMOVE}`}
                  >
                    −
                  </button>
                </li>
              ),
            )}
          </ol>
        </div>
        <div className="flex flex-col gap-2">
          {onFinishEarly && (
            <button
              type="button"
              onClick={onFinishEarly}
              className="min-h-[46px] rounded-md border-2 border-[#c5b7dd] bg-white text-[15px] font-bold text-[#5e4b96] hover:bg-[#f6f1fb]"
            >
              지금까지 고른 것으로 문서 만들기
            </button>
          )}
          <button
            type="button"
            onClick={onNext}
            className="min-h-[52px] rounded-md bg-primary text-[15px] font-bold text-white shadow-[0_3px_0_#59416e] transition-transform hover:bg-primary-hover active:translate-y-[3px] active:shadow-none"
          >
            {nextLabel}
          </button>
        </div>
      </aside>
    </div>
  );
}
