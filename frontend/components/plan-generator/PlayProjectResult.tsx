"use client";

import {
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type DragEvent,
  type KeyboardEvent,
} from "react";
import type { PlayProjectAnnualPlan } from "@/lib/api/types";
import workspace from "@/components/workspace/Workspace.module.css";
import tabs from "./GenerationFlow.module.css";
import styles from "./PlayProjectResult.module.css";
import PlayProjectPicking from "./PlayProjectPicking";
import PlayProjectSheet, { type PlayDnd } from "./PlayProjectSheet";
import {
  cellButtonId,
  eulReul,
  fields,
  type PlayField,
  type SheetZoom,
} from "./playProjectPagination";
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

// 같은 구간 목록에서 rowKey 를 toIndex 번째 자리로 옮기고 나머지를 민다.
export function placePlayPick(picks: string[], rowKey: string, toIndex: number): string[] {
  const from = picks.indexOf(rowKey);
  const to = Math.max(0, Math.min(picks.length - 1, toIndex));
  if (from < 0 || from === to) return picks;
  const placed = picks.filter((key) => key !== rowKey);
  placed.splice(to, 0, rowKey);
  return placed;
}

// ① 오른쪽 목록에서 slot 을 뺀 뒤 포커스: 뒤 자리가 위로 당겨지므로 같은 자리의 ×, 마지막이었으면 제목(null).
export function removeFocusSlot(count: number, slot: number): number | null {
  return slot < count - 1 ? slot : null;
}

export function leftTabTarget(key: string, current: LeftTab): LeftTab | null {
  if (key === "ArrowRight" || key === "ArrowLeft") return current === "edit" ? "picked" : "edit";
  if (key === "Home") return "edit";
  if (key === "End") return "picked";
  return null;
}

// 문서 행을 끌었으면 옮긴 놀이의 같은 칸(고른 칸이 그 놀이가 아니면 첫 칸), 목록 줄이면 null(목록 버튼).
export function dropFocusField(
  source: "list" | "doc",
  rowKey: string,
  selected: { rowKey: string; field: PlayField } | null,
): PlayField | null {
  if (source === "list") return null;
  return selected?.rowKey === rowKey ? selected.field : "play_name";
}

const wideQuery = "(min-width: 1024px)";
function subscribeWide(callback: () => void) {
  const query = window.matchMedia(wideQuery);
  query.addEventListener("change", callback);
  return () => query.removeEventListener("change", callback);
}
const isWide = () => typeof window !== "undefined" && window.matchMedia(wideQuery).matches;

type LeftTab = "edit" | "picked";
type DragState = {
  periodKey: string;
  rowKey: string;
  from: "list" | "doc";
  over: number | null;
};

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

function candidateName(period: PlayProjectAnnualPlan["periods"][number], rowKey: string) {
  return period.candidates.find((candidate) => candidate.row_key === rowKey)?.play_name.value ?? "";
}

// 놀이명을 넣어 같은 문장이 반복되지 않게 한다(낭독기는 같은 글을 다시 읽지 않는다).
function movedNotice(name: string, index: number) {
  return `「${name}」${eulReul(name)} ${index + 1}번째로 옮겼어요`;
}

