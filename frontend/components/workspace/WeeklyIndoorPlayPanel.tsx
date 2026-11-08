"use client";

/**
 * Ⓦ3 「AI 후보」 — 후보형 실내 자유놀이(ADR-054 확장). 이번 주에 넣은 놀이 목록과 종류별 후보.
 * 넣기 · 순서 · 빼기는 서버가 한다. 놀이 글은 문서 칸을 눌러 「칸 편집」에서 고친다.
 * 놀이 고르기 판처럼 넣은 놀이 밑에 점선 빈칸이 하나 늘 있다 — 후보를 끌어 놓거나 「+」로 직접 쓸 칸을 더한다.
 * 넣은 줄 · 후보 카드 모두 점 여섯 개 손잡이로 끈다. 줄은 다른 줄에 놓으면 그 자리로 옮기고(순서 화살표는 두지 않는다), 후보 쪽에 놓으면 뺀다.
 * 넣은 후보는 아래 후보 목록에서 뺀다(PM 2026-11-06).
 */

import type { DragEvent } from "react";
import type { WeeklyCell, WeeklyPlan } from "@/lib/api/types";
import { TrendMark } from "@/components/plan-ui/PlayPickBoard";
import { DROP, GRIP, SMALL, dropTo } from "@/components/plan-generator/PlayMonthlySafetyPanel";
import { BUTTON } from "@/components/plan-generator/AnnualFrame";

/** 후보 카드를 끄는 글 머리 · 넣은 줄을 끄는 글 머리 — 서로 섞이지 않게. */
const CANDIDATE_DRAG = "weekly-indoor:";
const ROW_DRAG = "weekly-indoor-row:";

