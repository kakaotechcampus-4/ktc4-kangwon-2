"use client";

import { useState } from "react";
import type { PlayProjectAnnualPlan } from "@/lib/api/types";
import workspace from "@/components/workspace/Workspace.module.css";
import tabs from "./GenerationFlow.module.css";
import styles from "./PlayProjectResult.module.css";

const MAX_PICKS = 5;
const fields = [
  { key: "play_name", label: "놀이명", heading: "놀이명" },
  { key: "materials", label: "지원매체", heading: "지원매체" },
  { key: "support_direction", label: "지원 방향", heading: "내용 및 지원 방향 예상하기" },
  { key: "learning", label: "놀이를 통한 배움", heading: "놀이를 통한 배움" },
] as const;
type PlayField = (typeof fields)[number]["key"];
type PreviewRow = {
  period: PlayProjectAnnualPlan["periods"][number];
  candidate: PlayProjectAnnualPlan["periods"][number]["candidates"][number] | null;
  rowSpan: number | undefined;
};

export function togglePlayPick(picks: string[], rowKey: string) {
  return picks.includes(rowKey)
    ? picks.filter((key) => key !== rowKey)
    : picks.length < MAX_PICKS
      ? [...picks, rowKey]
      : picks;
}

export function buildPlayProjectPreviewRows(
  plan: PlayProjectAnnualPlan,
  picks: Record<string, string[]>,
) {
  return plan.periods.flatMap<PreviewRow>((period) => {
    const selected = (picks[period.period_key] ?? []).map((key) =>
      period.candidates.find((candidate) => candidate.row_key === key)!,
    );
    return selected.length
      ? selected.map<PreviewRow>((candidate, index) => ({
          period,
          candidate,
          rowSpan: index === 0 ? selected.length : undefined,
        }))
      : [{ period, candidate: null, rowSpan: 1 }];
  });
}

