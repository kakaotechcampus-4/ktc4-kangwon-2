"use client";

/**
 * 아이 고르개 — 반 아이를 칩으로 깔아 한 화면에 전부 보여준다.
 *
 * 전에는 `<select>` 였다. 열기 전에는 **누가 오래 안 적혔는지 알 수 없고**, 열면 열여덟
 * 줄을 눈으로 훑어 이름을 찾아야 했다. 교사가 평가제에서 제일 걱정하는 것이 기록의
 * 치우침인데 고르개가 그것을 가리고 있었다.
 *
 * 칩은 반 정원(만 5세 20명)이 한 화면에 들어간다. 좌우로 미는 형태는 쓰지 않았다 —
 * 열한 번째 아이까지 열 번을 눌러야 하고, 아이 데이터에 사진이 없어 크게 띄울 것도 없다.
 *
 * 표식(쪽지 색)과 횟수 계산은 `lib/workspace/child-mark.ts` 에 있다.
 */

import type { ChildEntry } from "@/lib/onboarding/types";
import {
  isStale,
  markFor,
  markLetter,
  tallyFor,
  tallyLabel,
  type ChildMark,
} from "@/lib/workspace/child-mark";

/** 포스티 쪽지 색 일곱. 면 · 테두리 · 글자. 글자는 제 면 위에서 4.5:1 을 넘는다. */
const TONES = [
  ["--pg-note", "--pg-note-line", "--pg-sun-ink"],
  ["--pg-sage", "--pg-sage-line", "--pg-sage-ink"],
  ["--pg-plum", "--pg-plum-line", "--pg-primary-deep"],
  ["--pg-clay", "--pg-clay-line", "--pg-alert-ink"],
  ["--pg-primary-tint", "--pg-primary-tint-line", "--pg-primary-ink"],
  ["--pg-alert-soft", "--pg-alert-soft-line", "--pg-alert-ink"],
  ["--pg-sun-tint", "--pg-sun", "--pg-sun-ink"],
];

/*
  아이 칩 — 관찰 기록 화면의 아이 칩과 같은 물건(시안 4). 6px 모서리 · 테두리 · 도장 그림자라
  누르는 것으로 보이고, 고르면 그림자만큼 내려앉아 눌린 채로 있다. 한 주 넘게 빈 아이는 연노랑 면.
*/
const CHIP =
  "inline-flex min-h-11 items-center gap-2 rounded-md py-1 pl-2 pr-3 text-left text-[13px] font-semibold text-ink transition-transform";
const CHIP_UP =
  "shadow-pg-card active:translate-x-[2px] active:translate-y-[3px] active:shadow-none";
const CHIP_IDLE = `${CHIP} ${CHIP_UP} border border-line-strong bg-paper`;
const CHIP_STALE = `${CHIP} ${CHIP_UP} border border-note-soft-line bg-note-soft`;
const CHIP_ON = `${CHIP} translate-x-[2px] translate-y-[3px] border-2 border-ink bg-paper`;

