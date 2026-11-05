"use client";
import type { PlayMonthlyActivity, PlayMonthlyPlan } from "@/lib/api/types";
import type { PlaySection } from "@/lib/plan-generator/playMonthlyQueue";
import type { DragEvent } from "react";
import { DROP, GRIP, SMALL, dropTo } from "./PlayMonthlySafetyPanel";

export const SECTION_LABEL = {
  together: "함께 하는 활동",
  free_play: "유아 예상 자유놀이",
} as const;

/** 그 목록의 AI 후보 — 생성 순서 그대로, 넣은 것은 `picked`. */
export function sectionCandidates(plan: PlayMonthlyPlan, section: PlaySection) {
  const byId = new Map<string, { row: PlayMonthlyActivity; picked: boolean }>();
  for (const row of plan[section]) byId.set(row.activity_id, { row, picked: true });
  for (const row of plan.activity_pool ?? [])
    if (row.section === section) byId.set(row.activity_id, { row, picked: false });
  return (plan.activity_candidates ?? []).flatMap((id) => byId.get(id) ?? []);
}

/** 활동 후보를 끄는 글 머리 — 안전교육 끌기(`SAFETY_DRAG`)와 섞이지 않게. */
const ACTIVITY_DRAG = "play-activity:";

/**
 * 함께 하는 활동 · 유아 예상 자유놀이의 AI 후보 고르기(ADR-065) — 연간 「AI 후보」 패널과 같은 모양.
 * 맨 위 목록 이름 아래 넣은 활동(번호 · 빼기), 그 아래 「다른 후보」 카드(+ 넣기). 목록마다 정확히 `activity_pick` 개를 넣는다.
 * 둘 다 점 여섯 개 손잡이로 끌어 서로 옮길 수 있다 — 위로 끌면 넣고, 아래로 끌면 뺀다. 고르기 전의 후보는 고칠 수 없다(넣은 뒤 「칸 편집」).
 */
export default function PlayMonthlyActivityPanel({
  plan,
  section,
  onPick,
  onRemove,
  disabled,
}: {
  plan: PlayMonthlyPlan;
  section: PlaySection;
  onPick: (itemId: string) => void;
  onRemove: (itemId: string) => void;
  disabled: boolean;
}) {
  const max = plan.activity_pick ?? 0;
  const kept = plan[section];
  const rest = sectionCandidates(plan, section).filter((c) => !c.picked);
  const full = kept.length >= max;
  const keptIds = new Set(kept.map((row) => row.activity_id));
  const drag = (id: string) =>
    disabled
      ? {}
      : {
          draggable: true,
          onDragStart: (event: DragEvent<HTMLElement>) =>
            event.dataTransfer.setData("text/plain", ACTIVITY_DRAG + id),
        };
  const grab = disabled ? "" : "cursor-grab active:cursor-grabbing";
  const name = (row: PlayMonthlyActivity) => row.name.value.trim() || "(빈 후보)";
  const pickDrop = disabled
    ? {}
    : dropTo((id) => !keptIds.has(id) && !full && onPick(id), ACTIVITY_DRAG);
  const restDrop = disabled ? {} : dropTo((id) => keptIds.has(id) && onRemove(id), ACTIVITY_DRAG);
  return (
    <section aria-label={`${SECTION_LABEL[section]} 후보`} className="flex flex-col gap-5">
      <section {...pickDrop} className={`-m-1.5 flex flex-col gap-2 rounded-md p-1.5 ${DROP}`}>
        <h2 className="m-0 flex items-baseline justify-between text-[18px] font-bold leading-tight">
          {SECTION_LABEL[section]}
          <span
            role="status"
            className={`text-[13px] font-normal ${kept.length === max ? "text-ink-soft" : "text-peach-ink"}`}
          >
            {kept.length}/{max} 골랐어요
          </span>
        </h2>
        {kept.length > 0 ? (
          <ol className="m-0 list-none divide-y divide-[#ece6dc] rounded-md border border-line bg-paper p-0">
            {kept.map((row, index) => (
              <li
                key={row.activity_id}
                data-activity-candidate={row.activity_id}
                {...drag(row.activity_id)}
                className={`flex items-center gap-2.5 py-2.5 pl-2 pr-3 hover:bg-[#fbf9f5] ${grab}`}
              >
                {GRIP}
                <span
                  aria-hidden="true"
                  className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#efe8f7] text-xs font-bold text-primary-ink"
                >
                  {index + 1}
                </span>
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate text-[15px] font-bold">{name(row)}</span>
                  {row.description.value.trim() && (
                    <span className="truncate text-[13px] text-ink-soft">
                      {row.description.value}
                    </span>
                  )}
                </span>
                <button
                  type="button"
                  data-act="unpick"
                  aria-pressed
                  aria-label={`${SECTION_LABEL[section]}에 빼기: ${name(row)}`}
                  disabled={disabled}
                  onClick={() => onRemove(row.activity_id)}
                  className="min-h-[36px] shrink-0 rounded-md px-2.5 text-[13px] text-ink-soft hover:bg-[#f3efe8] hover:text-ink disabled:opacity-40"
                >
                  빼기
                </button>
              </li>
            ))}
          </ol>
        ) : (
          <p className="m-0 rounded-md border border-dashed border-[#d7d0c7] px-3 py-4 text-center text-[13px] text-ink-soft">
            아래 후보를 넣거나 여기로 끌어 오세요.
          </p>
        )}
      </section>
      {rest.length > 0 && (
        <section {...restDrop} className={`-m-1.5 flex flex-col gap-1 rounded-md p-1.5 ${DROP}`}>
          <h3 className="m-0 text-[15px] font-bold text-ink">다른 후보 {rest.length}개</h3>
          <p className="m-0 mb-1 text-[13px] text-ink-soft">
            {full
              ? "다 골랐어요. 바꾸려면 위에서 하나를 빼 주세요."
              : `${max}개를 골라야 확정할 수 있어요. 끌어서 위에 놓아도 돼요.`}
          </p>
          <ul className="m-0 flex list-none flex-col gap-2 p-0">
            {rest.map(({ row }) => (
              <li
                key={row.activity_id}
                data-activity-candidate={row.activity_id}
                {...drag(row.activity_id)}
                className={`flex items-center gap-2.5 rounded-md border border-line bg-[#faf8f4] py-2.5 pl-2 pr-3 hover:bg-[#f5f1e9] ${grab}`}
              >
                {GRIP}
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="text-[15px] font-bold leading-snug">{name(row)}</span>
                  {row.description.value.trim() && (
                    <span className="line-clamp-2 text-[13px] text-ink-soft">
                      {row.description.value}
                    </span>
                  )}
                </span>
                <button
                  type="button"
                  data-act="pick"
                  aria-pressed={false}
                  aria-label={`${SECTION_LABEL[section]}에 넣기: ${name(row)}`}
                  className={SMALL}
                  disabled={disabled || full}
                  onClick={() => onPick(row.activity_id)}
                >
                  + 넣기
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </section>
  );
}
