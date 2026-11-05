"use client";
/**
 * 놀이 고르기 (놀이 중심형, 생성 직후) — 디자인 확정본의 3패널.
 * 패널 구분: 위쪽 색 띠 + 연한 머리말. 왼쪽 후보는 한 장씩 테두리 카드. 선택 표시: 고른 것을 위로 모은다.
 *
 * 상호작용
 * - 왼쪽 줄을 누르면 가운데 '자세히 보기'에 그 놀이를 띄운다. 고르지는 않는다(고른 줄은 굵게).
 * - 고르기/빼기는 가운데 맨 아래 [이 놀이 고르기]/[✓ 골랐어요] 버튼 — 오른쪽 [다음] 버튼과 같은 높이.
 * - 오른쪽: 점선 칸 5개가 고른 순서대로 채워진다. ✕로 빼기. 계절당 최대 5개(서버 규칙).
 *
 * 계절 탭은 이 판 밖(PlayProjectResult)에 있다. 판은 지금 계절 하나만 그린다.
 */
import type { ReactNode } from "react";

export type PickCandidate = {
  key: string;
  name: string;
  materials: string;
  support: string;
  learning: string[];
  /** 요청 사항을 반영한 후보 — 작은 표시만 단다. */
  memoApplied?: boolean;
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

const TONE = { a: "#49654f", b: "#5e4b96", c: "#705936" } as const;
const TINT = { a: "#e8f1ea66", b: "#eee4f466", c: "#f8efdc66" } as const;
const STRIP = { a: "#9fbfa9", b: "#7053a0", c: "#c2a36a" } as const;
const ICON = { a: "☰", b: "◉", c: "✓" } as const;
const PANEL =
  "flex flex-col overflow-hidden rounded-[20px] border border-[#e8e2d8] border-t-[5px] bg-white";

function Head({
  tone,
  title,
  id,
  extra,
}: {
  tone: keyof typeof TONE;
  title: string;
  id?: string;
  extra?: ReactNode;
}) {
  return (
    <div
      className="flex items-center justify-between border-b border-[#f1ece4] px-5 py-3.5"
      style={{ background: TINT[tone] }}
    >
      <h2
        id={id}
        tabIndex={id ? -1 : undefined}
        className="m-0 flex items-center gap-2 text-[15px] font-bold"
      >
        <span aria-hidden="true" style={{ color: TONE[tone] }}>
          {ICON[tone]}
        </span>
        {title}
      </h2>
      {extra}
    </div>
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
    <li>
      <button
        type="button"
        onClick={onFocus}
        aria-current={focused ? "true" : undefined}
        className={`flex w-full items-center gap-3 rounded-xl border px-3 py-2.5 text-left ${focused ? "border-[#7053a0] bg-[#f6f1fb]" : "border-[#e3dccf] bg-white hover:border-[#c9bfae] hover:bg-[#fbf9f5]"}`}
      >
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span
            className={`line-clamp-2 text-[17px] leading-snug ${picked ? "font-bold text-[#2b2826]" : "text-[#5c5243]"}`}
          >
            {c.name}
          </span>
          <span className="truncate text-[14px] text-ink-soft">{c.materials}</span>
        </span>
        {c.memoApplied && <MemoMark />}
      </button>
    </li>
  );
}

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
      <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-8 pb-4 pt-5">
        <h3 className="m-0 text-[24px] font-bold leading-snug tracking-[-0.4px]">{c.name}</h3>
        <dl className="m-0 flex max-w-[640px] flex-col gap-5">
          <div className="flex flex-col gap-1.5">
            <dt className="text-sm font-bold text-[#5c5243]">지원매체</dt>
            <dd className="m-0 text-base">{c.materials}</dd>
          </div>
          <div className="flex flex-col gap-1.5">
            <dt className="text-sm font-bold text-[#5c5243]">내용 및 지원 방향</dt>
            <dd className="m-0 text-base leading-[1.75]">{c.support}</dd>
          </div>
          <div className="flex flex-col gap-1.5">
            <dt className="text-sm font-bold text-[#5c5243]">놀이를 통한 배움</dt>
            <dd className="m-0 flex flex-col gap-1 text-base">
              {c.learning.map((line) => (
                <span key={line}>{line}</span>
              ))}
            </dd>
          </div>
        </dl>
      </div>
      {/* 오른쪽 [다음] 버튼과 같은 줄 — 두 판 모두 아래 여백 16px · 버튼 높이 50px. */}
      <div className="flex items-center justify-end gap-3 p-4">
        {/* 흐린 까닭을 단추 옆에 — 다 골랐으면 하나를 빼야 바꿀 수 있다. */}
        {!picked && full && (
          <span className="text-[13px] text-ink-soft">다 골랐어요. 바꾸려면 하나를 빼 주세요.</span>
        )}
        <button
          type="button"
          onClick={onToggle}
          disabled={!picked && full}
          aria-pressed={picked}
          className={`min-h-[50px] rounded-xl px-8 text-[15px] font-bold disabled:opacity-40 ${picked ? "border border-[#c5b7dd] bg-[#f6f1fb] text-[#5e4b96]" : "bg-[#7053a0] text-white"}`}
        >
          {picked ? "✓ 골랐어요" : "이 놀이 고르기"}
        </button>
      </div>
    </div>
  );
}

