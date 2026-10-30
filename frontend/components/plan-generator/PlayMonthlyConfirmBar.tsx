"use client";
import { useEffect, useRef, useState } from "react";
import workspace from "@/components/workspace/Workspace.module.css";
import { ApiError } from "@/lib/api/client";
import { confirmPlayMonthly } from "@/lib/api/playMonthly";
import { isSaveConflict } from "@/lib/api/plans";
import type { PlayMonthlyPlan } from "@/lib/api/types";

const SECTION = { together: "함께 하는 활동", free_play: "자유놀이" } as const;

/**
 * 서버 422 `fields`(위치 키)를 한 줄로 — 예: 「놀이 주제 · 이름 없는 함께 하는 활동 1개 · 누리과정 연결을 1~3개로 맞춰야 하는 행 1개」.
 * 모르는 키는 건너뛴다. 아무것도 못 읽으면 빈 문자열이다.
 */
export function confirmShortages(fields: string[]) {
  const names = { together: 0, free_play: 0 };
  const links = new Set<string>();
  const parts: string[] = [];
  for (const key of fields) {
    const [section, id, tail] = key.split(".");
    if (key === "theme") parts.push("놀이 주제");
    else if (key === "rationale") parts.push("선정 이유");
    else if (!id && section in SECTION)
      parts.push(SECTION[section as keyof typeof SECTION] + " 행");
    else if (id && section in SECTION && tail === undefined) names[section as keyof typeof names]++;
    else if (id && section in SECTION && tail === "content_ids") links.add(section + "." + id);
  }
  (Object.keys(names) as (keyof typeof names)[]).forEach(
    (s) => names[s] && parts.push(`이름 없는 ${SECTION[s]} ${names[s]}개`),
  );
  if (links.size) parts.push(`누리과정 연결을 1~3개로 맞춰야 하는 행 ${links.size}개`);
  return parts.join(" · ");
}
const serverFields = (error: ApiError): string[] => {
  const fields = (error.body as { error?: { fields?: unknown } } | null)?.error?.fields;
  return Array.isArray(fields) ? fields.filter((f): f is string => typeof f === "string") : [];
};

/**
 * 확정 버튼 (연간 놀이형 확정과 같은 흐름 · ADR-044 §2 · §4): 열린 입력창을 닫아 저장을 큐에 넣고 →
 * 새 변경을 막고 → 남은 저장이 끝나길 기다린 뒤 → 그 revision 으로 확정한다. 확정본이면 아무것도 그리지 않는다(배지는 화면에 있다).
 */
export default function PlayMonthlyConfirmBar({
  plan,
  whenIdle,
  freeze,
  unfreeze,
  onConfirmed,
  onConflict,
}: {
  plan: PlayMonthlyPlan;
  /** 남은 저장이 모두 끝나길 기다린다. `saved` 가 false 면 실패한 저장이 있다. */
  whenIdle: () => Promise<{ saved: boolean; revision: number; rejected?: boolean }>;
  /** 이 뒤로 새 변경을 받지 않는다. */
  freeze: () => void;
  unfreeze: () => void;
  onConfirmed: (plan: PlayMonthlyPlan) => void;
  /** 409 — 그 사이 계획안이 바뀌었다. 새로 불러오는 일은 화면이 한다. */
  onConflict: () => void | Promise<void>;
}) {
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState("");
  const lock = useRef(false);
  // 화면이 내려간 뒤에는 confirm 도 onConfirmed 도 setState 도 하지 않는다.
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  async function confirm() {
    if (lock.current) return;
    lock.current = true;
    setConfirming(true);
    setError("");
    let confirmed = false;
    try {
      (document.activeElement as HTMLElement | null)?.blur();
      freeze(); // blur 가 넣은 마지막 저장까지는 받았다.
      const idle = await whenIdle();
      if (!mounted.current) return;
      if (!idle.saved) {
        setError(
          idle.rejected
            ? "저장하지 못한 곳을 원래대로 되돌렸어요. 확인한 뒤 다시 확정해 주세요."
            : "저장하지 못했어요. 다시 저장한 뒤 확정해 주세요.",
        );
        return;
      }
      const done = await confirmPlayMonthly(plan.id, idle.revision);
      confirmed = true;
      if (mounted.current) onConfirmed(done);
    } catch (e) {
      if (!mounted.current) return;
      if (isSaveConflict(e)) {
        try {
          await onConflict();
        } catch {
          setError("최신 내용을 불러오지 못했어요. 새로고침해 주세요.");
        }
        return;
      }
      const lacking =
        e instanceof ApiError && e.status === 422 ? confirmShortages(serverFields(e)) : "";
      setError(
        lacking
          ? "확정하려면 채워야 할 곳이 있어요: " + lacking
          : e instanceof Error
            ? e.message
            : "확정하지 못했어요.",
      );
    } finally {
      lock.current = false;
      // 확정되면 큐를 다시 열지 않는다 — 열린 입력창의 마지막 저장이 확정본을 덮으려 하지 못하게.
      if (!confirmed) unfreeze();
      if (mounted.current) setConfirming(false);
    }
  }

  if (plan.status === "CONFIRMED") return null;
  return (
    <div>
      <button type="button" className={workspace.primary} disabled={confirming} onClick={confirm}>
        {confirming ? "확정하는 중…" : "확정하기"}
      </button>{" "}
      <span className={workspace.muted}>확정하면 고칠 수 없어요</span>
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
