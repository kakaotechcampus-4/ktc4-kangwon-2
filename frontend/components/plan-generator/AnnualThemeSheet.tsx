"use client";
import type { DragEvent, MouseEvent } from "react";
import { slotRows } from "@/lib/plan-generator/subThemeSlots";
import { HATCH } from "./PlayMonthlySheet";
import { dropCells, liftCells, settle } from "./rowDrag";

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
/** 끄는 소주제 칸 — 같은 달 안에서만 놓을 수 있다. */
let dragging: { month: number; from: number } | null = null;

/**
 * 월별 주제형 연간 문서 (annual_v1_weeks.hwpx 모양). 왼쪽 3~8월 · 오른쪽 9~2월, 월 · 주 칸은 고정이다.
 * `onSelect` 가 있으면 생활주제 · 소주제 칸을 누를 수 있고, 주 수와 어긋난 칸을 표시한다.
 * `onMove` 가 있으면 소주제 칸 왼쪽 손잡이(마우스를 올렸을 때만)로 같은 달 안에서 끌어 순서를 바꾼다.
 */
export default function AnnualThemeSheet({
  title,
  months,
  selected = null,
  flagged = [],
  onSelect,
  onMove,
}: {
  title: string;
  months: SheetMonth[];
  selected?: ThemeSlot | null;
  /** 확정 422 가 알려 준 달. */
  flagged?: number[];
  onSelect?: (slot: ThemeSlot) => void;
  onMove?: (month: number, from: number, to: number) => void;
}) {
  const on = (month: number, slot: ThemeSlot["slot"]) =>
    selected?.month === month && selected.slot === slot ? SELECTED : "";
  const pick = (month: number, slot: ThemeSlot["slot"]) =>
    onSelect ? () => onSelect({ month, slot }) : undefined;
  // 칸 어디를 눌러도 그 칸을 고른다(글자 밖 빈 곳 포함). 글자는 버튼이라 키보드도 된다.
  const area = (month: number, slot: ThemeSlot["slot"]) =>
    onSelect
      ? {
          onClick: (event: MouseEvent<HTMLElement>) => {
            if (event.target === event.currentTarget) onSelect({ month, slot });
          },
        }
      : {};
  const HOVER = onSelect ? "cursor-pointer hover:bg-[#faf7fd]" : "";
  // 읽기 전용(확정본 · 크게 보기)은 한글 내려받기처럼 주 수만큼만 줄을 긋고, 남는 소주제는 마지막 주 칸에 줄을 바꿔 잇는다.
  const rowsOf = (m: SheetMonth) =>
    onSelect ? slotRows(m.sub_themes, m.week_count) : Math.max(m.week_count, 1);
  const total = (list: SheetMonth[]) => list.reduce((n, m) => n + rowsOf(m), 0);
  const height = Math.max(total(months.slice(0, 6)), total(months.slice(6)));
  const half = (list: SheetMonth[]) => (
    <table className="w-full table-fixed border-collapse text-[13px] leading-tight">
      <colgroup>
        {/* 양식 열 폭(HWPUNIT 2500 · 7300 · 2000 · 15696)의 비율. 줄 높이 2500 ≈ 36px. */}
        {[9.1, 26.5, 7.3, 57.1].map((w, i) => (
          <col key={i} style={{ width: w + "%" }} />
        ))}
      </colgroup>
      <thead>
        <tr>
          {["월", "생활주제", "주", "소주제"].map((h) => (
            <th
              key={h}
              scope="col"
              className="h-[43px] border border-black bg-[#E1F2FE] text-[15px] font-bold"
            >
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {list.map((m) => {
          const rows = rowsOf(m);
          const flag = flagged.includes(m.month) ? "bg-[#fdecea]" : "bg-[#EEF9FE]";
          return Array.from({ length: rows }, (_, i) => {
            const extra = i >= m.week_count;
            const value =
              !onSelect && i === rows - 1
                ? m.sub_themes.slice(i).join("\n")
                : (m.sub_themes[i] ?? "");
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
                      className={`${CELL} text-center font-bold ${HOVER} ${on(m.month, "theme")}`}
                      {...area(m.month, "theme")}
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
                <td className={`${CELL} h-[36px] text-center`}>{extra ? "+" : i + 1}</td>
                <td
                  data-slot={`${m.month}-${i}`}
                  className={`${CELL} whitespace-pre-line ${HOVER} ${tint} ${on(m.month, i)} ${onMove ? "group relative pl-6 transition-[background-color,opacity] duration-200 [&[data-dragging]]:opacity-40 [&[data-drop]]:bg-[#efe7f8]" : ""}`}
                  {...area(m.month, i)}
                  {...(onMove && {
                    onDragOver: (event: DragEvent<HTMLElement>) => {
                      if (dragging?.month !== m.month) return;
                      event.preventDefault();
                      event.currentTarget.dataset.drop = "";
                    },
                    onDragLeave: (event: DragEvent<HTMLElement>) => {
                      delete event.currentTarget.dataset.drop;
                    },
                    onDrop: (event: DragEvent<HTMLElement>) => {
                      event.preventDefault();
                      delete event.currentTarget.dataset.drop;
                      dropCells();
                      const from = dragging?.month === m.month ? dragging.from : null;
                      dragging = null;
                      if (from === null || from === i) return;
                      onMove(m.month, from, i);
                      settle(`[data-slot="${m.month}-${i}"]`);
                    },
                  })}
                >
                  {onMove && value.trim() && (
                    <span
                      draggable
                      aria-hidden="true"
                      title="끌어서 순서 바꾸기"
                      className="absolute inset-y-0 left-0 z-10 flex w-5 cursor-grab items-center justify-center bg-[#7053a0] text-[11px] font-bold text-white opacity-0 transition-opacity duration-150 active:cursor-grabbing group-hover:opacity-100"
                      onDragStart={(event) => {
                        dragging = { month: m.month, from: i };
                        const td = event.currentTarget.closest("td");
                        if (td) liftCells(event, [td], `${m.month}-${i}`);
                      }}
                      onDragEnd={() => {
                        dragging = null;
                        dropCells();
                      }}
                    >
                      ⠿
                    </span>
                  )}
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
        {/* 짧은 쪽 아래 빈 칸 — 한글 내려받기(annual_hwpx.py)가 좌우 높이를 맞추려 남는 줄을 한 칸으로 합친다. */}
        {height > total(list) && (
          <tr>
            <td
              colSpan={4}
              className={`${CELL} bg-[#EEF9FE]`}
              style={{ height: (height - total(list)) * 36 }}
            />
          </tr>
        )}
      </tbody>
    </table>
  );
  return (
    <div className="mx-auto w-full min-w-[720px] max-w-[860px] bg-white px-9 py-8 shadow-[0_1px_2px_rgba(43,40,38,0.1),0_14px_32px_-14px_rgba(43,40,38,0.35)]">
      <h3 className={`m-0 mb-4 ${HATCH} py-2.5 text-center text-[28px] font-bold`}>{title}</h3>
      <div className="grid grid-cols-2 items-start">
        {half(months.slice(0, 6))}
        {half(months.slice(6))}
      </div>
      <p className="mt-5 bg-[#E1F2FE] px-2 py-1 text-center text-[12px] leading-relaxed">
        {
          "*예상 놀이 방향은 [2019 개정 누리과정]의 목적에 따라 ‘유아 놀이 중심’ 활동이 진행 될 수 있도록 융통성 있게 구성되었습니다. "
        }
        <br />
        {"*유아들의 흥미도와 참여 정도에 따라 다른 방향으로 조정됩니다."}
      </p>
    </div>
  );
}