export default function WeeklyIndoorPlayPanel({
  plan,
  disabled,
  selected = null,
  shown = (cell) => cell.value,
  onAdd,
  onOrder,
  onRemove,
  onWrite,
}: {
  plan: WeeklyPlan;
  disabled: boolean;
  selected?: string | null;
  /** 칸의 지금 글 — 저장 전 입력 포함. */
  shown?: (cell: WeeklyCell) => string;
  onAdd: (candidateId: string | null) => void;
  onOrder: (itemIds: string[]) => void;
  onRemove: (itemId: string) => void;
  /** 줄을 「칸 편집」으로 연다 — 「+」로 더한 빈 줄을 눌렀을 때. */
  onWrite?: (itemId: string) => void;
}) {
  if (!plan.indoor_play_selection || plan.status === "CONFIRMED") return null;
  const rows = plan.sections.find((s) => s.section_key === "indoor_play")?.cells ?? [];
  // 넣으면 서버가 「[종류] 이름」(2026-11-06 전에는 「[종류] - 이름」)으로 옮겨 쓴다. 그 글이 목록에
  // 있으면 넣은 후보 — 아래 목록에서 뺀다. 교사가 옮긴 글을 고치면 다시 후보로 보이지만 서버가 같은
  // 후보는 한 번만 넣는다.
  const all = (plan.activity_candidates ?? []).filter((c) => c.section_key === "indoor_play");
  const candidates = all.filter((c) => {
    const put = [`[${c.activity_type}] ${c.name}`, `[${c.activity_type}] - ${c.name}`];
    return !(c.name.trim() && rows.some((r) => put.includes(r.value.trim())));
  });
  // 「+」로 더한 빈 줄도 목록에 그대로 보인다 — 누르면 「칸 편집」에서 쓴다(PM 2026-11-06).
  const ids = rows.map((c) => c.item_id);
  // 끈 줄을 놓은 줄 자리로 — 나머지 순서는 그대로.
  const moveTo = (dragged: string, target: string) => {
    if (dragged === target || !ids.includes(dragged)) return;
    const next = ids.filter((id) => id !== dragged);
    const after = ids.indexOf(dragged) < ids.indexOf(target) ? 1 : 0;
    next.splice(next.indexOf(target) + after, 0, dragged);
    onOrder(next);
  };
  const drag = (key: string) =>
    disabled
      ? {}
      : {
          draggable: true,
          onDragStart: (event: DragEvent<HTMLElement>) =>
            event.dataTransfer.setData("text/plain", key),
        };
  const grab = disabled ? "" : "cursor-grab active:cursor-grabbing";
  const listDrop = disabled ? {} : dropTo((id) => onAdd(id), CANDIDATE_DRAG);
  const restDrop = disabled ? {} : dropTo((id) => ids.includes(id) && onRemove(id), ROW_DRAG);
  return (
    <section aria-label="실내 자유놀이" className="flex flex-col gap-5">
      <section {...listDrop} className={`-m-1.5 flex flex-col gap-2 rounded-md p-1.5 ${DROP}`}>
        <h2 className="penMark m-0 font-display text-[24px] font-bold leading-tight text-ink">
          이번 주에 넣은 놀이
        </h2>
        <ol className="m-0 flex list-none flex-col gap-2 p-0">
          {rows.map((c, i) => (
            <li
              key={c.item_id}
              {...drag(ROW_DRAG + c.item_id)}
              {...(disabled ? {} : dropTo((id) => moveTo(id, c.item_id), ROW_DRAG))}
              className={`flex min-h-[48px] items-center gap-2.5 rounded-md border py-2 pl-2 pr-3 ${grab} ${DROP} ${c.item_id === selected ? "border-[#7053a0] bg-[#f6f1fb]" : "border-[#e8e2d8] bg-paper"}`}
            >
              {GRIP}
              <span
                aria-hidden="true"
                className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#efe8f7] text-xs font-bold text-primary-ink"
              >
                {i + 1}
              </span>
              {shown(c).trim() ? (
                <div className="min-w-0 flex-1 whitespace-pre-line text-[14px]">
                  {shown(c).trim()}
                </div>
              ) : (
                <button
                  type="button"
                  aria-label={`${i + 1}번 놀이 직접 쓰기`}
                  disabled={disabled || !onWrite}
                  onClick={() => onWrite?.(c.item_id)}
                  className="min-h-[32px] min-w-0 flex-1 text-left text-[13px] text-ink-soft hover:text-primary-ink"
                >
                  직접 써 주세요
                </button>
              )}
              <div className="flex shrink-0 gap-1">
                <button
                  type="button"
                  aria-label={`${i + 1}번 놀이 빼기`}
                  title="빼기"
                  className={BUTTON.remove}
                  disabled={disabled}
                  onClick={() => onRemove(c.item_id)}
                >
                  −
                </button>
              </div>
            </li>
          ))}
          {/* 늘 하나 있는 점선 빈칸 — 후보를 여기로 끌어 놓거나 「+」로 직접 쓸 칸을 더한다. 채우면 밑에 또 생긴다. */}
          <li className="flex min-h-[48px] items-center justify-center rounded-md border-2 border-dashed border-[#ddd6ca]">
            <button
              type="button"
              aria-label="직접 쓸 놀이 더하기"
              title="직접 쓸 놀이 더하기"
              disabled={disabled}
              onClick={() => onAdd(null)}
              className="pgPlus h-9 w-9 rounded-[10px] text-[#5e4b96] hover:bg-[#f6f1fb] disabled:opacity-40"
            >
              +
            </button>
          </li>
        </ol>
      </section>
      {!all.length && (
        <p className="m-0 text-[13px] text-[#5c5243]">
          쓸 수 있는 근거가 없어 후보를 만들지 않았어요. 직접 써 주세요.
        </p>
      )}
      {candidates.length > 0 && (
        <section {...restDrop} className={`-m-1.5 flex flex-col gap-1 rounded-md p-1.5 ${DROP}`}>
          <h3 className="m-0 text-[15px] font-bold text-ink">놀이 후보</h3>
          <ul className="m-0 flex list-none flex-col gap-2 p-0">
            {candidates.map((c) => {
              const text = c.cell.value.trim();
              const ok = !!c.name.trim();
              return (
                <li
                  key={c.cell.item_id}
                  {...(ok ? drag(CANDIDATE_DRAG + c.cell.item_id) : {})}
                  className={`flex items-center gap-2.5 rounded-md border border-line bg-[#faf8f4] py-2.5 pl-2 pr-3 hover:bg-[#f5f1e9] ${ok ? grab : ""}`}
                >
                  {GRIP}
                  <div className="min-w-0 flex-1 whitespace-pre-line text-[14px]">
                    <strong className="block">
                      [{c.activity_type}] {c.name}
                    </strong>
                    {text || "(빈 후보)"}
                  </div>
                  {ok && c.trend_applied && <TrendMark />}
                  <button
                    type="button"
                    aria-label={`이번 주 놀이에 넣기: ${c.name || text || "빈 후보"}`}
                    className={SMALL}
                    disabled={disabled || !ok}
                    onClick={() => onAdd(c.cell.item_id)}
                  >
                    +
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </section>
  );
}
