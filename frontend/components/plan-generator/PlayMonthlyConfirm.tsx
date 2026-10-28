"use client";
import { useEffect } from "react";
import styles from "./PlayMonthlyStructure.module.css";

/** 페이지 안 확인 상자(window.confirm 대신). 닫기는 부른 쪽이 정한다. */
export default function PlayMonthlyConfirm({
  message,
  yes,
  no = "아니요",
  disabled = false,
  onYes,
  onNo,
}: {
  message: string;
  yes: string;
  no?: string;
  disabled?: boolean;
  onYes: () => void;
  onNo: () => void;
}) {
  // 닫히면 포커스를 상자를 연 버튼으로 돌린다.
  useEffect(() => {
    const opener = globalThis.document?.activeElement as HTMLElement | null | undefined;
    return () => opener?.focus?.();
  }, []);
  // 포커스를 가두지 않는 페이지 안 비모달 확인이라 dialog 가 아니라 group 이다.
  return (
    <div
      role="group"
      aria-label={message}
      className={styles.confirm}
      onKeyDown={(e) => e.key === "Escape" && onNo()}
    >
      <p>{message}</p>
      <button type="button" data-act="no" ref={(el) => el?.focus()} onClick={onNo}>
        {no}
      </button>
      <button type="button" data-act="yes" disabled={disabled} onClick={onYes}>
        {yes}
      </button>
    </div>
  );
}
