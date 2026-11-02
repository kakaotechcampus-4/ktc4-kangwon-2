"use client";
import { slotRows } from "@/lib/plan-generator/subThemeSlots";

/** 문서에 그릴 한 달. `sub_themes` 는 입력 중 목록이라 빈 칸이 있을 수 있다. */
export interface SheetMonth {
  month: number;
  theme: string;
  sub_themes: string[];
  week_count: number;
}
/** 고른 칸 — 생활주제(`"theme"`) 또는 소주제 몇 번째 칸. */
export type ThemeSlot = { month: number; slot: "theme" | number };

const SELECTED = "outline outline-2 -outline-offset-2 outline-[#7053a0] bg-[#f6f1fb]";
const CELL = "border border-black px-1";

/**
 * 월별 주제형 연간 문서 (annual_v1_weeks.hwpx 모양). 왼쪽 3~8월 · 오른쪽 9~2월, 월 · 주 칸은 고정이다.
 * `onSelect` 가 있으면 생활주제 · 소주제 칸을 누를 수 있고, 주 수와 어긋난 칸을 표시한다.
 */
export default function AnnualThemeSheet({
  title,
  months,
  selected = null,
  flagged = [],
  onSelect,
}: {
  title: string;
  months: SheetMonth[];
  selected?: ThemeSlot | null;
  /** 확정 422 가 알려 준 달. */
  flagged?: number[];
  onSelect?: (slot: ThemeSlot) => void;
}) {
  const on = (month: number, slot: ThemeSlot["slot"]) =>
    selected?.month === month && selected.slot === slot ? SELECTED : "";
  const pick = (month: number, slot: ThemeSlot["slot"]) =>
    onSelect ? () => onSelect({ month, slot }) : undefined;
  const half = (list: SheetMonth[]) => (
    <table className="w-full table-fixed border-collapse text-[12px] leading-tight">
      <colgroup>
        {[12, 28, 8, 52].map((w, i) => (
          <col key={i} style={{ width: w + "%" }} />
        ))}
      </colgroup>
      <thead>
        <tr>
          {["월", "생활주제", "주", "소주제"].map((h) => (
            <th key={h} scope="col" className="h-7 border border-black bg-[#fff1c7] font-bold">
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {list.map((m) => {
          const rows = slotRows(m.sub_themes, m.week_count);
          const flag = flagged.includes(m.month) ? "bg-[#fdecea]" : "";
          return Array.from({ length: rows }, (_, i) => {
            const extra = i >= m.week_count;
            const value = m.sub_themes[i] ?? "";
            // 편집 중일 때만 빈 주 칸(노랑) · 주 수를 넘친 칸(빨강)을 칠한다.
            const tint =
              onSelect && extra ? "bg-[#fdecea]" : onSelect && !value.trim() ? "bg-[#fff8e1]" : "";
            return (
              <tr key={m.month + "-" + i}>
                {i === 0 && (
                  <>
                    <th
                      scope="rowgroup"
                      rowSpan={rows}
                      className={`${CELL} text-center font-bold ${flag}`}
                    >
                      {m.month}월
                    </th>
                    <td
                      rowSpan={rows}
                      className={`${CELL} text-center font-bold ${on(m.month, "theme")}`}
                    >
                      {onSelect ? (
                        <button
                          type="button"
                          className="h-full w-full"
                          onClick={pick(m.month, "theme")}
                        >
                          {m.theme}
                        </button>
                      ) : (
                        m.theme
                      )}
                    </td>
                  </>
                )}
                <td className={`${CELL} h-[19px] text-center`}>{extra ? "+" : i + 1}</td>
                <td className={`${CELL} ${tint} ${on(m.month, i)}`}>
                  {onSelect ? (
                    <button
                      type="button"
                      aria-label={`${m.month}월 ${extra ? "남는" : i + 1 + "주"} 소주제`}
                      className="min-h-[19px] w-full text-left"
                      onClick={pick(m.month, i)}
                    >
                      {value}
                    </button>
                  ) : (
                    value
                  )}
                </td>
              </tr>
            );
          });
        })}
      </tbody>
    </table>
  );
  return (
    <div className="mx-auto w-full max-w-[860px] bg-white px-9 py-8 shadow-[0_8px_24px_-12px_rgba(43,40,38,0.25)]">
      <h3 className="m-0 mb-4 text-center text-[19px] font-bold">{title}</h3>
      <div className="grid grid-cols-2 items-start">
        {half(months.slice(0, 6))}
        {half(months.slice(6))}
      </div>
    </div>
  );
}