// 화면 선택만 제공한다. 저장 · 수정 · 순서 바꾸기 · 쪽 넘김은 아직 지원하지 않는다.
export default function PlayProjectResult({ plan }: { plan: PlayProjectAnnualPlan }) {
  const [activePeriod, setActivePeriod] = useState(0);
  const [step, setStep] = useState(0);
  const [picks, setPicks] = useState<Record<string, string[]>>({});
  const [selectedCell, setSelectedCell] = useState<{
    periodKey: string;
    rowKey: string;
    field: PlayField;
  } | null>(null);
  const period = plan.periods[activePeriod];
  const periodPicks = picks[period.period_key] ?? [];
  const pickedCandidates = periodPicks.map((key) =>
    period.candidates.find((candidate) => candidate.row_key === key)!,
  );
  const selectedPeriod =
    selectedCell && plan.periods.find((p) => p.period_key === selectedCell.periodKey);
  const selectedCandidate = selectedPeriod?.candidates.find(
    (candidate) => candidate.row_key === selectedCell?.rowKey,
  );
  const selectedField = selectedCell && fields.find((field) => field.key === selectedCell.field);

  function toggleCandidate(rowKey: string) {
    if (
      periodPicks.includes(rowKey) &&
      selectedCell?.periodKey === period.period_key &&
      selectedCell.rowKey === rowKey
    )
      setSelectedCell(null);
    setPicks((current) => ({
      ...current,
      [period.period_key]: togglePlayPick(current[period.period_key] ?? [], rowKey),
    }));
  }

  function selectCell(periodIndex: number, rowKey: string, field: PlayField) {
    setActivePeriod(periodIndex);
    setSelectedCell({ periodKey: plan.periods[periodIndex].period_key, rowKey, field });
  }

  function renderPicking() {
    return (
      <div className={workspace.stack}>
        {period.candidates.map((candidate, index) => {
          const checked = periodPicks.includes(candidate.row_key);
          return (
            <article className={workspace.card} key={candidate.row_key}>
              <div className={`${workspace.between} ${styles.cardHeading}`}>
                <div>
                  <p className={workspace.eyebrow}>후보 {index + 1}</p>
                  <h2>{candidate.play_name.value}</h2>
                </div>
                <label className={`${workspace.check} ${styles.pick}`}>
                  <input
                    type="checkbox"
                    aria-label={`후보 ${index + 1} 고르기`}
                    checked={checked}
                    disabled={!checked && periodPicks.length >= MAX_PICKS}
                    onChange={() => toggleCandidate(candidate.row_key)}
                  />
                  고르기
                </label>
              </div>
              <dl className={styles.fields}>
                {fields.slice(1).map((field) => (
                  <div key={field.key}>
                    <dt>{field.heading}</dt>
                    <dd>{candidate[field.key].value}</dd>
                  </div>
                ))}
              </dl>
            </article>
          );
        })}
        {periodPicks.length === MAX_PICKS && (
          <p role="status" className={`${workspace.muted} ${styles.limitMessage}`}>
            5개를 모두 골랐어요. 바꾸려면 하나를 빼 주세요.
          </p>
        )}
      </div>
    );
  }

  function renderArrangement() {
    const rows = buildPlayProjectPreviewRows(plan, picks);
    return (
      <div className={styles.arrangementGrid}>
        <section
          className={`${workspace.card} ${styles.leftPanel}`}
          aria-label="고른 놀이와 선택한 칸"
        >
          <h2>고른 놀이 {periodPicks.length}</h2>
          <div className={workspace.stack}>
            {pickedCandidates.map((candidate) => (
              <button
                type="button"
                key={candidate.row_key}
                aria-pressed={
                  selectedCell?.periodKey === period.period_key &&
                  selectedCell.rowKey === candidate.row_key
                }
                className={`${workspace.item} ${styles.playButton}`}
                onClick={() => selectCell(activePeriod, candidate.row_key, "play_name")}
              >
                {candidate.play_name.value}
              </button>
            ))}
          </div>
          {selectedCandidate && selectedCell && selectedField ? (
            <div className={`${workspace.field} ${styles.viewer}`}>
              <div className={workspace.pills} aria-label="미리 볼 칸">
                {fields.map((field) => (
                  <button
                    type="button"
                    key={field.key}
                    aria-pressed={selectedCell.field === field.key}
                    className={selectedCell.field === field.key ? workspace.selected : undefined}
                    onClick={() => setSelectedCell({ ...selectedCell, field: field.key })}
                  >
                    {field.label}
                  </button>
                ))}
              </div>
              <label htmlFor="play-project-selected-cell">{selectedField.label}</label>
              <textarea
                id="play-project-selected-cell"
                readOnly
                value={selectedCandidate[selectedField.key].value}
              />
              <p>아직 수정 기능은 제공하지 않아요.</p>
            </div>
          ) : (
            <p className={`${workspace.muted} ${styles.hint}`}>
              오른쪽 문서의 칸을 누르면 여기에서 볼 수 있어요.
            </p>
          )}
        </section>
        <section
          className={`${workspace.card} ${styles.sheet}`}
          aria-label="연간놀이계획안 미리보기"
        >
          <h2>{plan.school_year} 연간놀이계획안</h2>
          <div className={styles.previewWrap}>
            <table className={styles.preview}>
              <thead>
                <tr>
                  <th scope="col">시기</th>
                  {fields.map((field) => (
                    <th scope="col" key={field.key}>
                      {field.heading}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const candidate = row.candidate;
                  return (
                    <tr key={`${row.period.period_key}-${candidate?.row_key ?? "empty"}`}>
                      {row.rowSpan ? (
                        <th scope="rowgroup" rowSpan={row.rowSpan}>
                          {row.period.label}
                        </th>
                      ) : null}
                      {candidate ? (
                        fields.map((field) => {
                          const selected =
                            selectedCell?.periodKey === row.period.period_key &&
                            selectedCell?.rowKey === candidate.row_key &&
                            selectedCell?.field === field.key;
                          return (
                            <td key={field.key}>
                              <button
                                type="button"
                                aria-label={`${candidate.play_name.value} ${field.heading}`}
                                aria-pressed={selected}
                                className={`${styles.cellButton} ${selected ? styles.selectedCell : ""}`}
                                onClick={() =>
                                  selectCell(
                                    plan.periods.indexOf(row.period),
                                    candidate.row_key,
                                    field.key,
                                  )
                                }
                              >
                                {candidate[field.key].value}
                              </button>
                            </td>
                          );
                        })
                      ) : (
                        <td colSpan={4} className={styles.empty}>
                          아직 고른 놀이가 없어요
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    );
  }

  const tabId = (index: number) => `play-project-tab-${plan.id}-${index}`;
  const panelId = `play-project-panel-${plan.id}`;
  return (
    <main className={workspace.page}>
      <div className={styles.meta}>
        <span className={workspace.badge}>{plan.status === "DRAFT" ? "초안" : "확정"}</span>
        <span>{plan.school_year}학년도</span>
      </div>
      <ol className={tabs.steps} aria-label="놀이 프로젝트 결과 단계">
        {["① 놀이 고르기", "② 배치하고 다듬기"].map((label, index) => (
          <li key={label} className={step === index ? tabs.reached : undefined}>
            <span>0{index + 1}</span>
            <button
              type="button"
              className={styles.stepButton}
              aria-current={step === index ? "step" : undefined}
              onClick={() => setStep(index)}
            >
              {label}
            </button>
          </li>
        ))}
      </ol>
      <div className={workspace.notice}>
        <p>놀이 프로젝트형은 아직 확정 · 내려받기를 할 수 없어요.</p>
        <p>이 반은 월간 · 주간계획안을 만들 수 없어요.</p>
        <p>고른 놀이는 아직 저장되지 않아요. 새로고침하면 처음부터 다시 골라야 해요.</p>
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
            aria-selected={activePeriod === index}
            aria-controls={panelId}
            className={activePeriod === index ? tabs.activeTab : undefined}
            onClick={() => {
              setActivePeriod(index);
              if (selectedCell && selectedCell.periodKey !== item.period_key) setSelectedCell(null);
            }}
          >
            {item.label} · {picks[item.period_key]?.length ?? 0}/{MAX_PICKS}
          </button>
        ))}
      </div>
      <section
        id={panelId}
        role="tabpanel"
        aria-labelledby={tabId(activePeriod)}
        tabIndex={0}
        className={styles.panel}
      >
        {step === 0 ? renderPicking() : renderArrangement()}
      </section>
    </main>
  );
}
