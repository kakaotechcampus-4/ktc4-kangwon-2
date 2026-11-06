"use client";

/**
 * Ⓦ3 「AI 후보」 — 대·소집단활동. 월간 안전교육 후보(PlayMonthlySafetyPanel)와 같은 모양:
 * 맨 위 요일마다 한 줄(넣은 활동 · 빼기), 그 아래 고른 요일의 후보 카드(+ 넣기).
 * 서버는 「[종류] 이름」으로 복사한다(weekly_activities.copy). 넣은 후보는 후보 목록에서 숨는다 —
 * 같은 활동을 다른 요일에도 두려면 위 줄을 그 요일 줄이나 문서 칸으로 끈다.
 * [+ 넣기] 뒤에는 다음 요일로 넘어간다. 마지막 요일이면 그대로 둔다.
 */

import type { WeeklyActivityCandidate, WeeklyCell, WeeklyPlan } from "@/lib/api/types";
import { DAY_NAMES } from "@/lib/weekly/section-labels";
import { DROP, GRIP, SMALL, dropTo } from "@/components/plan-generator/PlayMonthlySafetyPanel";
import { WEEKLY_ACTIVITY_DRAG } from "./WeeklySheet";

/** 칸 글이 이 후보를 넣은 글인가 — 2026-11-06 전에는 「[종류] - 이름」이었다. */
const copied = (text: string, c: WeeklyActivityCandidate) =>
  [`[${c.activity_type}] ${c.name}`, `[${c.activity_type}] - ${c.name}`].includes(text.trim());