export default function PlayPickBoard({
  season,
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
  /** 지금 계절 이름. 예: "3월~5월" */
  season: string;
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
    <div className="flex w-full flex-col gap-4 text-[#2b2826] lg:h-[calc(100vh-210px)] lg:min-h-[520px] lg:flex-row">
      <section
        aria-label={`${season} 놀이 후보`}
        className={`max-h-[60vh] lg:max-h-none lg:w-[400px] lg:shrink-0 ${PANEL}`}
        style={{ borderTopColor: STRIP.a }}
      >
        <Head
          tone="a"
          title={`${season} 놀이 후보 ${candidates.length}`}
          extra={
            <span className="font-display text-[17px] font-bold text-[#5c5243]">
              누르면 자세히 보여요!
            </span>
          }
        />
        <ul className="m-0 flex min-h-0 flex-1 list-none flex-col gap-2 overflow-y-auto bg-[#faf8f4] p-3">
          {chosen.length > 0 && (
            <li className="px-1 text-[13px] font-bold text-[#5e4b96]">고른 놀이 {chosen.length}</li>
          )}
          {chosen.map(row)}
          {chosen.length > 0 && rest.length > 0 && (
            <li aria-hidden="true" className="mx-1 my-1 border-t border-[#e3dccf]" />
          )}
          {rest.map(row)}
        </ul>
      </section>

      <section
        aria-label="놀이 자세히"
        className={`min-w-0 flex-1 ${PANEL}`}
        style={{ borderTopColor: STRIP.b }}
      >
        <Head tone="b" title="자세히 보기" />
        {shown && (
          <Detail
            c={shown}
            picked={picked.includes(shown.key)}
            full={full}
            onToggle={() => onToggle(shown.key)}
          />
        )}
      </section>

      <aside
        aria-label={`고른 ${season} 놀이`}
        className={`lg:w-[300px] lg:shrink-0 ${PANEL}`}
        style={{ borderTopColor: STRIP.c }}
      >
        <Head
          tone="c"
          id={`${idPrefix}-heading`}
          title={`고른 ${season} 놀이`}
          extra={
            <span className={`text-[20px] font-bold ${full ? "text-[#3b5441]" : ""}`}>
              {picked.length}/{max}
            </span>
          }
        />
        <ol className="m-0 flex min-h-0 flex-1 list-none flex-col gap-1.5 overflow-y-auto px-3 pt-3">
          {/* 칸 max 개를 점선으로 두고 고른 순서대로 채운다. */}
          {Array.from({ length: max }, (_, n) => chosen[n]).map((c, n) =>
            !c ? (
              <li
                key={"empty-" + n}
                className="flex min-h-[48px] items-center gap-3 rounded-xl border-2 border-dashed border-[#ddd6ca] px-3 text-sm text-[#b1a89c]"
              >
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-dashed border-[#d7d0c7] text-xs font-bold">
                  {n + 1}
                </span>
                <span className="sr-only">빈 칸</span>
              </li>
            ) : (
              <li
                key={c.key}
                className="flex min-h-[48px] items-center gap-3 rounded-xl border-2 border-[#e6dcf0] bg-[#fbf8f2] px-3"
              >
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-[#eee4f4] text-xs font-bold text-[#5e4b96]">
                  {n + 1}
                </span>
                <span className="min-w-0 flex-1 truncate text-sm">{c.name}</span>
                <button
                  type="button"
                  id={`${idPrefix}-remove-${n}`}
                  onClick={() => onRemove(c.key, n)}
                  aria-label={`${c.name} 빼기`}
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-ink-soft hover:bg-[#efeae2]"
                >
                  ✕
                </button>
              </li>
            ),
          )}
        </ol>
        <div className="flex flex-col gap-2 p-4">
          {onFinishEarly && (
            <button
              type="button"
              onClick={onFinishEarly}
              className="min-h-[46px] rounded-xl border-2 border-[#c5b7dd] bg-white text-[15px] font-bold text-[#5e4b96] hover:bg-[#f6f1fb]"
            >
              지금까지 고른 것으로 문서 만들기
            </button>
          )}
          <button
            type="button"
            onClick={onNext}
            className="min-h-[50px] rounded-xl bg-[#7053a0] text-[15px] font-bold text-white"
          >
            {nextLabel}
          </button>
        </div>
      </aside>
    </div>
  );
}
