"use client";

import { useState, type ReactNode } from "react";
import type { WeeklyActivityGrid, WeeklyCell, WeeklyPlan } from "@/lib/api/types";
import { DAY_NAMES } from "@/lib/weekly/section-labels";
import s from "./WeeklyActivityPanel.module.css";

type Props = {
  plan: WeeklyPlan;
  disabled: boolean;
  renderCell: (cell: WeeklyCell, label: string) => ReactNode;
  onCopy: (cellId: string, candidateId: string) => void;
  onSplit: (cellId: string, axis: "VERTICAL" | "HORIZONTAL") => void;
  onRemove: (cellId: string) => void;
};

export default function WeeklyActivityPanel({
  plan,
  disabled,
  renderCell,
  onCopy,
  onSplit,
  onRemove,
}: Props) {
  const [selected, setSelected] = useState("");
  const grids = plan.activity_grids ?? [];
  const cells =
    plan.sections.find((section) => section.section_key === "group_activity")?.cells ?? [];
  const current = cells.some((cell) => cell.item_id === selected)
    ? selected
    : (cells[0]?.item_id ?? "");
  const readonly = plan.status === "CONFIRMED";
  const candidates = (plan.activity_candidates ?? []).filter(
    (candidate) => candidate.section_key !== "indoor_play",
  );
  const kinds = [...new Set(candidates.map((c) => c.activity_type))];
  if (!grids.length) return null;

  function node(part: WeeklyActivityGrid, day: string): ReactNode {
    if (part.cell_id) {
      const cell = cells.find((c) => c.item_id === part.cell_id);
      if (!cell) return null;
      return (
        <div className={`${s.leaf} ${current === cell.item_id ? s.selected : ""}`}>
          {renderCell(cell, `${DAY_NAMES[day]} 활동`)}
          {!readonly && (
            <div className={s.actions}>
              <button
                type="button"
                disabled={disabled}
                aria-pressed={current === cell.item_id}
                onClick={() => setSelected(cell.item_id)}
              >
                이 칸 선택
              </button>
              <button
                type="button"
                disabled={disabled}
                onClick={() => onSplit(cell.item_id, "VERTICAL")}
              >
                위아래 나누기
              </button>
              <button
                type="button"
                disabled={disabled}
                onClick={() => onSplit(cell.item_id, "HORIZONTAL")}
              >
                좌우 나누기
              </button>
              <button
                type="button"
                disabled={disabled || cells.filter((c) => c.day === day).length === 1}
                onClick={() => onRemove(cell.item_id)}
              >
                칸 삭제
              </button>
            </div>
          )}
        </div>
      );
    }
    return (
      <div
        className={s.parts}
        style={{ flexDirection: part.axis === "VERTICAL" ? "column" : "row" }}
      >
        {part.children.map((child, index) => (
          <div
            key={child.cell_id ?? child.split_id}
            style={{
              flex: index === 0 ? (part.ratio ?? 50) : 100 - (part.ratio ?? 50),
              minWidth: 0,
            }}
          >
            {node(child, day)}
          </div>
        ))}
      </div>
    );
  }

  return (
    <section className={s.panel} aria-label="대·소집단 활동 후보와 배치">
      <h3>대·소집단활동</h3>
      <p>
        한 주에 할 활동을 종류별 후보에서 골라 요일 칸에 넣어요. 칸을 나눠 여러 활동을 둘 수 있어요.
      </p>
      <div
        className={s.days}
        style={{ gridTemplateColumns: `repeat(${grids.length}, minmax(0, 1fr))` }}
      >
        {grids.map((grid, index) => (
          <section
            key={plan.operating_days[index]}
            aria-label={`${DAY_NAMES[plan.operating_days[index]]} 활동 칸`}
          >
            <h4>{DAY_NAMES[plan.operating_days[index]]}</h4>
            {node(grid, plan.operating_days[index])}
          </section>
        ))}
      </div>
      {!readonly && (
        <label className={s.target}>
          후보를 넣을 칸
          <select
            disabled={disabled}
            value={current}
            onChange={(event) => setSelected(event.target.value)}
          >
            {cells.map((cell) => (
              <option key={cell.item_id} value={cell.item_id}>
                {DAY_NAMES[cell.day ?? ""]} · {cell.value || "빈칸"}
              </option>
            ))}
          </select>
        </label>
      )}
      {!candidates.length && (
        <p>사용할 수 있는 근거가 없어 후보를 만들지 않았어요. 칸에 직접 입력할 수 있어요.</p>
      )}
      {kinds.map((kind) => (
        <section key={kind} className={s.kind} aria-label={`${kind} 후보`}>
          <h4>{kind}</h4>
          <div className={s.candidates}>
            {candidates
              .filter((c) => c.activity_type === kind)
              .map((candidate) => (
                <div key={candidate.cell.item_id}>
                  {renderCell(candidate.cell, `${kind} 후보`)}
                  {!readonly && (
                    <button
                      type="button"
                      disabled={disabled || !current || !candidate.cell.value.trim()}
                      onClick={() => onCopy(current, candidate.cell.item_id)}
                    >
                      선택한 칸에 넣기
                    </button>
                  )}
                </div>
              ))}
          </div>
        </section>
      ))}
    </section>
  );
}
