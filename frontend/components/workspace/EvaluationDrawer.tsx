"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";
import styles from "./Evaluation.module.css";

/**
 * 오른쪽에서 나오는 서랍(시안 ④). 열 때만 그려 넣는다 — 닫혀 있는 동안 체크 상자가 DOM 에 남지 않는다.
 * 네이티브 `<dialog>` 라서 포커스를 가두고 Esc 로 닫히며, 닫으면 눌렀던 단추로 포커스가 돌아간다(RegionSheet 와 같다).
 * ×와 뒤 배경도 `close()` 를 거쳐 닫는다 — 부모가 곧장 지워 버리면 포커스가 돌아갈 곳을 잃는다.
 */
export default function EvaluationDrawer({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);

  return (
    <dialog
      ref={ref}
      className={styles.drawer}
      aria-labelledby={titleId}
      onClose={onClose}
      onClick={(e) => e.target === ref.current && ref.current.close()}
    >
      <div className={styles.drawerHead}>
        <h2 id={titleId}>{title}</h2>
        <button
          type="button"
          className={styles.drawerClose}
          aria-label="닫기"
          onClick={() => ref.current?.close()}
        >
          ×
        </button>
      </div>
      <div className={styles.drawerBody}>{children}</div>
    </dialog>
  );
}
