"use client";

import type { PlayProjectAnnualPlan } from "@/lib/api/types";
import {
  buildPlayProjectPreviewRows,
  cellButtonId,
  fields,
  type PlayField,
} from "./playProjectPagination";

const SELECTED = "outline outline-2 -outline-offset-2 outline-[#7053a0] bg-[#f6f1fb]";
const CELL = "border border-black px-1.5 py-1.5 align-top whitespace-pre-line";

type Props = {
  plan: PlayProjectAnnualPlan;
  picks: Record<string, string[]>;
  /** 그릴 구간(쪽). 구간마다 한 쪽이다. */
  periods: number[];
  selectedCell?: { periodKey: string; rowKey: string; field: PlayField } | null;
  /** 있으면 칸을 누를 수 있다 — 왼쪽 패널이 그 칸으로 간다. */
  onSelectCell?: (periodIndex: number, rowKey: string, field: PlayField) => void;
};

/** 놀이 중심형 연간 문서 (디자인 넘김 `V2Doc` 모양). 구간 하나가 한 쪽이다. */
export default function PlayProjectSheet({
  plan,
  picks,
  periods,
  selectedCell = null,
  onSelectCell,
}: Props) {
  const rows = buildPlayProjectPreviewRows(plan, picks);
  return (
    <div className="flex flex-col gap-6" aria-label="연간놀이계획안 미리보기">
      {periods.map((index) => {
        const period = plan.periods[index];
        return (
          <article
            key={period.period_key}
            aria-label={period.label}
            className="mx-auto w-full max-w-[860px] bg-white px-9 py-8 shadow-[0_8px_24px_-12px_rgba(43,40,38,0.25)]"
          >
            <h3 className="m-0 mb-4 border border-black bg-[#E1F2FE] py-2 text-center text-[19px] font-bold">
              {plan.school_year} 연간놀이계획안
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
                      className="h-8 border border-black bg-[#E1F2FE] font-bold"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows
                  .filter((row) => row.period === period)
                  .map((row) => (
                    <tr key={row.key}>
                      {row.rowSpan && (
                        <th
                          scope="rowgroup"
                          rowSpan={row.rowSpan}
                          className="border border-black text-center font-bold"
                        >
                          {period.label}
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
                              className={`${CELL} ${center ? "text-center" : ""} ${field.key === "play_name" ? "font-bold" : ""} ${selected ? SELECTED : ""}`}
                            >
                              {onSelectCell ? (
                                <button
                                  type="button"
                                  id={cellButtonId(period.period_key, candidate.row_key, field.key)}
                                  aria-label={`${candidate.play_name.value} ${field.heading}`}
                                  aria-pressed={selected}
                                  className={`w-full whitespace-pre-line ${center ? "text-center" : "text-left"}`}
                                  onClick={() => onSelectCell(index, candidate.row_key, field.key)}
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
                  ))}
              </tbody>
            </table>
            <p className="mt-5 bg-[#E1F2FE] px-2 py-1 text-center text-[10px] leading-relaxed">
              {
                "*예상 놀이 방향은 [2019 개정 누리과정]의 목적에 따라 ‘유아 놀이 중심’ 활동이 진행 될 수 있도록 융통성 있게 구성되었습니다. "
              }
              <br />
              {"*유아들의 흥미도와 참여 정도에 따라 다른 방향으로 조정됩니다."}
            </p>
          </article>
        );
      })}
    </div>
  );
}
