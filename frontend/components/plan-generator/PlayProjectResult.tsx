"use client";

import { useEffect, useRef, useState } from "react";
import type { PlayProjectAnnualPlan } from "@/lib/api/types";
import workspace from "@/components/workspace/Workspace.module.css";
import tabs from "./GenerationFlow.module.css";
import styles from "./PlayProjectResult.module.css";
import PlayProjectSheet from "./PlayProjectSheet";
import { fields, type PlayField, type SheetZoom } from "./playProjectPagination";
export { buildPlayProjectPreviewRows } from "./playProjectPagination";

const MAX_PICKS = 5;

export function togglePlayPick(picks: string[], rowKey: string) {
  return picks.includes(rowKey)
    ? picks.filter((key) => key !== rowKey)
    : picks.length < MAX_PICKS
      ? [...picks, rowKey]
      : picks;
}

export function movePlayPick(picks: string[], rowKey: string, delta: -1 | 1): string[] {
  const index = picks.indexOf(rowKey);
  const next = index + delta;
  if (index < 0 || next < 0 || next >= picks.length) return picks;
  const moved = [...picks];
  [moved[index], moved[next]] = [moved[next], moved[index]];
  return moved;
}

export function floatingNextBottom(rect: { top: number; height: number }): number | null {
  return rect.top > 0 ? rect.height + 12 : null;
}

export function nextPlayProjectPeriod(
  plan: PlayProjectAnnualPlan,
  picks: Record<string, string[]>,
  activePeriod: number,
) {
  for (let offset = 1; offset < plan.periods.length; offset++) {
    const index = (activePeriod + offset) % plan.periods.length;
    if ((picks[plan.periods[index].period_key]?.length ?? 0) < MAX_PICKS) return index;
  }
  return null;
}

