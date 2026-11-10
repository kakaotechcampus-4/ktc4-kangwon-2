"use client";

import { useEffect, useState } from "react";
import { getChildren } from "@/lib/api/children";
import { getObservations } from "@/lib/api/observations";
import { getWeeklyPlan, listWeeklyPlans } from "@/lib/api/weekly";
import { dayPlan, planOfDay, withoutNames, type DayPlan } from "@/lib/workspace/journal-day";

/** 칠판에 띄울 그날 관찰 한 줄. 이름은 이미 뺐다. */
export interface DayObservation {
  id: number;
  context: string;
  text: string;
  /** 못 가린 낱말 — 외자 부르는 이름. 화면이 노랗게 짚는다. */
  suspects: string[];
}

interface Extras {
  key: string;
  plan: DayPlan | null;
  observations: DayObservation[];
}

/** 그날이 든 달과 앞 달의 주간계획안. 주는 한 달에 속하지만 그 주가 앞 달에서 시작할 수 있다. */
function nearMonths(date: string) {
  const month = Number(date.slice(5, 7));
  return new Set([month, month === 1 ? 12 : month - 1]);
}

/**
 * 일과 기록 화면 옆에 띄울 것 — 그날 주간계획안 칸, 그날 관찰 (ADR-086 · ADR-024 덧붙임).
 *
 * **둘 다 거들 뿐이다.** 못 받아 와도 일과를 적는 일을 막지 않는다 — 없으면 안 띄운다.
 * 계획안은 하민님 계약(`/api/plans/weekly`)을 읽기만 한다. 관찰 글은 받자마자 반 아이 이름을
 * 「○○」로 뺀 글로만 들고 있는다 — 넣으면 교사가 고친다.
 */
export function useDayExtras(classId: number | null, date: string) {
  const key = classId === null || !date ? "" : `${classId}|${date}`;
  const [extras, setExtras] = useState<Extras | null>(null);

  useEffect(() => {
    if (classId === null || !date) return;
    let live = true;
    const at = `${classId}|${date}`;
    const months = nearMonths(date);
    const plan = listWeeklyPlans(classId)
      .then(({ items }) =>
        Promise.all(
          items
            .filter((p) => months.has(Number(p.target_month.slice(5, 7))))
            .map((p) => getWeeklyPlan(p.id)),
        ),
      )
      .then((plans) => {
        const found = planOfDay(plans, date);
        return found ? dayPlan(found, date) : null;
      })
      .catch(() => null);
    const observations = Promise.all([
      getObservations({ class_id: classId, from: date, to: date }),
      getChildren(classId),
    ])
      .then(([{ items }, children]) => {
        const names = children.items.map((c) => c.name);
        return items
          .filter((o) => o.context?.trim())
          .map((o) => ({ id: o.id, context: o.context ?? "", ...withoutNames(o.fact, names) }));
      })
      .catch(() => [] as DayObservation[]);
    void Promise.all([plan, observations]).then(
      ([plan, observations]) => live && setExtras({ key: at, plan, observations }),
    );
    return () => {
      live = false;
    };
  }, [classId, date]);

  const current = extras?.key === key ? extras : null;
  return { plan: current?.plan ?? null, observations: current?.observations ?? [] };
}