export default function WeeklyGroupActivityPanel({
  plan,
  cellId,
  shown,
  disabled,
  onPut,
  onDrop,
  onClear,
  onSelect,
}: {
  plan: WeeklyPlan;
  /** 지금 고른 대·소집단활동 칸. */
  cellId: string;
  shown: (cell: WeeklyCell) => string;
  disabled: boolean;
  onPut: (cellId: string, candidateItemId: string) => void;
  /** 끌어 놓은 후보 — 빈 후보 · 이미 그 글인 칸은 넣지 않는다(편집기가 가린다). */
  onDrop: (cellId: string, candidateItemId: string) => void;
  onClear: (cellId: string) => void;
  onSelect: (cellId: string) => void;
}) {
  const days = plan.operating_days;
  const cells = (plan.sections.find((s) => s.section_key === "group_activity")?.cells ?? [])
    .filter((c) => c.day && days.includes(c.day))
    .sort((a, b) => days.indexOf(a.day ?? "") - days.indexOf(b.day ?? ""));
  // 나눈 요일은 「월 1」 · 「월 2」.
  const label = (cell: WeeklyCell) => {
    const same = cells.filter((c) => c.day === cell.day);
    const name = DAY_NAMES[cell.day ?? ""] ?? cell.day ?? "";
    return same.length > 1 ? `${name} ${same.indexOf(cell) + 1}` : name;
  };
  const candidates = (plan.activity_candidates ?? []).filter(
    (c) => (c.section_key ?? "group_activity") === "group_activity",
  );
  const sourceOf = (cell: WeeklyCell) =>
    candidates.find((c) => c.name.trim() && copied(shown(cell), c));
  const rest = candidates.filter((c) => !c.name.trim() || !cells.some((x) => copied(shown(x), c)));
  const current = cells.find((c) => c.item_id === cellId);
  const next = current
    ? cells.find((c) => c.day === days[days.indexOf(current.day ?? "") + 1])
    : undefined;
  const put = (id: string) => {
    onPut(cellId, id);
    if (next) onSelect(next.item_id);
  };
  const filled = cells.filter((c) => shown(c).trim()).length;
  const here = current ? label(current) : "";
  return (
    <section aria-label="대·소집단활동" className="flex flex-col gap-5">
      <section className="flex flex-col gap-2">
        <h2 className="m-0 flex items-baseline justify-between text-[18px] font-bold leading-tight">
          대·소집단활동
          <span className="text-[13px] font-normal text-ink-soft">
            {filled}/{cells.length}
            {cells.length === days.length ? "일" : "칸"} 채웠어요
          </span>
        </h2>
        <ol
          aria-label="넣은 활동"
          className="m-0 list-none divide-y divide-[#ece6dc] rounded-md border border-line bg-paper p-0"
        >
          {cells.map((cell) => {
            const text = shown(cell).trim();
            const source = sourceOf(cell);
            const head = text.match(/^(\[[^\]\n]+\])(?: - | )([\s\S]*)$/);
            const now = cell.item_id === cellId;
            return (
              <li
                key={cell.item_id}
                {...(disabled
                  ? {}
                  : dropTo((id) => onDrop(cell.item_id, id), WEEKLY_ACTIVITY_DRAG))}
                // 넣은 후보 줄은 끌어서 다른 요일 줄이나 문서 칸에 놓을 수 있다(그 요일에도 같은 활동을 둔다).
                draggable={!!source && !disabled}
                onDragStart={
                  source
                    ? (event) =>
                        event.dataTransfer.setData(
                          "text/plain",
                          WEEKLY_ACTIVITY_DRAG + source.cell.item_id,
                        )
                    : undefined
                }
                className={`flex min-h-[48px] items-center gap-2.5 py-2 pl-2 pr-3 ${source && !disabled ? "cursor-grab active:cursor-grabbing" : ""} ${now ? "bg-[#f6f1fb]" : "hover:bg-[#fbf9f5]"} ${DROP}`}
              >
                <span className={source ? "contents" : "invisible contents"}>{GRIP}</span>
                {/* 요일 · 글 자리가 요일 고르기 단추다. [빼기]는 그 옆에 따로 둔다. */}
                <button
                  type="button"
                  aria-current={now ? "true" : undefined}
                  aria-label={`${label(cell)}요일 활동 고르기${text ? `: ${text}` : " (빈 칸)"}`}
                  onClick={() => onSelect(cell.item_id)}
                  className="flex min-h-[40px] min-w-0 flex-1 items-center gap-2.5 self-stretch text-left"
                >
                  <span
                    className={`flex h-6 shrink-0 items-center justify-center rounded-full px-2 text-xs font-bold ${text ? "bg-[#efe8f7] text-primary-ink" : "border border-dashed border-[#d7d0c7] text-[#b1a89c]"}`}
                  >
                    {label(cell)}
                  </span>
                  {text ? (
                    <span className="min-w-0 flex-1 text-sm leading-snug">
                      {head ? (
                        <>
                          <b className="block text-[12px] text-[#5e4b96]">{head[1]}</b>
                          <span className="line-clamp-2">{head[2]}</span>
                        </>
                      ) : (
                        <span className="line-clamp-2">{text}</span>
                      )}
                    </span>
                  ) : (
                    <span className="flex-1 text-[13px] text-[#b1a89c]">비어 있어요</span>
                  )}
                </button>
                {text && (
                  <button
                    type="button"
                    aria-label={`${label(cell)}요일에서 빼기: ${text}`}
                    disabled={disabled}
                    onClick={() => onClear(cell.item_id)}
                    className="min-h-[36px] shrink-0 rounded-md px-2.5 text-[13px] text-ink-soft hover:bg-[#f3efe8] hover:text-ink disabled:opacity-40"
                  >
                    빼기
                  </button>
                )}
              </li>
            );
          })}
        </ol>
      </section>
      <section className="flex flex-col gap-1">
        <h3 className="m-0 flex items-center justify-between gap-2 text-[15px] font-bold text-ink">
          {here}요일 활동 후보
          {current && !shown(current).trim() && (
            <span className="shrink-0 rounded-full bg-peach-tint px-2.5 py-0.5 font-body text-[12px] font-semibold text-peach-ink">
              아직 비어 있어요
            </span>
          )}
        </h3>
        <p className="m-0 mb-1 text-[13px] text-ink-soft">
          {rest.length === 0
            ? "후보를 다 넣었어요. 위 요일의 [빼기]로 되돌릴 수 있어요."
            : `${next ? "넣으면 다음 요일로 넘어가요. " : ""}끌어서 위 요일이나 문서 칸에 놓아도 돼요.`}
        </p>
        <ul className="m-0 flex list-none flex-col gap-2 p-0">
          {rest.map((c) => {
            const id = c.cell.item_id;
            const text = c.cell.value.trim();
            const ok = !!text && !!c.name.trim();
            const note = c.description.trim() || text;
            return (
              <li
                key={id}
                draggable={ok && !disabled}
                onDragStart={(event) =>
                  event.dataTransfer.setData("text/plain", WEEKLY_ACTIVITY_DRAG + id)
                }
                className={`flex items-center gap-2.5 rounded-md border border-line bg-[#faf8f4] py-2.5 pl-2 pr-3 hover:bg-[#f5f1e9] ${ok && !disabled ? "cursor-grab active:cursor-grabbing" : ""}`}
              >
                {GRIP}
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="text-[15px] font-bold leading-snug">
                    {ok ? `[${c.activity_type}] ${c.name}` : "(빈 후보)"}
                  </span>
                  {ok && note && (
                    <span className="line-clamp-2 text-[13px] text-ink-soft">{note}</span>
                  )}
                </span>
                <button
                  type="button"
                  aria-label={`${here}요일에 넣기: ${ok ? c.name : "빈 후보"}`}
                  className={SMALL}
                  disabled={disabled || !ok}
                  onClick={() => put(id)}
                >
                  + 넣기
                </button>
              </li>
            );
          })}
        </ul>
      </section>
    </section>
  );
}
