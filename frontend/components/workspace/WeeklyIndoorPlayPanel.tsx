"use client";

/**
 * Ⓦ3 「AI 후보」 — 후보형 실내 자유놀이(ADR-054 확장). 이번 주에 넣은 놀이 목록과 종류별 후보.
 * 넣기 · 순서 · 빼기는 서버가 한다. 놀이 글은 「칸 편집」에서 고친다(`onEdit`).
 */

import type { WeeklyCell, WeeklyPlan } from "@/lib/api/types";
import { CARD, PUT } from "@/components/plan-generator/PlayMonthlySafetyPanel";
import { BUTTON } from "@/components/plan-generator/AnnualFrame";

const PICKED = "border-[#7053a0] bg-[#f6f1fb]";

export default function WeeklyIndoorPlayPanel({
  plan,
  disabled,
  selected = null,
  shown = (cell) => cell.value,
  onEdit,
  onAdd,
  onOrder,
  onRemove,
}: {
  plan: WeeklyPlan;
  disabled: boolean;
  selected?: string | null;
  /** 칸의 지금 글 — 저장 전 입력 포함. */
  shown?: (cell: WeeklyCell) => string;
  onEdit: (itemId: string) => void;
  onAdd: (candidateId: string | null) => void;
  onOrder: (itemIds: string[]) => void;
  onRemove: (itemId: string) => void;
}) {
  if (!plan.indoor_play_selection || plan.status === "CONFIRMED") return null;
  const rows = plan.sections.find((s) => s.section_key === "indoor_play")?.cells ?? [];
  const candidates = (plan.activity_candidates ?? []).filter(
    (c) => c.section_key === "indoor_play",
  );
  const move = (index: number, delta: number) => {
    const ids = rows.map((c) => c.item_id);
    [ids[index], ids[index + delta]] = [ids[index + delta], ids[index]];
    onOrder(ids);
  };
  return (
    <section aria-label="실내 자유놀이" className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h2 className="m-0 text-[15px] font-bold">이번 주에 넣은 놀이</h2>
        <p className="m-0 text-[13px] text-[#5c5243]">넣은 순서대로 문서에 들어가요.</p>
      </div>
      <ol className="m-0 flex list-none flex-col gap-2 p-0">
        {rows.map((c, i) => (
          <li
            key={c.item_id}
            className={`${CARD} ${c.item_id === selected ? PICKED : "border-[#e8e2d8]"}`}
          >
            <button
              type="button"
              aria-label={`${i + 1}번 놀이 고치기`}
              className="min-w-0 flex-1 whitespace-pre-line text-left text-[14px]"
              disabled={disabled}
              onClick={() => onEdit(c.item_id)}
            >
              {shown(c).trim() || <span className="text-[#8a8178]">눌러서 직접 쓰기</span>}
            </button>
            <div className="flex shrink-0 gap-1">
              {/* 한 줄뿐이면 순서 화살표는 할 일이 없다. */}
              {rows.length > 1 && (
                <>
                  <button
                    type="button"
                    aria-label={`${i + 1}번 놀이 위로`}
                    className={BUTTON.quiet}
                    disabled={disabled || i === 0}
                    onClick={() => move(i, -1)}
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    aria-label={`${i + 1}번 놀이 아래로`}
                    className={BUTTON.quiet}
                    disabled={disabled || i === rows.length - 1}
                    onClick={() => move(i, 1)}
                  >
                    ↓
                  </button>
                </>
              )}
              <button
                type="button"
                aria-label={`${i + 1}번 놀이 빼기`}
                className={BUTTON.quiet}
                disabled={disabled || (rows.length === 1 && !shown(c).trim())}
                onClick={() => onRemove(c.item_id)}
              >
                빼기
              </button>
            </div>
          </li>
        ))}
      </ol>
      {/* 빈 줄이 남아 있으면 그 줄부터 쓰게 — 흐린 단추를 두지 않는다. */}
      {!rows.some((c) => !shown(c).trim()) && (
        <button
          type="button"
          className={`${BUTTON.outline} self-start`}
          disabled={disabled}
          onClick={() => onAdd(null)}
        >
          직접 쓸 놀이 더하기
        </button>
      )}
      {!candidates.length && (
        <p className="m-0 text-[13px] text-[#5c5243]">
          쓸 수 있는 근거가 없어 후보를 만들지 않았어요. 직접 써 주세요.
        </p>
      )}
      <ul className="m-0 flex list-none flex-col gap-2 p-0">
        {candidates.map((c) => {
          const text = c.cell.value.trim();
          // 넣으면 서버가 「[종류] - 이름」으로 옮겨 쓴다. 그 글이 목록에 있으면 넣은 후보다.
          // 교사가 옮긴 글을 고치면 다시 「넣기」로 보이지만 서버가 같은 후보는 한 번만 넣는다.
          const copied = `[${c.activity_type}] - ${c.name}`;
          const here = !!c.name.trim() && rows.some((r) => r.value.trim() === copied);
          return (
            <li key={c.cell.item_id} className={`${CARD} ${here ? PICKED : "border-[#e8e2d8]"}`}>
              <div className="min-w-0 flex-1 whitespace-pre-line text-[14px]">
                <strong className="block">
                  [{c.activity_type}] {c.name}
                </strong>
                {text || "(빈 후보)"}
              </div>
              <button
                type="button"
                aria-label={`이번 주 놀이에 넣기: ${c.name || text || "빈 후보"}`}
                className={PUT}
                disabled={disabled || !c.name.trim() || here}
                onClick={() => onAdd(c.cell.item_id)}
              >
                {here ? "넣음" : "넣기"}
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
