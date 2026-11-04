"use client";
import { CARD, PUT } from "./PlayMonthlySafetyPanel";

/** Ⓜ3 AI 후보 — 소방대피 훈련 후보를 「소방대피/재난대비」 칸에 넣는다(09c). 쓴 글이 있어도 묻지 않고 바꾼다. */
export default function PlayMonthlyDrillPanel({
  candidates,
  onCopy,
  disabled,
}: {
  candidates: { topic_id: string; label: string; cell: { item_id: string; value: string } }[];
  onCopy: (itemId: string) => void;
  disabled: boolean;
}) {
  return (
    <section aria-label="소방대피 훈련" className="flex flex-col gap-2">
      <h2 className="m-0 text-[15px] font-bold">넣을 문구 고르기</h2>
      <ul className="m-0 flex list-none flex-col gap-2 p-0">
        {candidates.map((d) => {
          const id = d.cell.item_id;
          return (
            <li key={d.topic_id} className={`${CARD} border-[#e8e2d8]`}>
              <div className="min-w-0 flex-1 text-[14px]">
                <strong>{d.label}</strong>
                {d.cell.value && ` — ${d.cell.value}`}
              </div>
              <button
                type="button"
                data-act="copy"
                data-candidate={id}
                aria-label={`소방대피/재난대비 칸에 넣기: ${d.label}`}
                className={PUT}
                disabled={disabled || d.cell.value.trim() === ""}
                onClick={() => onCopy(id)}
              >
                넣기
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
