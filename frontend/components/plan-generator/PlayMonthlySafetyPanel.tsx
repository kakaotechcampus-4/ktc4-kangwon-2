"use client";
import { useState } from "react";
import type { PlayMonthlyPlan } from "@/lib/api/types";
import styles from "./PlayMonthlyStructure.module.css";

const KIND = { STATUTORY: "법정", SUPPLEMENTAL: "생활안전" } as const;

/** 안전교육 후보를 골라 주마다 둔다(버튼 · 선택만, 끌어놓기 없음). 같은 후보를 여러 주에 둘 수 있다. */
export default function PlayMonthlySafetyPanel({
  plan,
  onPlace,
  disabled,
}: {
  plan: PlayMonthlyPlan;
  onPlace: (weekId: string, candidateItemId: string | null) => void;
  disabled: boolean;
}) {
  // 고른 후보는 어느 계획의 것인지 같이 기억한다. 계획이 바뀌면 버려진다.
  const [pick, setPick] = useState<{ planId: number; id: string } | null>(null);
  const picked =
    pick?.planId === plan.id && plan.safety_candidates.some((c) => c.cell.item_id === pick.id)
      ? pick.id
      : null;
  const textOf = (id: string | null) =>
    plan.safety_candidates.find((c) => c.cell.item_id === id)?.cell.value ?? "";
  const label = (weekId: string) => plan.weeks.find((w) => w.week_id === weekId)?.label ?? weekId;
  return (
    <section className={styles.panel} aria-label="안전교육">
      <h2>안전교육 후보</h2>
      <ul>
        {plan.safety_candidates.map((c) => (
          <li key={c.cell.item_id}>
            <span className={styles.tag}>{KIND[c.kind]}</span>
            <button
              type="button"
              data-candidate={c.cell.item_id}
              aria-label={c.cell.value.trim() ? undefined : `${KIND[c.kind]} 빈 후보`}
              aria-pressed={picked === c.cell.item_id}
              disabled={disabled}
              onClick={() =>
                setPick(picked === c.cell.item_id ? null : { planId: plan.id, id: c.cell.item_id })
              }
            >
              {c.cell.value}
            </button>
          </li>
        ))}
      </ul>
      <h2>주별 배치</h2>
      <ul>
        {plan.safety_weeks.map((w) => (
          <li key={w.week_id} data-week={w.week_id}>
            <strong>{label(w.week_id)}</strong>
            <span>{w.candidate_item_id ? textOf(w.candidate_item_id) : "아직 안 뒀어요"}</span>
            <button
              type="button"
              data-act="place"
              aria-label={`${label(w.week_id)}에 두기${picked ? `: ${textOf(picked)}` : ""}`}
              disabled={disabled || picked === null}
              onClick={() => picked && onPlace(w.week_id, picked)}
            >
              {label(w.week_id)}에 두기
            </button>
            {w.candidate_item_id && (
              <button
                type="button"
                data-act="clear"
                aria-label={`${label(w.week_id)} 비우기: ${textOf(w.candidate_item_id)}`}
                disabled={disabled}
                onClick={() => onPlace(w.week_id, null)}
              >
                비우기
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
