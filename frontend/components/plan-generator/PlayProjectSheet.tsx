"use client";

import type { DragEvent } from "react";
import type { PlayProjectAnnualPlan } from "@/lib/api/types";
import {
  buildPlayProjectPreviewRows,
  cellButtonId,
  fields,
  playSeason,
  type PlayField,
} from "./playProjectPagination";

const SELECTED = "outline outline-2 -outline-offset-2 outline-[#7053a0] bg-[#f6f1fb]";

/** 옮긴 줄이 새 자리에서 한 번 떠올랐다 내려앉는다. 움직임을 줄인 환경에서는 하지 않는다. */
function settle(rowKey: string) {
  if (
    typeof window === "undefined" ||
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  )
    return;
  // 상태가 바뀌어 다시 그린 뒤의 줄을 잡는다.
  requestAnimationFrame(() =>
    requestAnimationFrame(() =>
      document
        .querySelectorAll<HTMLElement>(`tr[data-row="${CSS.escape(rowKey)}"] > td`)
        .forEach((td) =>
          td.animate(
            [
              { backgroundColor: "#e9ddf7", transform: "translateY(-6px)" },
              { backgroundColor: "#f6f1fb", transform: "translateY(0)", offset: 0.6 },
              { backgroundColor: "transparent", transform: "translateY(0)" },
            ],
            { duration: 520, easing: "cubic-bezier(.2,.8,.2,1)" },
          ),
        ),
    ),
  );
}
const CELL = "border border-black px-1.5 py-1.5 align-top whitespace-pre-line";

type Props = {
  plan: PlayProjectAnnualPlan;
  /** 제목 뒤 「- 햇살반」. HWP 내려받기 제목과 같은 모양. */
  className?: string;
  picks: Record<string, string[]>;
  /** 그릴 구간. */
  periods: number[];
  /** 한 쪽에 담을 구간 수. 편집은 1(구간마다 한 쪽), 크게 보기 · ⑥ 은 2(봄·여름 / 가을·겨울 — 원래 문서 쪽 나눔). */
  perPage?: number;
  selectedCell?: { periodKey: string; rowKey: string; field: PlayField } | null;
  /** 있으면 칸을 누를 수 있다 — 왼쪽 패널이 그 칸으로 간다. */
  onSelectCell?: (periodIndex: number, rowKey: string, field: PlayField) => void;
  /** 있으면 놀이를 이 줄에 끌어놓을 수 있다 — 끈 놀이가 그 줄 자리로 옮겨 간다. */
  onDropPick?: (rowKey: string, targetRowKey: string) => void;
};

