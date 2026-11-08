"use client";
import { DRILL_DRAG, DROP, GRIP, REMOVE, SMALL, dropTo } from "./PlayMonthlySafetyPanel";

/**
 * Ⓜ3 AI 후보 — 소방대피 훈련 후보를 「소방대피/재난대비」 칸에 넣는다(09c). 쓴 글이 있어도 묻지 않고 바꾼다.
 * 안전교육 패널과 같은 모양: 머리 · 넣은 것 상자([−] 빼기) · 후보 카드([+] 넣기). 달마다 칸이 하나라 상자도 한 줄.
 * 칸 글이 후보 글(머리 「[주제]」 포함, 그 전에 넣은 칸은 문장만)과 같으면 넣은 후보 — 후보 목록에서는 숨긴다.
 * 카드를 끌어(점 여섯 개) 위 상자나 문서의 소방대피/재난대비 칸에 놓아도 넣는다.
 */
export default function PlayMonthlyDrillPanel({
  candidates,
  current,
  onCopy,
  onClear,
  disabled,
}: {
  candidates: { topic_id: string; label: string; cell: { item_id: string; value: string } }[];
  current: string;
  onCopy: (itemId: string) => void;
  /** 칸을 비운다(넣은 것 상자의 [−]). */
  onClear: () => void;
  disabled: boolean;
}) {
  // 「[주제] 문장」은 lib/monthly/section-labels 의 drillText 와 같은 모양. 11-06 전에 복사한 칸은 「[주제]」 다음 줄이다.
  const now = current.trim();
  const placed = (d: { label: string; cell: { value: string } }) =>
    !!now &&
    [`[${d.label}] ${d.cell.value}`, `[${d.label}]\n${d.cell.value}`, d.cell.value]
      .map((s) => s.trim())
      .includes(now);
  const mine = candidates.find(placed);
  const rest = candidates.filter((d) => d !== mine);
  // 후보에서 넣었으면 「[화재]」 머리 + 문장, 직접 쓴 글이면 그 글 그대로.
  const sentence = mine ? mine.cell.value.trim() : now;
  return (
    <section aria-label="소방대피/재난대비" className="flex flex-col gap-5">
      <section className="flex flex-col gap-2">
        <h2 className="penMark m-0 font-display text-[24px] font-bold leading-tight text-ink">
          소방대피/재난대비
        </h2>
        <div
          {...(disabled ? {} : dropTo(onCopy, DRILL_DRAG))}
          className={`flex min-h-[48px] items-center gap-2.5 rounded-md border border-line bg-paper py-2 pl-3 pr-3 ${DROP}`}
        >
          {now ? (
            <>
              <span className="min-w-0 flex-1 text-sm leading-snug">
                {mine && <b className="block text-[12px] text-[#5e4b96]">[{mine.label}]</b>}
                <span className="line-clamp-2 whitespace-pre-line">{sentence}</span>
              </span>
              <button
                type="button"
                data-act="clear"
                aria-label={`소방대피/재난대비 칸에서 빼기: ${mine?.label ?? sentence}`}
                title="빼기"
                disabled={disabled}
                onClick={onClear}
                className={REMOVE}
              >
                −
              </button>
            </>
          ) : (
            <span className="flex-1 text-[13px] text-[#b1a89c]">비어 있어요</span>
          )}
        </div>
      </section>
      <section className="flex flex-col gap-1">
        <h3 className="m-0 text-[15px] font-bold text-ink">훈련 후보</h3>
        <ul className="m-0 flex list-none flex-col gap-2 p-0">
          {rest.map((d) => {
            const value = d.cell.value.trim();
            return (
              <li
                key={d.topic_id}
                draggable={!disabled && !!value}
                onDragStart={(event) =>
                  event.dataTransfer.setData("text/plain", DRILL_DRAG + d.cell.item_id)
                }
                className={`flex items-center gap-2.5 rounded-md border border-line bg-[#faf8f4] py-2.5 pl-2 pr-3 hover:bg-[#f5f1e9] ${disabled || !value ? "" : "cursor-grab active:cursor-grabbing"}`}
              >
                {GRIP}
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="text-[15px] font-bold leading-snug">{value || "(빈 후보)"}</span>
                  <span className="text-[13px] text-ink-soft">{d.label}</span>
                </span>
                <button
                  type="button"
                  data-act="copy"
                  data-candidate={d.cell.item_id}
                  aria-label={`소방대피/재난대비 칸에 넣기: ${d.label}`}
                  className={SMALL}
                  disabled={disabled || !value}
                  onClick={() => onCopy(d.cell.item_id)}
                >
                  +
                </button>
              </li>
            );
          })}
        </ul>
      </section>
    </section>
  );
}
