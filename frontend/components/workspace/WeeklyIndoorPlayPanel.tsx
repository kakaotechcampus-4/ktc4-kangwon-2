"use client";

import type { ReactNode } from "react";
import type { WeeklyCell, WeeklyPlan } from "@/lib/api/types";
import s from "./WeeklyActivityPanel.module.css";

type Props = {
  plan: WeeklyPlan;
  disabled: boolean;
  renderCell: (cell: WeeklyCell, label: string) => ReactNode;
  onAdd: (candidateId: string | null) => void;
  onOrder: (itemIds: string[]) => void;
  onRemove: (itemId: string) => void;
};

export default function WeeklyIndoorPlayPanel({
  plan,
  disabled,
  renderCell,
  onAdd,
  onOrder,
  onRemove,
}: Props) {
  if (!plan.indoor_play_selection) return null;
  const rows = plan.sections.find((section) => section.section_key === "indoor_play")?.cells ?? [];
  const candidates = (plan.activity_candidates ?? []).filter(
    (candidate) => candidate.section_key === "indoor_play",
  );
  const readonly = plan.status === "CONFIRMED";
  const kinds = [...new Set(candidates.map((candidate) => candidate.activity_type))];
  function move(index: number, delta: number) {
    const order = rows.map((cell) => cell.item_id);
    [order[index], order[index + delta]] = [order[index + delta], order[index]];
    onOrder(order);
  }
  return (
    <section className={`${s.panel} ${s.indoor}`} aria-label="실내 자유놀이 후보와 선택 목록">
      <h3>실내 자유놀이</h3>
      <p>
        이번 주에 할 놀이를 영역별 후보에서 골라요. 고른 놀이는 한글 문서의 넓은 칸에 목록으로
        들어가요.
      </p>
      <section aria-label="이번 주에 넣은 자유놀이">
        <h4>이번 주에 넣은 놀이 · {rows.filter((cell) => cell.value.trim()).length}개</h4>
        {rows.map((cell, index) => (
          <div key={cell.item_id} className={s.leaf}>
            {renderCell(cell, `${index + 1}번 자유놀이`)}
            {!readonly && (
              <div className={s.actions}>
                <button
                  type="button"
                  disabled={disabled || index === 0}
                  aria-label={`${index + 1}번 자유놀이 위로`}
                  onClick={() => move(index, -1)}
                >
                  위로
                </button>
                <button
                  type="button"
                  disabled={disabled || index === rows.length - 1}
                  aria-label={`${index + 1}번 자유놀이 아래로`}
                  onClick={() => move(index, 1)}
                >
                  아래로
                </button>
                <button
                  type="button"
                  disabled={disabled || (rows.length === 1 && !cell.value.trim())}
                  aria-label={`${index + 1}번 자유놀이 빼기`}
                  onClick={() => onRemove(cell.item_id)}
                >
                  빼기
                </button>
              </div>
            )}
          </div>
        ))}
        {!readonly && (
          <button
            type="button"
            disabled={disabled || rows.some((cell) => !cell.value.trim())}
            onClick={() => onAdd(null)}
          >
            직접 쓸 놀이 추가
          </button>
        )}
      </section>
      {!candidates.length && (
        <p>사용할 수 있는 근거가 없어 후보를 만들지 않았어요. 직접 입력할 수 있어요.</p>
      )}
      {!readonly &&
        kinds.map((kind) => (
          <section key={kind} className={s.kind} aria-label={`${kind} 자유놀이 후보`}>
            <h4>{kind}</h4>
            <div className={s.candidates}>
              {candidates
                .filter((candidate) => candidate.activity_type === kind)
                .map((candidate) => (
                  <div key={candidate.cell.item_id}>
                    {renderCell(candidate.cell, `${kind} 후보`)}
                    <button
                      type="button"
                      disabled={disabled || !candidate.name.trim()}
                      aria-label={`${candidate.name} 이번 주 놀이에 넣기`}
                      onClick={() => onAdd(candidate.cell.item_id)}
                    >
                      이번 주 놀이에 넣기
                    </button>
                  </div>
                ))}
            </div>
          </section>
        ))}
    </section>
  );
}
