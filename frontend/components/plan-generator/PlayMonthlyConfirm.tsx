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

/**
 * 칸을 고르기 전 왼쪽 패널 — 얼마나 채웠는지 · 남은 빈칸(누르면 그 칸으로) · 고치는 법.
 * 월간(주제형 · 놀이형) · 주간이 같이 쓴다.
 */
export function PanelOverview({
  filled,
  total,
  rows,
}: {
  filled: number;
  total: number;
  rows: Parameters<typeof BlankRows>[0]["rows"];
}) {
  const done = total > 0 && filled >= total;
  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby="overview-progress" className="flex flex-col gap-2.5">
        <h2 id="overview-progress" className="m-0 text-[18px] font-bold leading-tight text-ink">
          {done ? "빈칸을 다 채웠어요" : `칸 ${total}개 중 ${filled}개를 채웠어요`}
        </h2>
        <div
          role="progressbar"
          aria-label="채운 칸"
          aria-valuemin={0}
          aria-valuemax={total}
          aria-valuenow={filled}
          className="h-2 overflow-hidden rounded-full bg-[#ece6dc]"
        >
          <div
            className={`h-full rounded-full transition-[width] duration-500 ease-out ${done ? "bg-[#3b7a4b]" : "bg-primary"}`}
            style={{ width: `${total ? (filled / total) * 100 : 0}%` }}
          />
        </div>
        <p className="m-0 text-[13px] text-ink-soft">
          {done
            ? "문서를 한 번 훑어보고 확정해 주세요."
            : "비운 칸이 있어도 확정할 수 있어요. 법정 안전교육은 꼭 확인해 주세요."}
        </p>
      </section>
      {rows.length > 0 && (
        <section aria-labelledby="overview-blanks" className="flex flex-col gap-2">
          <h3 id="overview-blanks" className="m-0 text-[15px] font-bold text-ink">
            남은 빈칸
          </h3>
          <BlankRows rows={rows} />
        </section>
      )}
      <section aria-labelledby="overview-howto" className="flex flex-col gap-2">
        <h3 id="overview-howto" className="m-0 text-[15px] font-bold text-ink">
          고치는 법
        </h3>
        <ol className="m-0 flex list-none flex-col gap-2 p-0 text-sm text-ink-soft">
          {[
            "오른쪽 문서에서 고칠 칸을 눌러요.",
            "여기에 열린 글상자에서 고치면 바로 저장돼요.",
            "잘못 고쳤으면 문서 위 되돌리기로 돌아가요.",
          ].map((text, i) => (
            <li key={i} className="flex gap-2.5">
              <span
                aria-hidden="true"
                className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[#efe8f7] text-[11px] font-bold text-primary-ink"
              >
                {i + 1}
              </span>
              {text}
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