// 고른 놀이와 보기 설정은 화면 상태에만 둔다.
export default function PlayProjectResult({ plan }: { plan: PlayProjectAnnualPlan }) {
  const [activePeriod, setActivePeriod] = useState(0);
  const [step, setStep] = useState(0);
  const [picks, setPicks] = useState<Record<string, string[]>>({});
  const [selectedCell, setSelectedCell] = useState<{
    periodKey: string;
    rowKey: string;
    field: PlayField;
  } | null>(null);
  const [zoom, setZoom] = useState<SheetZoom>({ mode: "fit", percent: 100 });
  const [scrollPeriod, setScrollPeriod] = useState<{
    periodKey: string;
    request: number;
    cell?: { rowKey: string; field: PlayField };
  } | null>(null);
  const tabListRef = useRef<HTMLDivElement>(null);
  const floatingRef = useRef<HTMLButtonElement>(null);
  const period = plan.periods[activePeriod];
  const periodPicks = picks[period.period_key] ?? [];
  const nextPeriod = nextPlayProjectPeriod(plan, picks, activePeriod);
  const showFloating = step === 0 && periodPicks.length === MAX_PICKS;
  const pickedCandidates = periodPicks.map((key) =>
    period.candidates.find((candidate) => candidate.row_key === key)!,
  );
  const selectedPeriod =
    selectedCell && plan.periods.find((p) => p.period_key === selectedCell.periodKey);
  const selectedCandidate = selectedPeriod?.candidates.find(
    (candidate) => candidate.row_key === selectedCell?.rowKey,
  );
  const selectedField = selectedCell && fields.find((field) => field.key === selectedCell.field);

  useEffect(() => {
    if (!showFloating || typeof ResizeObserver === "undefined") return;
    const nav = document.querySelector('aside[aria-label="주 메뉴"]');
    const button = floatingRef.current;
    if (!nav || !button) return;
    const update = () => {
      const bottom = floatingNextBottom(nav.getBoundingClientRect());
      button.style.bottom = bottom === null ? "" : `${bottom}px`;
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(nav);
    return () => observer.disconnect();
  }, [showFloating]);

  function toggleCandidate(rowKey: string) {
    if (periodPicks.includes(rowKey)) {
      if (selectedCell?.periodKey === period.period_key && selectedCell.rowKey === rowKey)
        setSelectedCell(null);
      setScrollPeriod((current) =>
        current?.periodKey === period.period_key && current.cell?.rowKey === rowKey
          ? null
          : current,
      );
    }
    setPicks((current) => ({
      ...current,
      [period.period_key]: togglePlayPick(current[period.period_key] ?? [], rowKey),
    }));
  }

  function selectCell(periodIndex: number, rowKey: string, field: PlayField) {
    setActivePeriod(periodIndex);
    const periodKey = plan.periods[periodIndex].period_key;
    setSelectedCell({ periodKey, rowKey, field });
    if (window.matchMedia("(min-width: 1024px)").matches)
      setScrollPeriod((current) => ({
        periodKey,
        request: (current?.request ?? 0) + 1,
        cell: { rowKey, field },
      }));
  }

  function moveCandidate(rowKey: string, delta: -1 | 1) {
    setPicks((current) => ({
      ...current,
      [period.period_key]: movePlayPick(current[period.period_key] ?? [], rowKey, delta),
    }));
    requestAnimationFrame(() => {
      const arrow = document.getElementById(
        `${pickId(rowKey)}-${delta}`,
      ) as HTMLButtonElement | null;
      (arrow?.disabled ? document.getElementById(pickId(rowKey)) : arrow)?.focus();
    });
  }

  function removeCandidate(rowKey: string) {
    toggleCandidate(rowKey);
    requestAnimationFrame(() => document.getElementById(pickedHeadingId)?.focus());
  }

  function addCandidate(rowKey: string) {
    toggleCandidate(rowKey);
    requestAnimationFrame(() => document.getElementById(pickId(rowKey))?.focus());
  }

  function goToStep(index: number) {
    if (index === step) return;
    setScrollPeriod(null);
    setStep(index);
    requestAnimationFrame(() => window.scrollTo({ top: 0 }));
  }

  function goToPeriod(index: number) {
    setActivePeriod(index);
    setSelectedCell(null);
    if (step > 0)
      setScrollPeriod((current) => ({
        periodKey: plan.periods[index].period_key,
        request: (current?.request ?? 0) + 1,
      }));
  }

  function advance() {
    if (nextPeriod === null) {
      goToStep(1);
      document.getElementById(panelId)?.focus({ preventScroll: true });
      return;
    }
    setActivePeriod(nextPeriod);
    setSelectedCell(null);
    tabListRef.current?.scrollIntoView?.({ block: "start" });
    document.getElementById(tabId(nextPeriod))?.focus();
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

  function renderArrangement(interactive = true) {
    return (
      <div className={interactive ? styles.arrangementGrid : styles.draftArrangement}>
        {interactive && (
          <div className={workspace.stack}>
            <section
              className={`${workspace.card} ${styles.leftPanel}`}
              aria-label="고른 놀이와 선택한 칸"
            >
              <h2 id={pickedHeadingId} tabIndex={-1}>
                고른 놀이 {periodPicks.length}
              </h2>
              <div className={workspace.stack}>
                {pickedCandidates.map((candidate, index) => (
                  <div key={candidate.row_key} className={styles.pickedRow}>
                    <button
                      type="button"
                      id={pickId(candidate.row_key)}
                      aria-pressed={
                        selectedCell?.periodKey === period.period_key &&
                        selectedCell.rowKey === candidate.row_key
                      }
                      className={`${workspace.item} ${styles.playButton}`}
                      onClick={() => selectCell(activePeriod, candidate.row_key, "play_name")}
                    >
                      {candidate.play_name.value}
                    </button>
                    <div className={styles.rowControls}>
                      {([-1, 1] as const).map((delta) => (
                        <button
                          type="button"
                          key={delta}
                          id={`${pickId(candidate.row_key)}-${delta}`}
                          aria-label={`${index + 1}번째 놀이 ${delta === -1 ? "위로" : "아래로"}`}
                          disabled={
                            delta === -1 ? index === 0 : index === pickedCandidates.length - 1
                          }
                          onClick={() => moveCandidate(candidate.row_key, delta)}
                        >
                          {delta === -1 ? "↑" : "↓"}
                        </button>
                      ))}
                      <button
                        type="button"
                        aria-label={`${candidate.play_name.value} 빼기`}
                        onClick={() => removeCandidate(candidate.row_key)}
                      >
                        빼기
                      </button>
                    </div>
                  </div>
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
                        className={
                          selectedCell.field === field.key ? workspace.selected : undefined
                        }
                        onClick={() => selectCell(activePeriod, selectedCell.rowKey, field.key)}
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
              className={`${workspace.card} ${styles.availableCard}`}
              aria-label="넣을 수 있는 놀이"
            >
              <h2>넣을 수 있는 놀이 {period.candidates.length - periodPicks.length}</h2>
              <div className={workspace.stack}>
                {period.candidates.map((candidate, index) => {
                  if (periodPicks.includes(candidate.row_key)) return null;
                  return (
                    <div key={candidate.row_key} className={styles.pickedRow}>
                      <div className={styles.availableName}>
                        <p className={workspace.eyebrow}>후보 {index + 1}</p>
                        <p>{candidate.play_name.value}</p>
                      </div>
                      <button
                        type="button"
                        className={workspace.secondary}
                        aria-label={`${candidate.play_name.value} 넣기`}
                        disabled={periodPicks.length >= MAX_PICKS}
                        onClick={() => addCandidate(candidate.row_key)}
                      >
                        넣기
                      </button>
                    </div>
                  );
                })}
              </div>
              {periodPicks.length === MAX_PICKS && (
                <p
                  role="status"
                  className={`${workspace.muted} ${styles.limitMessage} ${styles.availableLimit}`}
                >
                  5개를 모두 골랐어요. 바꾸려면 하나를 빼 주세요.
                </p>
              )}
            </section>
          </div>
        )}
        <PlayProjectSheet
          plan={plan}
          picks={picks}
          interactive={interactive}
          selectedCell={selectedCell}
          onSelectCell={selectCell}
          zoom={zoom}
          onZoomChange={setZoom}
          scrollPeriod={scrollPeriod}
        />
      </div>
    );
  }

  function renderDraft() {
    const shortages = plan.periods
      .filter((item) => (picks[item.period_key]?.length ?? 0) < MAX_PICKS)
      .map((item) => `${item.label}이 ${picks[item.period_key]?.length ?? 0}개`);
    return (
      <div className={workspace.stack}>
        {shortages.length > 0 && (
          <p role="status" className={workspace.muted}>
            {shortages.join(", ")}예요. 확정하려면 구간마다 5개가 필요해요.
          </p>
        )}
        <div>
          <button type="button" className={workspace.secondary} onClick={() => goToStep(1)}>
            ← 배치하고 다듬기로
          </button>
        </div>
        {renderArrangement(false)}
      </div>
    );
  }

  const tabId = (index: number) => `play-project-tab-${plan.id}-${index}`;
  const panelId = `play-project-panel-${plan.id}`;
  const pickedHeadingId = `${panelId}-picked`;
  const pickId = (rowKey: string) => `${panelId}-${period.period_key}-${rowKey}`;
  return (
    <main className={workspace.page}>
      <div className={styles.meta}>
        <span className={workspace.badge}>{plan.status === "DRAFT" ? "초안" : "확정"}</span>
        <span>{plan.school_year}학년도</span>
      </div>
      <ol className={`${tabs.steps} ${styles.steps}`} aria-label="놀이 프로젝트 결과 단계">
        {["① 놀이 고르기", "② 배치하고 다듬기", "③ 전체 초안 보기"].map((label, index) => (
          <li key={label} className={step === index ? tabs.reached : undefined}>
            <span>0{index + 1}</span>
            <button
              type="button"
              className={styles.stepButton}
              aria-current={step === index ? "step" : undefined}
              onClick={() => goToStep(index)}
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
        ref={tabListRef}
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
            onClick={() => goToPeriod(index)}
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
        className={`${styles.panel} ${showFloating ? styles.panelWithFloating : ""}`}
      >
        {step === 0 && renderPicking()}
        {step === 1 && renderArrangement()}
        {step === 2 && renderDraft()}
      </section>
      {showFloating && (
        <button
          ref={floatingRef}
          type="button"
          className={`${workspace.primary} ${styles.floatingNext}`}
          onClick={advance}
        >
          {nextPeriod === null
            ? "배치하고 다듬기로 →"
            : `다음: ${plan.periods[nextPeriod].label} 고르기 →`}
        </button>
      )}
    </main>
  );
}