function PickedListRow({
  candidate,
  index,
  count,
  periodKey,
  buttonId,
  selected,
  drag,
  draggable,
  dnd,
  onSelect,
  onMove,
  onRemove,
}: {
  candidate: PlayProjectAnnualPlan["periods"][number]["candidates"][number];
  index: number;
  count: number;
  periodKey: string;
  buttonId: string;
  selected: boolean;
  drag: DragState | null;
  draggable: boolean;
  dnd: PlayDnd;
  onSelect: () => void;
  onMove: (delta: -1 | 1) => void;
  onRemove: () => void;
}) {
  // 끌던 줄이 먼저다 — 자기 자리에는 놓을 자리 표시를 켜지 않는다.
  const rowClass =
    drag?.rowKey === candidate.row_key
      ? styles.dragging
      : drag?.over === index
        ? styles.dropOver
        : "";
  const dragProps = draggable
    ? {
        draggable: true,
        onDragStart: (event: DragEvent) => dnd.start(periodKey, candidate.row_key, event, "list"),
        onDragOver: (event: DragEvent) => dnd.over(periodKey, index, event),
        onDrop: (event: DragEvent) => dnd.drop(periodKey, index, event),
        onDragEnd: dnd.end,
      }
    : {};
  return (
    <div className={`${styles.pickedRow} ${rowClass}`} {...dragProps}>
      {draggable && (
        <span className={styles.grip} aria-hidden="true">
          ⠿
        </span>
      )}
      <button
        type="button"
        id={buttonId}
        aria-pressed={selected}
        className={`${workspace.item} ${styles.playButton}`}
        onClick={onSelect}
      >
        {candidate.play_name.value}
      </button>
      <div className={styles.rowControls}>
        {([-1, 1] as const).map((delta) => (
          <button
            type="button"
            key={delta}
            id={`${buttonId}-${delta}`}
            aria-label={`${index + 1}번째 놀이 ${delta === -1 ? "위로" : "아래로"}`}
            disabled={delta === -1 ? index === 0 : index === count - 1}
            onClick={() => onMove(delta)}
          >
            {delta === -1 ? "↑" : "↓"}
          </button>
        ))}
        <button type="button" aria-label={`${candidate.play_name.value} 빼기`} onClick={onRemove}>
          빼기
        </button>
      </div>
    </div>
  );
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
  const [editorTab, setEditorTab] = useState<LeftTab>("edit");
  const [detailKey, setDetailKey] = useState<string | null>(null);
  const [moveNotice, setMoveNotice] = useState("");
  const [drag, setDrag] = useState<DragState | null>(null);
  const wide = useSyncExternalStore(subscribeWide, isWide, () => false);
  const tabListRef = useRef<HTMLDivElement>(null);
  const floatingRef = useRef<HTMLButtonElement>(null);
  const period = plan.periods[activePeriod];
  const periodPicks = picks[period.period_key] ?? [];
  const nextPeriod = nextPlayProjectPeriod(plan, picks, activePeriod);
  const total = plan.periods.reduce((sum, item) => sum + (picks[item.period_key]?.length ?? 0), 0);
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
    setMoveNotice("");
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

  // 목록의 놀이명을 눌러 고를 때(keepTab)는 넓은 화면에서만 목록 탭에 머문다. 좁은 화면은 문서 강조가 안 보인다.
  function selectCell(periodIndex: number, rowKey: string, field: PlayField, keepTab = false) {
    if (!(keepTab && wide)) setEditorTab("edit");
    setMoveNotice("");
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
    setMoveNotice(movedNotice(candidateName(period, rowKey), periodPicks.indexOf(rowKey) + delta));
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

  function dropPlay(periodKey: string, toIndex: number) {
    const from = drag;
    setDrag(null);
    if (!from || from.periodKey !== periodKey) return;
    const current = picks[periodKey] ?? [];
    const placed = placePlayPick(current, from.rowKey, toIndex);
    if (placed === current) return;
    const periodIndex = plan.periods.findIndex((item) => item.period_key === periodKey);
    setPicks((all) => ({ ...all, [periodKey]: placed }));
    // 다른 구간의 문서 행을 옮겼으면 왼쪽 목록과 안내가 그 구간을 가리키게 한다.
    if (periodIndex !== activePeriod) setActivePeriod(periodIndex);
    setMoveNotice(
      movedNotice(
        candidateName(plan.periods[periodIndex], from.rowKey),
        placed.indexOf(from.rowKey),
      ),
    );
    // 자리 번호로 고정한 표 줄이라 옛 자리 버튼에 포커스가 남지 않게 옮긴 놀이로 보낸다.
    const field = dropFocusField(from.from, from.rowKey, selectedCell);
    requestAnimationFrame(() =>
      document
        .getElementById(
          field ? cellButtonId(periodKey, from.rowKey, field) : pickId(from.rowKey, periodKey),
        )
        ?.focus(),
    );
  }

  // 같은 구간 안에서만 놓을 수 있다. 다른 구간 위에서는 preventDefault 를 안 해 놓기가 막힌다.
  const dnd: PlayDnd = {
    dragging: drag,
    start(periodKey, rowKey, event: DragEvent, from) {
      event.dataTransfer.setData("text/plain", rowKey);
      event.dataTransfer.effectAllowed = "move";
      setDrag({ periodKey, rowKey, from, over: null });
    },
    over(periodKey, index, event: DragEvent) {
      if (drag?.periodKey !== periodKey) {
        setDrag((current) =>
          current && current.over !== null ? { ...current, over: null } : current,
        );
        return;
      }
      event.preventDefault();
      setDrag((current) =>
        current && current.over !== index ? { ...current, over: index } : current,
      );
    },
    drop(periodKey, index, event: DragEvent) {
      event.preventDefault();
      dropPlay(periodKey, index);
    },
    end: () => setDrag(null),
  };

  function removeCandidate(rowKey: string) {
    toggleCandidate(rowKey);
    requestAnimationFrame(() => document.getElementById(pickedHeadingId)?.focus());
  }

  function selectLeftTab(tab: LeftTab) {
    setEditorTab(tab);
    setMoveNotice("");
  }

  function onLeftTabKey(event: KeyboardEvent) {
    const target = leftTabTarget(event.key, editorTab);
    if (!target) return;
    event.preventDefault();
    selectLeftTab(target);
    document.getElementById(leftTabId(target))?.focus();
  }

  function removeFromPickList(rowKey: string, slot: number) {
    const target = removeFocusSlot(periodPicks.length, slot);
    toggleCandidate(rowKey);
    requestAnimationFrame(() =>
      document
        .getElementById(
          target === null ? `${pickPrefix}-heading` : `${pickPrefix}-remove-${target}`,
        )
        ?.focus(),
    );
  }

  function addCandidate(rowKey: string) {
    toggleCandidate(rowKey);
    requestAnimationFrame(() => document.getElementById(pickId(rowKey))?.focus());
  }

  function goToStep(index: number) {
    if (index === step) return;
    setScrollPeriod(null);
    setMoveNotice("");
    setDetailKey(null);
    setDrag(null);
    setStep(index);
    requestAnimationFrame(() => window.scrollTo({ top: 0 }));
  }

  function goToPeriod(index: number) {
    setMoveNotice("");
    setDetailKey(null);
    setDrag(null);
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
    setMoveNotice("");
    setDetailKey(null);
    setDrag(null);
    setActivePeriod(nextPeriod);
    setSelectedCell(null);
    tabListRef.current?.scrollIntoView?.({ block: "start" });
    document.getElementById(tabId(nextPeriod))?.focus();
  }

  function renderPicking() {
    return (
      <PlayProjectPicking
        periods={plan.periods}
        period={period}
        picks={picks}
        max={MAX_PICKS}
        detailKey={detailKey}
        idPrefix={pickPrefix}
        onToggle={toggleCandidate}
        onRemove={removeFromPickList}
        onDetail={setDetailKey}
        onArrange={() => goToStep(1)}
      />
    );
  }

  function renderViewer() {
    if (!selectedCandidate || !selectedCell || !selectedField)
      return (
        <p className={`${workspace.muted} ${styles.hint}`}>
          오른쪽 문서의 칸을 누르면 여기에서 볼 수 있어요.
        </p>
      );
    return (
      <div className={`${workspace.field} ${styles.viewer}`}>
        <div className={workspace.pills} aria-label="미리 볼 칸">
          {fields.map((field) => (
            <button
              type="button"
              key={field.key}
              aria-pressed={selectedCell.field === field.key}
              className={selectedCell.field === field.key ? workspace.selected : undefined}
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
    );
  }

  function renderPickedList() {
    return (
      <div className={workspace.stack}>
        <h2 id={pickedHeadingId} tabIndex={-1}>
          고른 놀이 {periodPicks.length}
        </h2>
        <div className={workspace.stack}>
          {pickedCandidates.map((candidate, index) => (
            <PickedListRow
              key={candidate.row_key}
              candidate={candidate}
              index={index}
              count={pickedCandidates.length}
              periodKey={period.period_key}
              buttonId={pickId(candidate.row_key)}
              selected={
                selectedCell?.periodKey === period.period_key &&
                selectedCell.rowKey === candidate.row_key
              }
              drag={drag?.periodKey === period.period_key ? drag : null}
              draggable={wide}
              dnd={dnd}
              onSelect={() => selectCell(activePeriod, candidate.row_key, "play_name", true)}
              onMove={(delta) => moveCandidate(candidate.row_key, delta)}
              onRemove={() => removeCandidate(candidate.row_key)}
            />
          ))}
        </div>
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
              <div
                role="tablist"
                aria-label="왼쪽 패널"
                className={styles.leftTabs}
                onKeyDown={onLeftTabKey}
              >
                {(["edit", "picked"] as const).map((tab) => (
                  <button
                    key={tab}
                    type="button"
                    role="tab"
                    id={leftTabId(tab)}
                    aria-selected={editorTab === tab}
                    aria-controls={leftPanelId(tab)}
                    tabIndex={editorTab === tab ? 0 : -1}
                    onClick={() => selectLeftTab(tab)}
                  >
                    {tab === "edit" ? "내용 편집" : `선택한 놀이 ${periodPicks.length}`}
                  </button>
                ))}
              </div>
              <div
                role="tabpanel"
                id={leftPanelId("edit")}
                aria-labelledby={leftTabId("edit")}
                hidden={editorTab !== "edit"}
              >
                {renderViewer()}
              </div>
              <div
                role="tabpanel"
                id={leftPanelId("picked")}
                aria-labelledby={leftTabId("picked")}
                hidden={editorTab !== "picked"}
              >
                {renderPickedList()}
              </div>
              <p role="status" className={`${workspace.muted} ${styles.moveNotice}`}>
                {moveNotice}
              </p>
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
          dnd={interactive && wide ? dnd : undefined}
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
  const leftTabId = (tab: string) => `${panelId}-left-${tab}`;
  const leftPanelId = (tab: string) => `${panelId}-left-${tab}-panel`;
  const pickId = (rowKey: string, periodKey = period.period_key) =>
    `${panelId}-${periodKey}-${rowKey}`;
  const pickPrefix = `${panelId}-pick`;
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
      <div className={styles.tabRow}>
        <div
          ref={tabListRef}
          role="tablist"
          aria-label="놀이 프로젝트 기간"
          className={`${tabs.tabs} ${tabs.wrappingTabs} ${styles.periodTabs}`}
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
        <p className={styles.total}>
          전체 <strong>{total}</strong>/{plan.periods.length * MAX_PICKS}개 선택
        </p>
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