export default function ChildPicker({
  childList,
  records,
  today,
  selected,
  onSelect,
  multiple,
  onMultipleChange,
  label = "아이",
  disabled = false,
}: {
  childList: ChildEntry[];
  /** 이 반의 기록. 「마지막 기록」과 「이번 주 횟수」를 여기서 센다. */
  records: readonly { childId: string; date: string }[];
  /** 오늘 날짜 (`YYYY-MM-DD`). 서버 시간이 아니라 화면이 보는 오늘이다. */
  today: string;
  selected: string[];
  onSelect: (ids: string[]) => void;
  multiple?: boolean;
  /** 주면 「여럿 고르기」 칸이 붙는다. 안 주면 한 명만 고른다. */
  onMultipleChange?: (on: boolean) => void;
  label?: string;
  disabled?: boolean;
}) {
  const many = !!multiple;

  // 가나다 순으로 고정한다. 기록 수 순으로 정렬하면 아이가 매번 다른 자리에 있어서
  // 교사의 손이 자리를 외우지 못한다.
  const sorted = [...childList].sort((a, b) => a.name.localeCompare(b.name, "ko"));
  const names = childList.map((c) => c.name);

  /*
    기록이 **한 건도 없는 반**에서는 빈 칸을 칠하지 않는다.

    「한 주 넘게 비었다」는 치우침을 가리키는 말인데, 처음 시작한 반은 전원이 비어 있어서
    열여덟 칸이 전부 노래진다. 가리킬 치우침이 없는데 경고만 남는다.
  */
  const started = records.length > 0;

  const toggle = (id: string) => {
    if (!many) {
      onSelect([id]);
      return;
    }
    onSelect(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]);
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-3">
        <span className="text-[13px] font-medium tracking-[0.12em] text-ink-soft">{label}</span>
        {onMultipleChange && (
          <label className="flex min-h-11 items-center gap-2 text-xs text-ink-soft">
            <input
              type="checkbox"
              checked={many}
              disabled={disabled}
              onChange={(e) => onMultipleChange(e.target.checked)}
              className="h-[18px] w-[18px] accent-[var(--pg-primary)]"
            />
            여럿 고르기
          </label>
        )}
      </div>

      <div role="group" aria-label="아이 고르기" className="flex flex-wrap gap-2.5">
        {sorted.map((child) => {
          const tally = tallyFor(records, child.id, today);
          const on = selected.includes(child.id);
          const stale = started && !on && isStale(tally);
          return (
            <button
              key={child.id}
              type="button"
              aria-pressed={on}
              disabled={disabled}
              onClick={() => toggle(child.id)}
              // 마지막 기록 · 이번 주 횟수는 마우스를 올리거나 화면 낭독기로 듣는다. 칩마다 둘째 줄을
              // 달면 「아직 없어요」가 줄줄이 붙는다(점검 M-D3).
              title={tallyLabel(tally)}
              className={on ? CHIP_ON : stale ? CHIP_STALE : CHIP_IDLE}
            >
              <ChildNote name={child.name} mark={markFor(child.id)} size={26} classNames={names} />
              <span className="break-keep">{child.name}</span>
              <span className="sr-only">, {tallyLabel(tally)}</span>
            </button>
          );
        })}
      </div>

      {started && (
        <p className="text-xs leading-relaxed text-ink-soft">연노랑 칸은 한 주 넘게 비어 있어요.</p>
      )}
    </div>
  );
}

/**
 * 아이마다 고정된 쪽지 — 이름 첫 글자를 손글씨로 적고, 오른쪽 아래 귀를 접었다.
 * 이름이 옆에 있으니 읽어 줄 것은 없다.
 */
export function ChildNote({
  name,
  mark,
  size = 24,
  classNames,
}: {
  name: string;
  mark: ChildMark;
  size?: number;
  /** 같은 반 아이 이름. 주면 표식 글자가 겹치는 아이는 두 글자로 쓴다(점검 O-E1). */
  classNames?: readonly string[];
}) {
  const [paper, line, ink] = TONES[mark.tone % TONES.length];
  const fold = Math.round(size * 0.3);
  const letter = markLetter(name, classNames);
  return (
    <span
      aria-hidden="true"
      className="relative inline-flex shrink-0 -rotate-[4deg] items-center justify-center border font-display font-bold leading-none"
      style={{
        width: size,
        height: size,
        // 두 글자면 쪽지 안에 들어가게 줄인다.
        fontSize: Math.round(size * (Array.from(letter).length > 1 ? 0.44 : 0.68)),
        background: `var(${paper})`,
        borderColor: `var(${line})`,
        color: `var(${ink})`,
        borderRadius: `3px 3px ${Math.round(size * 0.12)}px 3px`,
      }}
    >
      {letter}
      <span
        className="absolute -right-px -bottom-px rounded-tl-[3px]"
        style={{
          width: fold,
          height: fold,
          background: `linear-gradient(135deg, var(${line}) 50%, transparent 50%)`,
        }}
      />
    </span>
  );
}
