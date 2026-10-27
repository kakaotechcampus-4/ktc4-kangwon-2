"use client";

import type { ReactNode } from "react";
import type { SelfCheckIndicator } from "@/lib/api/evaluation";
import { ws } from "./WorkspaceUI";
import styles from "./Evaluation.module.css";

/** 서버 순서를 지키며 영역별로 묶는다. */
function byArea(items: SelfCheckIndicator[]) {
  const areas = new Map<string, SelfCheckIndicator[]>();
  for (const item of items) areas.set(item.area, [...(areas.get(item.area) ?? []), item]);
  return [...areas.entries()];
}

function AreaGroup({
  area,
  items,
  initiallyOpen,
  onCheck,
}: {
  area: string;
  items: SelfCheckIndicator[];
  initiallyOpen: Set<string>;
  onCheck: (element: string, checked: boolean) => void;
}) {
  const checked = items.reduce((sum, item) => sum + item.progress.checked, 0);
  const total = items.reduce((sum, item) => sum + item.progress.total, 0);
  return (
    <section className={styles.area} aria-label={area}>
      <div className={styles.areaHead}>
        <h3>
          영역 {items[0].indicator.split("-")[0]} · {area}
        </h3>
        <span className={styles.bar} aria-hidden="true">
          <span style={{ width: `${total ? (checked / total) * 100 : 0}%` }} />
        </span>
        <span className={styles.areaCount}>
          {checked} / {total}
        </span>
      </div>
      {items.map((item) => (
        // 펼침은 불러올 때 한 번만 정한다. 체크하다가 저절로 접히지 않게 한다.
        <details
          key={item.indicator}
          className={styles.indicator}
          open={initiallyOpen.has(item.indicator)}
        >
          <summary>
            <span className={styles.indicatorNumber}>{item.indicator}</span>
            <span className={styles.indicatorTitle}>{item.title}</span>
            <span className={`${styles.progressChip} ${item.complete ? styles.progressDone : ""}`}>
              {item.complete ? "완료 " : ""}
              {item.progress.checked}/{item.progress.total}
            </span>
          </summary>
          <fieldset className={styles.elements} aria-label={`${item.indicator} ${item.title}`}>
            {item.elements.map((element) => (
              <label key={element.element} className={styles.element}>
                <input
                  type="checkbox"
                  checked={element.checked}
                  onChange={(e) => onCheck(element.element, e.target.checked)}
                />
                <span>
                  {element.element} · {element.text}
                </span>
              </label>
            ))}
          </fieldset>
        </details>
      ))}
    </section>
  );
}

/** 자체평가 탭 — 체크는 선생님이 직접 확인한 것이지 증빙이 아니다(ADR-022). */
export default function EvaluationSelfCheck({
  items,
  savedAt,
  initiallyOpen,
  onCheck,
  children,
}: {
  items: SelfCheckIndicator[];
  savedAt: Date | null;
  initiallyOpen: Set<string>;
  onCheck: (element: string, checked: boolean) => void;
  children?: ReactNode;
}) {
  return (
    <div className={ws.stack}>
      <div className={styles.titleRow}>
        <div>
          <h2 className={styles.sectionTitle}>자체평가 · 원에서 스스로 확인하는 평가항목</h2>
          <p className={ws.hint}>
            해당하는 평가요소를 누르면 바로 저장돼요. 선생님이 직접 확인한 항목이고, 공식 평가
            통과를 뜻하지 않아요.
          </p>
        </div>
        <p role="status" className={styles.savedState}>
          {savedAt &&
            `✓ 저장됨 · ${savedAt.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })}`}
        </p>
      </div>
      {byArea(items).map(([area, list]) => (
        <AreaGroup
          key={area}
          area={area}
          items={list}
          initiallyOpen={initiallyOpen}
          onCheck={onCheck}
        />
      ))}
      <p className={styles.footnote}>
        영역 1 · 2 · 3(평가항목 6개)은 쌤플 문서로 확인할 수 없어 여기서 다루지 않아요. 자체평가 때
        위원회가 교실을 보며 함께 확인해요.
      </p>
      {children}
    </div>
  );
}
