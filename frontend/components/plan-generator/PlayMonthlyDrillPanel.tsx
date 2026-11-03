"use client";
import { useState } from "react";
import PlayMonthlyConfirm from "./PlayMonthlyConfirm";
import { CARD, PUT } from "./PlayMonthlySafetyPanel";

/** Ⓜ3 AI 후보 — 소방대피 훈련 후보를 「소방대피/재난대비」 칸에 넣는다(09c). 쓴 글이 있으면 덮기 전에 묻는다. */
export default function PlayMonthlyDrillPanel({
  candidates,
  current,
  onCopy,
  disabled,
}: {
  candidates: { topic_id: string; label: string; cell: { item_id: string; value: string } }[];
  current: string;
  onCopy: (itemId: string) => void;
  disabled: boolean;
}) {
  const [asking, setAsking] = useState<string | null>(null);
  if (disabled && asking) setAsking(null);
  const copy = (id: string) => {
    if (disabled) return;
    setAsking(null);
    onCopy(id);
  };
  return (
    <section aria-label="소방대피 훈련" className="flex flex-col gap-2">
      <h2 className="m-0 flex items-baseline justify-between text-[15px] font-bold">
        넣을 문구 고르기
        <span className="text-[13px] font-normal text-[#5c5243]">넣은 뒤 고칠 수 있어요</span>
      </h2>
      <ul className="m-0 flex list-none flex-col gap-2 p-0">
        {candidates.map((d) => {
          const id = d.cell.item_id;
          const empty = d.cell.value.trim() === "";
          return (
            <li key={d.topic_id} className="flex flex-col gap-2">
              <div className={`${CARD} border-[#e8e2d8]`}>
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
                  disabled={disabled || empty}
                  onClick={() => (current.trim() ? setAsking(id) : copy(id))}
                >
                  넣기
                </button>
              </div>
              {asking === id && (
                <PlayMonthlyConfirm
                  message="지금 쓴 글을 이 후보로 바꿀까요?"
                  yes="바꾸기"
                  disabled={disabled}
                  onYes={() => copy(id)}
                  onNo={() => setAsking(null)}
                />
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
