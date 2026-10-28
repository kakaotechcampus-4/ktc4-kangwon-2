"use client";

import {
  useEffect,
  useMemo,
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
import PlayCellEditor from "./PlayCellEditor";
import {
  EMPTY_HISTORY,
  popRedo,
  popUndo,
  pushStep,
  stepSave,
  type EditHistory,
  type EditStep,
} from "@/lib/plan-generator/playEditHistory";
import { usePlaySelectionSave } from "@/lib/hooks/use-play-selection-save";
import type { Rejected } from "@/lib/plan-generator/playSelectionQueue";
import {
  cellButtonId,
  eulReul,
  fields,
  type PlayField,
  type SheetZoom,
} from "./playProjectPagination";
export { buildPlayProjectPreviewRows } from "./playProjectPagination";

const MAX_PICKS = 5;

const SAVE_LABEL = {
  idle: "",
  saving: "저장 중…",
  saved: "저장됨",
  failed: "저장하지 못했어요",
  reloading: "최신 내용을 다시 불러오는 중…",
};

// 서버가 저장해 둔 고르기(selected)가 처음 상태다. 새로고침해도 고른 것이 그대로 보인다.
export function picksFromPlan(plan: PlayProjectAnnualPlan): Record<string, string[]> {
  return Object.fromEntries(plan.periods.map((item) => [item.period_key, item.selected]));
}

// 저장 요청은 네 구간을 전부 보낸다. 아직 안 고른 구간은 빈 목록이다.
export function selectionsOf(plan: PlayProjectAnnualPlan, picks: Record<string, string[]>) {
  return Object.fromEntries(
    plan.periods.map((item) => [item.period_key, picks[item.period_key] ?? []]),
  );
}

// 칸 글 저장 상태. `saved` 는 마지막으로 저장한 값(서버 값과 다른 칸만), `epochs` 는 칸마다 — 되돌리기 · 거절로 그 칸의 입력창을 다시 열 때 올린다.
interface EditState {
  saved: Record<string, string>;
  history: EditHistory;
  epochs: Record<string, number>;
}
const EMPTY_EDIT: EditState = { saved: {}, history: EMPTY_HISTORY, epochs: {} };

function bumped(epochs: Record<string, number>, itemId: string) {
  return { ...epochs, [itemId]: (epochs[itemId] ?? 0) + 1 };
}

function without(values: Record<string, string>, key: string) {
  const rest = { ...values };
  delete rest[key];
  return rest;
}

// 칸 값을 화면에 입힌다. 입력 중 글(live) → 마지막 저장값(saved) → 서버 값 순이다. 바뀐 칸이 없으면 그대로 돌려준다.
export function withCellValues(
  plan: PlayProjectAnnualPlan,
  saved: Record<string, string>,
  live: Record<string, string>,
): PlayProjectAnnualPlan {
  if (!Object.keys(saved).length && !Object.keys(live).length) return plan;
  const pick = (
    cell: PlayProjectAnnualPlan["periods"][number]["candidates"][number]["play_name"],
  ) => ({
    ...cell,
    value: live[cell.item_id] ?? saved[cell.item_id] ?? cell.value,
  });
  return {
    ...plan,
    periods: plan.periods.map((item) => ({
      ...item,
      candidates: item.candidates.map((candidate) => ({
        ...candidate,
        play_name: pick(candidate.play_name),
        materials: pick(candidate.materials),
        support_direction: pick(candidate.support_direction),
      })),
    })),
  };
}

function serverCellValue(plan: PlayProjectAnnualPlan, itemId: string) {
  for (const item of plan.periods)
    for (const candidate of item.candidates)
      for (const field of fields)
        if (candidate[field.key].item_id === itemId) return candidate[field.key].value;
  return "";
}

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

// 보기 설정은 화면 상태에만 둔다. 고른 놀이는 바뀔 때마다 바로 저장한다(ADR-044).
export default function PlayProjectResult({
  plan,
  notice,
  onConflict,
  onDismissNotice,
}: {
  plan: PlayProjectAnnualPlan;
  /** 다시 불러온 직후에 보이는 안내. */
  notice?: string;
  /** 다른 곳에서 바뀌어 저장이 막혔을 때. 부모가 최신 계획안을 다시 불러오고, 끝나면 돌려준다. */
  onConflict: () => Promise<void>;
  /** 고르기가 바뀌거나 저장이 성공하면 다시 불러온 안내를 지우도록 부모에게 알린다. */
  onDismissNotice?: () => void;
}) {
  const [activePeriod, setActivePeriod] = useState(0);
  const [step, setStep] = useState(0);
  const [picks, setPicks] = useState(() => picksFromPlan(plan));
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
  // 입력 중 글(문서 미리보기용) · 마지막으로 저장한 칸 값과 되돌리기 목록 · 되돌렸다는 안내.
  const [live, setLive] = useState<Record<string, string>>({});
  const [edit, setEdit] = useState<EditState>(EMPTY_EDIT);
  const [historyNotice, setHistoryNotice] = useState("");
  const wide = useSyncExternalStore(subscribeWide, isWide, () => false);
  const saving = usePlaySelectionSave(
    plan.id,
    plan.revision,
    onConflict,
    onDismissNotice,
    onRejected,
    selectionsOf(plan, picksFromPlan(plan)),
    Object.keys(live).length > 0,
  );
  // 고르기의 최신 값. 이벤트 핸들러에서만 읽고 쓴다 — 같은 렌더에서 두 번 바뀌어도 앞 변경을 잃지 않는다.
  const latestPicks = useRef(picks);
  const latestEdit = useRef(edit);
  const tabListRef = useRef<HTMLDivElement>(null);
  const floatingRef = useRef<HTMLButtonElement>(null);
  const shown = useMemo(() => withCellValues(plan, edit.saved, live), [plan, edit.saved, live]);
  const period = shown.periods[activePeriod];
  const periodPicks = picks[period.period_key] ?? [];
  const nextPeriod = nextPlayProjectPeriod(plan, picks, activePeriod);
  const total = plan.periods.reduce((sum, item) => sum + (picks[item.period_key]?.length ?? 0), 0);
  const showFloating = step === 0 && periodPicks.length === MAX_PICKS;
  const pickedCandidates = periodPicks.map((key) =>
    period.candidates.find((candidate) => candidate.row_key === key)!,
  );
  const selectedPeriod =
    selectedCell && shown.periods.find((p) => p.period_key === selectedCell.periodKey);
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
    applyPicks(period.period_key, (list) => togglePlayPick(list, rowKey));
  }

  // 고르기를 바꾸는 곳은 전부 여기를 지난다 — 최신 값에서 다음 값을 만들어 화면에 반영하고 저장 큐에 넣는다.
  // 바뀐 게 없으면 null, 바뀌었으면 그 구간의 새 목록을 돌려준다.
  function applyPicks(periodKey: string, change: (list: string[]) => string[]) {
    const list = latestPicks.current[periodKey] ?? [];
    const next = change(list);
    if (next === list) return null;
    const before = selectionsOf(plan, latestPicks.current);
    setPicksTo({ ...latestPicks.current, [periodKey]: next });
    recordStep({ kind: "picks", before, after: selectionsOf(plan, latestPicks.current) });
    return next;
  }

  // 고르기를 이 값으로 바꾸고 저장 큐에 넣는다.
  function setPicksTo(next: Record<string, string[]>) {
    latestPicks.current = next;
    setPicks(next);
    onDismissNotice?.();
    saving.save(selectionsOf(plan, next));
  }

  function setEditBoth(next: EditState) {
    latestEdit.current = next;
    setEdit(next);
  }

  // 새 변경이다 — 되돌리기 목록에 쌓고 다시 하기 목록은 비운다.
  function recordStep(step: EditStep) {
    setHistoryNotice("");
    setEditBoth({ ...latestEdit.current, history: pushStep(latestEdit.current.history, step) });
  }

  // 칸 글을 저장한다. 마지막 저장값과 같으면 보내지 않는다(서버는 같은 값을 422 로 거절한다).
  // `epoch` 는 이 글을 낸 입력창이 그려질 때의 번호다. 그 뒤 되돌리기 · 거절로 입력창이 바뀌었으면 옛 입력창의 글은 버린다.
  function commitCell(itemId: string, value: string, record = true, epoch?: number) {
    const current = latestEdit.current;
    if (epoch !== undefined && epoch !== (current.epochs[itemId] ?? 0)) return;
    const base = savedCellValue(itemId);
    setLive((drafts) => without(drafts, itemId));
    if (value === base.trim()) return;
    saving.saveCell(itemId, value, base);
    onDismissNotice?.();
    const saved = { ...current.saved, [itemId]: value };
    setEditBoth({ ...current, saved });
    if (record) recordStep({ kind: "cell", itemId, before: base, after: value });
  }

  // 서버가 받지 않아 버린 저장 — 화면을 서버가 확인한 값으로 되돌린다. 되돌리기 목록은 더는 맞지 않아 비운다.
  function onRejected(rejected: Rejected) {
    const current = latestEdit.current;
    if (rejected.kind === "picks") {
      latestPicks.current = rejected.selections;
      setPicks(rejected.selections);
      setSelectedCell((cell) =>
        cell && rejected.selections[cell.periodKey]?.includes(cell.rowKey) ? cell : null,
      );
      setEditBoth({ ...current, history: EMPTY_HISTORY });
    } else {
      setLive((drafts) => without(drafts, rejected.itemId));
      const saved = { ...current.saved, [rejected.itemId]: rejected.value };
      setEditBoth({
        saved,
        history: EMPTY_HISTORY,
        epochs: bumped(current.epochs, rejected.itemId),
      });
    }
    announce(
      rejected.kind === "picks"
        ? "저장하지 못한 고르기는 원래대로 되돌렸어요."
        : "저장하지 못한 칸은 원래대로 되돌렸어요.",
    );
  }

  // 같은 문장을 연달아 내도 다시 읽히도록 끝에 보이지 않는 글자를 번갈아 붙인다.
  function announce(message: string) {
    setHistoryNotice((previous) => (previous === message ? message + "\u200b" : message));
  }

  function savedCellValue(itemId: string) {
    return latestEdit.current.saved[itemId] ?? serverCellValue(plan, itemId);
  }

  // 되돌리기 · 다시 하기. 같은 두 저장 API 로 이전 상태를 다시 저장한다.
  function stepThrough(direction: "undo" | "redo") {
    const popped = (direction === "undo" ? popUndo : popRedo)(latestEdit.current.history);
    if (!popped) return;
    const save = stepSave(popped.step, direction, {
      selections: selectionsOf(plan, latestPicks.current),
      cellValue: savedCellValue,
    });
    if (save?.kind === "picks") {
      setPicksTo(save.selections);
      if (selectedCell && !save.selections[selectedCell.periodKey]?.includes(selectedCell.rowKey))
        setSelectedCell(null);
    }
    if (save?.kind === "cell") commitCell(save.itemId, save.value, false);
    // 입력창이 새 값으로 다시 열리도록 번호를 올린다.
    const { step } = popped;
    setEditBoth({
      ...latestEdit.current,
      history: popped.history,
      epochs:
        step.kind === "cell"
          ? bumped(latestEdit.current.epochs, step.itemId)
          : latestEdit.current.epochs,
    });
    announce(direction === "undo" ? "되돌렸어요" : "다시 했어요");
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
    applyPicks(period.period_key, (list) => movePlayPick(list, rowKey, delta));
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
    const placed = applyPicks(periodKey, (list) => placePlayPick(list, from.rowKey, toIndex));
    if (!placed) return;
    const periodIndex = plan.periods.findIndex((item) => item.period_key === periodKey);
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
        periods={shown.periods}
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
        {renderCellField(selectedCandidate[selectedField.key], selectedField)}
      </div>
    );
  }

  // 놀이명 · 지원매체 · 지원 방향은 입력창이고, 배움은 누리과정 원문이라 읽기만 한다.
  function renderCellField(
    cell: { item_id: string; value: string },
    field: (typeof fields)[number],
  ) {
    if (field.key === "learning")
      return (
        <>
          <label htmlFor={cellFieldId}>{field.label}</label>
          <textarea id={cellFieldId} readOnly value={cell.value} />
          <p>배움은 누리과정 원문이라 고칠 수 없어요.</p>
        </>
      );
    const itemId = cell.item_id;
    const epoch = edit.epochs[itemId] ?? 0;
    return (
      <PlayCellEditor
        key={itemId + ":" + epoch}
        id={cellFieldId}
        label={field.label}
        value={edit.saved[itemId] ?? serverCellValue(plan, itemId)}
        onDraft={(text) => setLive((drafts) => ({ ...drafts, [itemId]: text }))}
        onSave={(text) => commitCell(itemId, text, true, epoch)}
        onRevert={() => setLive((drafts) => without(drafts, itemId))}
      />
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
          plan={shown}
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

  const cellFieldId = "play-project-selected-cell";
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
        <span role="status">{SAVE_LABEL[saving.status]}</span>
        {saving.status === "failed" && (
          <button type="button" className={workspace.secondary} onClick={saving.retry}>
            다시 저장
          </button>
        )}
        {(["undo", "redo"] as const).map((direction) => (
          <button
            key={direction}
            type="button"
            className={workspace.secondary}
            disabled={edit.history[direction].length === 0}
            onClick={() => stepThrough(direction)}
          >
            <span aria-hidden="true">{direction === "undo" ? "⟲" : "⟳"}</span>{" "}
            {direction === "undo" ? "되돌리기" : "다시 하기"}
          </button>
        ))}
        <span role="status">{historyNotice}</span>
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
      {notice && (
        <p role="status" className={workspace.notice}>
          {notice}
        </p>
      )}
      <div className={workspace.notice}>
        <p>놀이 프로젝트형은 아직 확정 · 내려받기를 할 수 없어요.</p>
        <p>이 반은 월간 · 주간계획안을 만들 수 없어요.</p>
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
