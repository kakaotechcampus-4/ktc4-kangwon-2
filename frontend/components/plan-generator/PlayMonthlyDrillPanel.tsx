"use client";
import { useState } from "react";
import type { PlayMonthlyPlan } from "@/lib/api/types";
import PlayMonthlyConfirm from "./PlayMonthlyConfirm";
import styles from "./PlayMonthlyStructure.module.css";

/** 소방대피 훈련 후보를 「소방대피/재난대비」 칸에 복사한다. 쓴 글이 있으면 덮기 전에 묻는다. */
export default function PlayMonthlyDrillPanel({
  plan,
  onCopy,
  disabled,
}: {
  plan: PlayMonthlyPlan;
  onCopy: (itemId: string) => void;
  disabled: boolean;
}) {
  const [asking, setAsking] = useState<string | null>(null);
  const current =
    plan.teacher_inputs.find((t) => t.key === "fire_disaster_drill")?.cell.value ?? "";
  if (disabled && asking) setAsking(null);
  const copy = (id: string) => {
    if (disabled) return;
    setAsking(null);
    onCopy(id);
  };
  return (
    <section className={styles.panel} aria-label="소방대피 훈련">
      <h2>소방대피 훈련 후보</h2>
      <ul>
        {plan.drill_candidates.map((d) => {
          const id = d.cell.item_id;
          const empty = d.cell.value.trim() === "";
          return (
            <li key={d.topic_id}>
              <strong>{d.label}</strong>
              <span>{d.cell.value}</span>
              <button
                type="button"
                data-act="copy"
                data-candidate={id}
                aria-label={`소방대피/재난대비 칸에 넣기: ${d.label}`}
                disabled={disabled || empty}
                onClick={() => (current.trim() ? setAsking(id) : copy(id))}
              >
                소방대피/재난대비 칸에 넣기
              </button>
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
