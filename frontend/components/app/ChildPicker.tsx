"use client";

/**
 * 아이 고르개 — 반 아이를 격자로 깔아 한 화면에 전부 보여준다.
 *
 * 전에는 `<select>` 였다. 열기 전에는 **누가 오래 안 적혔는지 알 수 없고**, 열면 열여덟
 * 줄을 눈으로 훑어 이름을 찾아야 했다. 교사가 평가제에서 제일 걱정하는 것이 기록의
 * 치우침인데 고르개가 그것을 가리고 있었다.
 *
 * 격자는 반 정원(만 5세 20명)이 한 화면에 들어간다. 좌우로 미는 형태는 쓰지 않았다 —
 * 열한 번째 아이까지 열 번을 눌러야 하고, 아이 데이터에 사진이 없어 크게 띄울 것도 없다.
 *
 * 표식(도형·색)과 횟수 계산은 `lib/workspace/child-mark.ts` 에 있다.
 */

import type { ChildEntry } from "@/lib/onboarding/types";
import { isStale, markFor, tallyFor, tallyLabel, type ChildMark } from "@/lib/workspace/child-mark";

/** 꽉 찬 도형 여섯. 테두리 도형보다 자리를 덜 먹고 멀리서도 모양이 잡힌다. */
const SHAPES = [
  "M12 21a9 9 0 1 1 0-18 9 9 0 0 1 0 18z",
  "M7.6 3h8.8A4.6 4.6 0 0 1 21 7.6v8.8A4.6 4.6 0 0 1 16.4 21H7.6A4.6 4.6 0 0 1 3 16.4V7.6A4.6 4.6 0 0 1 7.6 3z",
  "M12 2.8 21.4 20.6H2.6z",
  "M12 21s-7.8-4.5-7.8-9.8A4.4 4.4 0 0 1 12 8.2a4.4 4.4 0 0 1 7.8 3c0 5.3-7.8 9.8-7.8 9.8z",
  "M12 2.6 14.8 9.3 22 9.8 16.5 14.5 18.2 21.6 12 17.8 5.8 21.6 7.5 14.5 2 9.8 9.2 9.3z",
  "M7 19a4.7 4.7 0 0 1 .75-9.35A5.9 5.9 0 0 1 18.4 9.3 4.4 4.4 0 0 1 17.7 19z",
];

/** 셋만 쓴다. 전부 흰 카드·크림 바탕에서 3:1 을 넘는 진한 색이다. */
const TONES = ["var(--pg-primary)", "var(--pg-peach-ink)", "var(--pg-sage-ink)"];

const TILE =
  "flex min-h-[60px] flex-col justify-center gap-0.5 rounded-[10px] text-left transition-colors";
const TILE_IDLE = `${TILE} border border-line bg-paper px-2.5 py-2 hover:bg-shell-hover`;
const TILE_STALE = `${TILE} border border-note-soft-line bg-note-soft px-2.5 py-2 hover:brightness-[0.98]`;
const TILE_ON = `${TILE} border-2 border-primary bg-primary-tint px-2 py-[7px]`;

const NAME = "break-keep text-base leading-tight";
const META = "text-xs leading-tight";

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
        <span className="text-xs font-medium text-ink-soft">{label}</span>
        {onMultipleChange && (
          <label className="flex items-center gap-2 text-xs text-ink-soft">
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

      <div
        role="group"
        aria-label={`${label} 고르기`}
        className="grid grid-cols-[repeat(auto-fill,minmax(126px,1fr))] gap-x-2 gap-y-2.5"
      >
        {sorted.map((child) => {
          const tally = tallyFor(records, child.id, today);
          const on = selected.includes(child.id);
          const stale = !on && isStale(tally);
          return (
            <button
              key={child.id}
              type="button"
              aria-pressed={on}
              disabled={disabled}
              onClick={() => toggle(child.id)}
              className={on ? TILE_ON : stale ? TILE_STALE : TILE_IDLE}
            >
              <span className="flex min-w-0 items-center gap-1.5">
                <ChildShape mark={markFor(child.id)} />
                <span
                  className={`${NAME} ${on ? "font-bold text-primary-ink" : "font-medium text-ink"}`}
                >
                  {child.name}
                </span>
              </span>
              <span
                className={`${META} ${
                  on ? "text-primary-ink" : stale ? "font-bold text-sun-ink" : "text-ink-soft"
                }`}
              >
                {tallyLabel(tally)}
              </span>
            </button>
          );
        })}
      </div>

      <p className="text-xs leading-relaxed text-ink-soft">
        숫자는 이번 주에 적은 횟수예요. 연노랑 칸은 한 주 넘게 비어 있어요.
      </p>
    </div>
  );
}

/** 아이마다 고정된 도형. 이름이 있으니 읽어 줄 것은 없다. */
function ChildShape({ mark }: { mark: ChildMark }) {
  return (
    <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true" className="shrink-0">
      <path d={SHAPES[mark.shape]} style={{ fill: TONES[mark.tone] }} />
    </svg>
  );
}
