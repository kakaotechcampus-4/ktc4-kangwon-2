"use client";
import { useState } from "react";
import { isSaveConflict } from "@/lib/api/plans";
import PlayMonthlyConfirm from "./PlayMonthlyConfirm";

/**
 * [확정 취소] (계약 U). 페이지 안 확인 상자를 거쳐 `run` 을 부르고, 응답 계획안을 `onDone` 으로 넘긴다.
 * 409(그 사이 바뀜)는 `onConflict` 로 다시 불러온다. 하위 계획안은 그대로 남는다.
 */
export default function UnconfirmButton<T>({
  message,
  className,
  run,
  onDone,
  onConflict,
}: {
  message: string;
  className?: string;
  run: () => Promise<T>;
  onDone: (plan: T) => void;
  onConflict: () => void | Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function unconfirm() {
    setBusy(true);
    setError("");
    try {
      const plan = await run();
      setOpen(false);
      onDone(plan);
    } catch (e) {
      if (isSaveConflict(e)) await onConflict();
      else setError(e instanceof Error ? e.message : "확정을 풀지 못했어요.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button type="button" className={className} disabled={busy} onClick={() => setOpen(true)}>
        확정 취소
      </button>
      {open && (
        <PlayMonthlyConfirm
          message={message}
          yes={busy ? "푸는 중…" : "확정 풀기"}
          no="그대로 두기"
          disabled={busy}
          onYes={unconfirm}
          onNo={() => setOpen(false)}
        />
      )}
      {error && <p role="alert">{error}</p>}
    </>
  );
}
