"use client";
import { useEffect, useRef, type ReactNode } from "react";
import styles from "./PlayMonthlyStructure.module.css";

/** 페이지 안 확인 상자(window.confirm 대신). 닫기는 부른 쪽이 정한다. `yes` 가 없으면 단추 하나(알림), `shake` 면 열릴 때 살짝 흔든다. */
export default function PlayMonthlyConfirm({
  message,
  yes,
  no = "아니요",
  disabled = false,
  shake = false,
  onYes,
  onNo,
  children,
}: {
  message: string;
  /** 글 아래 · 단추 위에 덧붙일 것(남은 빈칸 목록 등). */
  children?: ReactNode;
  yes?: string;
  no?: string;
  disabled?: boolean;
  shake?: boolean;
  onYes?: () => void;
  onNo: () => void;
}) {
  // 열릴 때 한 번만 「아니요」로 포커스를 옮기고, 닫히면 상자를 연 버튼으로 돌린다. 다시 그려도 포커스를 가져가지 않는다.
  const noButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const opener = globalThis.document?.activeElement as HTMLElement | null | undefined;
    noButton.current?.focus();
    return () => opener?.focus?.();
  }, []);
  // 포커스를 가두지 않는 페이지 안 비모달 확인이라 dialog 가 아니라 group 이다.
  return (
    <div
      role="group"
      aria-label={message}
      className={`${styles.confirm} ${shake ? styles.shake : ""}`}
      onKeyDown={(e) => e.key === "Escape" && onNo()}
    >
      <p>{message}</p>
      {children && <div className="basis-full">{children}</div>}
      <button type="button" data-act="no" ref={noButton} onClick={onNo}>
        {no}
      </button>
      {yes && (
        <button type="button" data-act="yes" disabled={disabled} onClick={onYes}>
          {yes}
        </button>
      )}
    </div>
  );
}

/** 확정 확인 상자 안 「남은 빈칸」 목록. 줄마다 빈칸 수, 누르면 그 줄 첫 빈칸으로 간다. 법정 안전교육 줄은 맨 위 · 붉은 글. */
export function BlankRows({
  rows,
}: {
  rows: { key: string; label: string; count: number; safety?: boolean; onJump: () => void }[];
}) {
  if (!rows.length) return null;
  const sorted = [...rows].sort((a, b) => Number(!!b.safety) - Number(!!a.safety));
  return (
    <ul
      className="m-0 flex list-none flex-col gap-1 rounded-md bg-[#f7f4ee] p-2"
      aria-label="남은 빈칸"
    >
      {sorted.map((r) => (
        <li key={r.key}>
          <button
            type="button"
            onClick={r.onJump}
            className={`flex min-h-[36px] w-full items-center justify-between gap-3 rounded px-2 text-left text-sm hover:bg-white ${r.safety ? "font-bold text-[#a2492f]" : "text-[#2b2826]"}`}
          >
            <span>
              {r.label}
              {r.safety && " · 법정 안전교육"}
            </span>
            <span className="shrink-0">빈칸 {r.count}개 →</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