/** 놀이 중심형 연간 문서 (디자인 넘김 `V2Doc` 모양). 구간 하나가 한 쪽이다. */
export default function PlayProjectSheet({
  plan,
  className = "",
  picks,
  periods,
  selectedCell = null,
  onSelectCell,
  onDropPick,
  perPage = 1,
}: Props) {
  const rows = buildPlayProjectPreviewRows(plan, picks);
  const pages = periods
    .filter((_, i) => i % perPage === 0)
    .map((_, n) => periods.slice(n * perPage, n * perPage + perPage).map((i) => plan.periods[i]));
  return (
    <div className="flex flex-col gap-6" aria-label="연간놀이계획안 미리보기">
      {pages.map((page) => {
        return (
          <article
            key={page[0].period_key}
            aria-label={page.map((period) => period.label).join(" · ")}
            className="mx-auto w-full max-w-[860px] bg-white px-9 py-8 shadow-[0_8px_24px_-12px_rgba(43,40,38,0.25)]"
          >
            <h3 className="m-0 mb-4 text-center text-[19px] font-bold">
              {plan.school_year} 연간놀이계획안{className && ` - ${className}`}
            </h3>
            <table className="w-full table-fixed border-collapse text-[12.5px] leading-snug">
              <colgroup>
                {[8, 15, 15, 36, 26].map((w, i) => (
                  <col key={i} style={{ width: w + "%" }} />
                ))}
              </colgroup>
              <thead>
                <tr>
                  {["시기", ...fields.map((field) => field.heading)].map((h) => (
                    <th
                      key={h}
                      scope="col"
                      className="h-8 border border-black bg-[#eef1e8] font-bold"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows
                  .filter((row) => page.includes(row.period))
                  .map((row) => {
                    const period = row.period;
                    const index = plan.periods.indexOf(period);
                    const season = playSeason(period);
                    return (
                      <tr
                        key={row.key}
                        data-row={row.candidate?.row_key}
                        // 끄는 줄은 흐리게, 놓을 줄은 보라 바탕 — 색은 천천히 바뀐다.
                        className="group [&>td]:transition-[background-color,opacity] [&>td]:duration-200 [&[data-dragging]>td]:opacity-40 [&[data-drop]>td]:bg-[#efe7f8]"
                        {...(onDropPick &&
                          row.candidate && {
                            // 끌어놓을 줄 강조는 data-drop 으로만 — 상태를 두지 않는다.
                            onDragOver: (event: DragEvent<HTMLElement>) => {
                              event.preventDefault();
                              event.currentTarget.dataset.drop = "";
                            },
                            onDragLeave: (event: DragEvent<HTMLElement>) => {
                              delete event.currentTarget.dataset.drop;
                            },
                            onDrop: (event: DragEvent<HTMLElement>) => {
                              event.preventDefault();
                              delete event.currentTarget.dataset.drop;
                              const dragged = event.dataTransfer.getData("text/plain");
                              if (!dragged) return;
                              onDropPick(dragged, row.candidate!.row_key);
                              if (dragged !== row.candidate!.row_key) settle(dragged);
                            },
                          })}
                      >
                        {row.rowSpan && (
                          <th
                            scope="rowgroup"
                            rowSpan={row.rowSpan}
                            className="border border-black text-center font-bold"
                          >
                            {season.months ? (
                              <>
                                {season.months}
                                <br />
                                {season.name}
                              </>
                            ) : (
                              period.label
                            )}
                          </th>
                        )}
                        {row.candidate ? (
                          fields.map((field) => {
                            const candidate = row.candidate!;
                            const value = candidate[field.key].value;
                            const selected =
                              selectedCell?.periodKey === period.period_key &&
                              selectedCell.rowKey === candidate.row_key &&
                              selectedCell.field === field.key;
                            const center = field.key === "play_name" || field.key === "materials";
                            return (
                              <td
                                key={field.key}
                                className={`${CELL} ${field.key === "play_name" && onDropPick ? "relative" : ""} ${center ? "text-center" : ""} ${field.key === "play_name" ? "font-bold" : ""} ${selected ? SELECTED : ""} ${onSelectCell ? "cursor-pointer hover:bg-[#faf7fd]" : ""}`}
                                // 칸 어디를 눌러도 그 칸을 고른다(글자 아래 빈 곳 포함). 글자는 버튼이라 키보드도 된다.
                                onClick={
                                  onSelectCell
                                    ? (event) => {
                                        if (event.target === event.currentTarget)
                                          onSelectCell(index, candidate.row_key, field.key);
                                      }
                                    : undefined
                                }
                              >
                                {/* 순서 손잡이 — 칸 왼쪽 위, 줄에 마우스를 올렸을 때만. 문서 글자를 밀어내지 않는다. */}
                                {onDropPick && field.key === "play_name" && (
                                  <span
                                    draggable
                                    aria-hidden="true"
                                    title="끌어서 순서 바꾸기"
                                    className="absolute left-1 top-0 z-10 -translate-y-1/2 cursor-grab rounded bg-[#7053a0] px-1 text-[11px] font-bold leading-[18px] text-white opacity-0 shadow-sm transition-opacity duration-150 active:cursor-grabbing group-hover:opacity-100"
                                    onDragStart={(event) => {
                                      event.dataTransfer.setData("text/plain", candidate.row_key);
                                      event.dataTransfer.effectAllowed = "move";
                                      const tr = event.currentTarget.closest("tr");
                                      if (tr) {
                                        event.dataTransfer.setDragImage(tr, 16, 16);
                                        tr.dataset.dragging = "";
                                      }
                                    }}
                                    onDragEnd={(event) => {
                                      delete event.currentTarget.closest("tr")?.dataset.dragging;
                                    }}
                                  >
                                    ⠿{" "}
                                    {(picks[period.period_key] ?? []).indexOf(candidate.row_key) +
                                      1}
                                  </span>
                                )}
                                {onSelectCell ? (
                                  <button
                                    type="button"
                                    id={cellButtonId(
                                      period.period_key,
                                      candidate.row_key,
                                      field.key,
                                    )}
                                    aria-label={`${candidate.play_name.value} ${field.heading}`}
                                    aria-pressed={selected}
                                    className={`w-full whitespace-pre-line ${center ? "text-center" : "text-left"}`}
                                    onClick={() =>
                                      onSelectCell(index, candidate.row_key, field.key)
                                    }
                                  >
                                    {value}
                                  </button>
                                ) : (
                                  value
                                )}
                              </td>
                            );
                          })
                        ) : (
                          <td colSpan={4} className={`${CELL} text-center text-[#8a8178]`}>
                            아직 고른 놀이가 없어요
                          </td>
                        )}
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </article>
        );
      })}
    </div>
  );
}
