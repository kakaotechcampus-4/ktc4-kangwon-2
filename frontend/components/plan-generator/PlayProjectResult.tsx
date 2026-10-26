"use client";

import { useState } from "react";
import type { PlayProjectAnnualPlan } from "@/lib/api/types";
import workspace from "@/components/workspace/Workspace.module.css";
import tabs from "./GenerationFlow.module.css";
import styles from "./PlayProjectResult.module.css";

// 놀이 프로젝트형 결과 — 확정 · 수정은 아직 없는 읽기 전용 화면이다(ADR-043). 고르기 · 미리보기는 다음 PR.
export default function PlayProjectResult({ plan }: { plan: PlayProjectAnnualPlan }) {
  const [selected, setSelected] = useState(0);
  const period = plan.periods[selected];
  const tabId = (index: number) => `play-project-tab-${plan.id}-${index}`;
  const panelId = `play-project-panel-${plan.id}`;
  return (
    <main className={workspace.page}>
      <div className={styles.meta}>
        <span className={workspace.badge}>{plan.status === "DRAFT" ? "초안" : "확정"}</span>
        <span>{plan.school_year}학년도</span>
      </div>
      <div className={workspace.notice}>
        <p>놀이 프로젝트형은 아직 확정 · 내려받기를 할 수 없어요.</p>
        <p>이 반은 월간 · 주간계획안을 만들 수 없어요.</p>
      </div>
      <div
        role="tablist"
        aria-label="놀이 프로젝트 기간"
        className={`${tabs.tabs} ${tabs.wrappingTabs}`}
      >
        {plan.periods.map((item, index) => (
          <button
            key={item.period_key}
            id={tabId(index)}
            type="button"
            role="tab"
            aria-selected={selected === index}
            aria-controls={panelId}
            className={selected === index ? tabs.activeTab : undefined}
            onClick={() => setSelected(index)}
          >
            {item.label}
          </button>
        ))}
      </div>
      <section
        id={panelId}
        role="tabpanel"
        aria-labelledby={tabId(selected)}
        tabIndex={0}
        className={styles.panel}
      >
        <div className={workspace.stack}>
          {period.candidates.map((candidate, index) => (
            <article className={workspace.card} key={candidate.row_key}>
              <p className={workspace.eyebrow}>후보 {index + 1}</p>
              <h2>{candidate.play_name.value}</h2>
              <dl className={styles.fields}>
                <div>
                  <dt>지원매체</dt>
                  <dd>{candidate.materials.value}</dd>
                </div>
                <div>
                  <dt>내용 및 지원 방향 예상하기</dt>
                  <dd>{candidate.support_direction.value}</dd>
                </div>
                <div>
                  <dt>놀이를 통한 배움</dt>
                  <dd>{candidate.learning.value}</dd>
                </div>
              </dl>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
