"use client";

import { useEffect, useMemo, useRef, useState, type DragEvent, type KeyboardEvent } from "react";
import type { PlayProjectAnnualPlan } from "@/lib/api/types";
import workspace from "@/components/workspace/Workspace.module.css";
import PlayProjectPicking from "./PlayProjectPicking";
import PlayProjectSheet from "./PlayProjectSheet";
import { MemoMark } from "@/components/plan-ui/PlayPickBoard";
import PlayCellEditor from "./PlayCellEditor";
import PlayMonthlyConfirm from "./PlayMonthlyConfirm";
import Link from "next/link";
import AnnualFrame, {
  BACK_BUTTON,
  BACK_ICON,
  BigView,
  BUTTON,
  POPOVER,
  pageClass,
  tabClass,
  UndoRedo,
  useSheetZoom,
} from "./AnnualFrame";
import {
  EMPTY_HISTORY,
  popRedo,
  popUndo,
  pushStep,
  stepSave,
  type EditHistory,
  type EditStep,
} from "@/lib/plan-generator/playEditHistory";
import { ApiError } from "@/lib/api/client";
import { confirmPlayProject, errorFields, isSaveConflict } from "@/lib/api/plans";
import { usePlaySelectionSave } from "@/lib/hooks/use-play-selection-save";
import type { Rejected } from "@/lib/plan-generator/playSelectionQueue";
import { eulReul, fields, playSeason, type PlayField } from "./playProjectPagination";
import { PlanMemoNote } from "./PlanMemo";
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

// 끌어놓기: 끈 놀이가 놓은 줄의 자리로 간다. 고른 놀이면 순서만 바꾸고,
// 다른 후보면 다 찼을 때는 그 줄과 바꾸고(그 줄은 다른 후보로) 자리가 남으면 그 줄 앞에 넣는다.
export function placePlayPick(picks: string[], rowKey: string, targetKey: string): string[] {
  const to = picks.indexOf(targetKey);
  if (to < 0 || rowKey === targetKey) return picks;
  if (!picks.includes(rowKey))
    return picks.length >= MAX_PICKS
      ? picks.map((key) => (key === targetKey ? rowKey : key))
      : [...picks.slice(0, to), rowKey, ...picks.slice(to)];
  const rest = picks.filter((key) => key !== rowKey);
  return [...rest.slice(0, to), rowKey, ...rest.slice(to)];
}

// ④ 고른 놀이 목록에서 slot 을 뺀 뒤 포커스: 뒤 자리가 위로 당겨지므로 같은 자리의 ×, 마지막이었으면 제목(null).
export function removeFocusSlot(count: number, slot: number): number | null {
  return slot < count - 1 ? slot : null;
}

// 왼쪽 탭은 「AI 후보」 → 「칸 편집」 순서다.
export function leftTabTarget(key: string, current: LeftTab): LeftTab | null {
  if (key === "ArrowRight" || key === "ArrowLeft") return current === "edit" ? "picked" : "edit";
  if (key === "Home") return "picked";
  if (key === "End") return "edit";
  return null;
}

function candidateName(period: PlayProjectAnnualPlan["periods"][number], rowKey: string) {
  return period.candidates.find((candidate) => candidate.row_key === rowKey)?.play_name.value ?? "";
}

// 놀이명을 넣어 같은 문장이 반복되지 않게 한다(낭독기는 같은 글을 다시 읽지 않는다).
function movedNotice(name: string, index: number) {
  return `「${name}」${eulReul(name)} ${index + 1}번째로 옮겼어요`;
}

type LeftTab = "edit" | "picked";
// 문서 기준 폭(A4 세로 비율). 「맞춤」은 이 폭을 문서 칸 폭에 맞춰 키우거나 줄인다.
const SHEET_WIDTH = 794;
const SMALL =
  "min-h-[36px] shrink-0 rounded-lg border border-[#ddd6ca] px-3 text-xs font-bold text-[#5e4b96] disabled:opacity-40";
/** 끌어서 순서를 바꾸는 손잡이(점 여섯 개). */
const GRIP = (
  <svg
    aria-hidden="true"
    viewBox="0 0 10 16"
    width="10"
    height="16"
    className="shrink-0 text-[#b8ae9f]"
    fill="currentColor"
  >
    {[2, 8, 14].map((y) => [2, 8].map((x) => <circle key={`${x}${y}`} cx={x} cy={y} r="1.5" />))}
  </svg>
);
const DROP_ON = "[&[data-drop]]:bg-[#efe7f8]";

// 끌어 온 놀이를 받는 곳. 받을 곳 강조는 data-drop 으로만 — 문서 줄과 같은 방식.
const DROP_HOVER = {
  onDragOver: (event: DragEvent<HTMLElement>) => {
    event.preventDefault();
    event.currentTarget.dataset.drop = "";
  },
  onDragLeave: (event: DragEvent<HTMLElement>) => {
    delete event.currentTarget.dataset.drop;
  },
};

/** 놓은 놀이의 row_key. 바깥 받는 곳(묶음)이 한 번 더 받지 않게 여기서 멈춘다. */
function takeDrop(event: DragEvent<HTMLElement>) {
  event.preventDefault();
  event.stopPropagation();
  delete event.currentTarget.dataset.drop;
  return event.dataTransfer.getData("text/plain");
}

/**
 * 놀이 중심형 연간: ④ 놀이 고르기 → ⑤ 다듬기(왼쪽 AI 후보 · 칸 편집, 오른쪽 문서). 확정본은 부모가 ⑥ 으로 그린다.
 * 고른 놀이와 칸 글은 바뀔 때마다 바로 저장한다(ADR-044).
 */
export default function PlayProjectResult({
  plan,
  className = "",
  notice,
  onConflict,
  onDismissNotice,
  onConfirmed,
}: {
  plan: PlayProjectAnnualPlan;
  /** 문서 제목에 붙는 반 이름. 브라우저에 반 정보가 없으면 빈 값. */
  className?: string;
  /** 다시 불러온 직후에 보이는 안내. */
  notice?: string;
  /** 다른 곳에서 바뀌어 저장이 막혔을 때. 부모가 최신 계획안을 다시 불러오고, 끝나면 돌려준다. */
  onConflict: () => Promise<void>;
  /** 고르기가 바뀌거나 저장이 성공하면 다시 불러온 안내를 지우도록 부모에게 알린다. */
  onDismissNotice?: () => void;
  /** 확정이 끝났다. 부모가 응답 계획안으로 ⑥ 을 그린다. */
  onConfirmed: (plan: PlayProjectAnnualPlan) => void;
}) {
  const [activePeriod, setActivePeriod] = useState(0);
  const [picks, setPicks] = useState(() => picksFromPlan(plan));
  // 네 구간이 다 차 있으면 ⑤ 부터 연다.
  const [step, setStep] = useState(() =>
    plan.periods.every((p) => p.selected.length === MAX_PICKS) ? 1 : 0,
  );
  const [selectedCell, setSelectedCell] = useState<{
    periodKey: string;
    rowKey: string;
    field: PlayField;
  } | null>(null);
  const [editorTab, setEditorTab] = useState<LeftTab>("picked");
  const [detailKey, setDetailKey] = useState<string | null>(null);
  const [moveNotice, setMoveNotice] = useState("");
  // 문서 크게 보기 창 — 확정이 막혀 패널로 보낼 때 닫는다.
  const bigDialog = useRef<HTMLDialogElement>(null);
  const [asking, setAsking] = useState(false);
  // 입력 중 글(문서 미리보기용) · 마지막으로 저장한 칸 값과 되돌리기 목록 · 되돌렸다는 안내.
  const [live, setLive] = useState<Record<string, string>>({});
  const [edit, setEdit] = useState<EditState>(EMPTY_EDIT);
  const [historyNotice, setHistoryNotice] = useState("");
  // 확정 중 여부 · 실패 안내 · 5개가 안 찬 구간 키(탭 강조).
  const [confirming, setConfirming] = useState(false);
  const [confirmError, setConfirmError] = useState("");
  const [lacking, setLacking] = useState<string[]>([]);
  const docBox = useRef<HTMLDivElement>(null);
  const sheetZoom = useSheetZoom(docBox, SHEET_WIDTH, step);
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
  const confirmLock = useRef(false);
  // 확정이 큐를 기다리기 시작한 뒤에는 새 변경을 받지 않는다(그 사이 PUT 과 confirm 이 겹치지 않게).
  const frozen = useRef(false);
  // 화면이 내려간 뒤에는 confirm 도 onConfirmed 도 setState 도 하지 않는다.
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const shown = useMemo(() => withCellValues(plan, edit.saved, live), [plan, edit.saved, live]);
  const period = shown.periods[activePeriod];
  const periodPicks = picks[period.period_key] ?? [];
  const seasonLabel = [playSeason(period).name, playSeason(period).months]
    .filter(Boolean)
    .join(" ");
  const pickedCandidates = periodPicks.map((key) =>
    period.candidates.find((candidate) => candidate.row_key === key)!,
  );
  const selectedPeriod =
    selectedCell && shown.periods.find((p) => p.period_key === selectedCell.periodKey);
  const selectedCandidate = selectedPeriod?.candidates.find(
    (candidate) => candidate.row_key === selectedCell?.rowKey,
  );
  const selectedField = selectedCell && fields.find((field) => field.key === selectedCell.field);
  // 확정 전에 채울 첫 곳 — 놀이를 5개 다 고르지 않은 구간, 또는 고른 놀이의 빈 칸(배움은 서버 원문이라 뺀다).
  const gap = (() => {
    for (const [index, item] of shown.periods.entries()) {
      const keys = picks[item.period_key] ?? [];
      if (keys.length < MAX_PICKS) return { index, rowKey: null, field: null };
      for (const rowKey of keys) {
        const row = item.candidates.find((candidate) => candidate.row_key === rowKey);
        const field = row && fields.find((f) => f.key !== "learning" && !row[f.key].value.trim());
        if (field) return { index, rowKey, field: field.key };
      }
    }
    return null;
  })();
  // 빈 곳 알림 — 0 이면 닫힘. 다시 누를 때마다 올려 새로 그려 다시 흔든다.
  const [nudge, setNudge] = useState(0);

  function toggleCandidate(rowKey: string) {
    setMoveNotice("");
    if (
      periodPicks.includes(rowKey) &&
      selectedCell?.periodKey === period.period_key &&
      selectedCell.rowKey === rowKey
    )
      setSelectedCell(null);
    applyPicks(period.period_key, (list) => togglePlayPick(list, rowKey));
  }

  // 고르기를 바꾸는 곳은 전부 여기를 지난다 — 최신 값에서 다음 값을 만들어 화면에 반영하고 저장 큐에 넣는다.
  // 바뀐 게 없으면 null, 바뀌었으면 그 구간의 새 목록을 돌려준다.
  function applyPicks(periodKey: string, change: (list: string[]) => string[]) {
    if (frozen.current) return null;
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
    if (frozen.current) return;
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
    setHistoryNotice((previous) => (previous === message ? message + "​" : message));
  }

  function savedCellValue(itemId: string) {
    return latestEdit.current.saved[itemId] ?? serverCellValue(plan, itemId);
  }

  // 되돌리기 · 다시 하기. 같은 두 저장 API 로 이전 상태를 다시 저장한다.
  function stepThrough(direction: "undo" | "redo") {
    if (frozen.current) return;
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
  }

  // 문서 칸이나 목록의 놀이명을 누르면 그 칸을 「칸 편집」에서 연다.
  function selectCell(periodIndex: number, rowKey: string, field: PlayField) {
    setEditorTab("edit");
    setMoveNotice("");
    setActivePeriod(periodIndex);
    setSelectedCell({ periodKey: plan.periods[periodIndex].period_key, rowKey, field });
  }

  // 목록이나 문서의 놀이(고른 것 · 다른 후보)를 고른 놀이 줄에 끌어놓았다.
  function dropPick(rowKey: string, targetKey: string) {
    if (!period.candidates.some((c) => c.row_key === rowKey)) return;
    const name = candidateName(period, rowKey);
    const picked = periodPicks.includes(rowKey);
    const next = applyPicks(period.period_key, (list) => placePlayPick(list, rowKey, targetKey));
    if (!next) return;
    if (!next.includes(targetKey) && selectedCell?.rowKey === targetKey) setSelectedCell(null);
    const index = next.indexOf(rowKey);
    setMoveNotice(
      picked ? movedNotice(name, index) : `「${name}」${eulReul(name)} ${index + 1}번째에 넣었어요`,
    );
  }

  // 고른 놀이를 「다른 후보」로 끌어 왔다 — 문서에서 뺀다.
  function dropToRest(rowKey: string) {
    if (periodPicks.includes(rowKey)) toggleCandidate(rowKey);
  }

  // 다른 후보를 고른 놀이 묶음(줄 밖)에 끌어 왔다 — 자리가 남으면 맨 아래에 넣는다.
  function dropToPicked(rowKey: string) {
    if (!periodPicks.includes(rowKey) && period.candidates.some((c) => c.row_key === rowKey))
      toggleCandidate(rowKey);
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

  function goToPeriod(index: number) {
    setMoveNotice("");
    setDetailKey(null);
    setActivePeriod(index);
    setSelectedCell(null);
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
        onArrange={() => setStep(1)}
        onPeriod={goToPeriod}
      />
    );
  }

  // 칸 편집: 칸 칩 · 입력창 · 문서에서 빼기. 순서는 문서에서 끌어 옮긴다.
  function renderViewer() {
    if (!selectedCandidate || !selectedCell || !selectedField)
      return (
        <p className="m-0 text-[15px] text-[#5c5243]">
          오른쪽 문서의 칸을 누르면 여기에서 고칠 수 있어요.
        </p>
      );
    return (
      <div className="flex flex-col gap-4">
        <h2 className="m-0 text-[20px] font-bold leading-tight">
          {selectedCandidate.play_name.value}
        </h2>
        <div className="flex flex-wrap gap-1.5" aria-label="고칠 칸">
          {fields.map((field) => (
            <button
              type="button"
              key={field.key}
              aria-pressed={selectedCell.field === field.key}
              className={`min-h-[36px] rounded-full border px-3 text-sm ${selectedCell.field === field.key ? "border-[#7053a0] bg-[#f6f1fb] font-bold text-[#5e4b96]" : "border-[#e8e2d8] text-[#5c5243]"}`}
              onClick={() => selectCell(activePeriod, selectedCell.rowKey, field.key)}
            >
              {field.key === "learning" ? "배움" : field.label}
            </button>
          ))}
        </div>
        <div className={workspace.field}>
          {renderCellField(selectedCandidate[selectedField.key], selectedField)}
        </div>
        <div className="flex gap-2 border-t border-[#efeae2] pt-4">
          <button
            type="button"
            className={BUTTON.quiet}
            onClick={() => toggleCandidate(selectedCandidate.row_key)}
          >
            문서에서 빼기
          </button>
        </div>
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

  // AI 후보: 문서에 넣은 놀이(순서 · 빼기)와 넣을 수 있는 나머지 후보(넣기).
  // 고른 놀이는 번호 붙은 한 묶음, 나머지는 한 장씩 테두리 카드. 둘 다 끌어서 서로 옮긴다(문서 줄에도 놓을 수 있다).
  function renderCandidates() {
    const rest = period.candidates.filter((c) => !periodPicks.includes(c.row_key));
    const full = periodPicks.length >= MAX_PICKS;
    return (
      <div className="flex flex-col gap-5">
        <section
          className="flex flex-col gap-2"
          {...DROP_HOVER}
          onDrop={(event) => dropToPicked(takeDrop(event))}
        >
          <h2
            id={pickedHeadingId}
            tabIndex={-1}
            className="m-0 flex items-baseline justify-between text-[18px] font-bold leading-tight"
          >
            {seasonLabel} 놀이
            <span className="text-[13px] font-normal text-ink-soft">
              {periodPicks.length}/{MAX_PICKS} 골랐어요
            </span>
          </h2>
          {pickedCandidates.length > 0 && (
            <ol className="m-0 list-none divide-y divide-[#ece6dc] rounded-md border border-line bg-paper p-0">
              {pickedCandidates.map((candidate, index) => (
                <li
                  key={candidate.row_key}
                  className={`flex cursor-grab items-center gap-2.5 py-2.5 pl-2 pr-3 hover:bg-[#fbf9f5] ${DROP_ON}`}
                  draggable
                  onDragStart={(event) =>
                    event.dataTransfer.setData("text/plain", candidate.row_key)
                  }
                  {...DROP_HOVER}
                  onDrop={(event) => dropPick(takeDrop(event), candidate.row_key)}
                >
                  {GRIP}
                  <span
                    aria-hidden="true"
                    className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#efe8f7] text-xs font-bold text-primary-ink"
                  >
                    {index + 1}
                  </span>
                  <button
                    type="button"
                    className="flex min-w-0 flex-1 flex-col text-left"
                    onClick={() => selectCell(activePeriod, candidate.row_key, "play_name")}
                  >
                    <span className="truncate text-[15px] font-bold">
                      {candidate.play_name.value}
                    </span>
                    <span className="truncate text-[13px] text-ink-soft">
                      {candidate.materials.value}
                    </span>
                  </button>
                  {candidate.memo_applied && <MemoMark />}
                  <button
                    type="button"
                    className="min-h-[36px] shrink-0 rounded-md px-2.5 text-[13px] text-ink-soft hover:bg-[#f3efe8] hover:text-ink"
                    aria-label={`${candidate.play_name.value} 빼기`}
                    onClick={() => toggleCandidate(candidate.row_key)}
                  >
                    빼기
                  </button>
                </li>
              ))}
            </ol>
          )}
        </section>
        {rest.length > 0 && (
          <section
            className={`-m-1.5 flex flex-col gap-1 rounded-md p-1.5 ${DROP_ON}`}
            {...DROP_HOVER}
            onDrop={(event) => dropToRest(takeDrop(event))}
          >
            <h3 className="m-0 text-[15px] font-bold text-ink">다른 후보 {rest.length}개</h3>
            <p className="m-0 mb-1 text-[13px] text-ink-soft">
              {full
                ? "위 놀이나 문서 줄에 끌어 놓으면 그 놀이와 바뀌어요."
                : "넣으면 고른 놀이 맨 아래에 붙어요. 끌어 놓으면 그 자리에 들어가요."}
            </p>
            <ul className="m-0 flex list-none flex-col gap-2 p-0">
              {rest.map((candidate) => (
                <li
                  key={candidate.row_key}
                  className="flex cursor-grab items-center gap-2.5 rounded-md border border-line bg-[#faf8f4] py-2.5 pl-2 pr-3 hover:bg-[#f5f1e9]"
                  draggable
                  onDragStart={(event) =>
                    event.dataTransfer.setData("text/plain", candidate.row_key)
                  }
                >
                  {GRIP}
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="truncate text-[15px] font-bold">
                      {candidate.play_name.value}
                    </span>
                    <span className="truncate text-[13px] text-ink-soft">
                      {candidate.materials.value}
                    </span>
                  </span>
                  {candidate.memo_applied && <MemoMark />}
                  <button
                    type="button"
                    className={SMALL}
                    aria-label={`${candidate.play_name.value} 넣기`}
                    disabled={full}
                    onClick={() => toggleCandidate(candidate.row_key)}
                  >
                    + 넣기
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    );
  }

  // 확정(ADR-044 §2 · §4): 입력 중 글을 큐에 넣고 → 남은 저장이 끝나길 기다린 뒤 → 마지막 revision 으로 확정한다.
  async function confirm() {
    if (confirmLock.current) return;
    confirmLock.current = true;
    setConfirming(true);
    setConfirmError("");
    setLacking([]);
    try {
      (document.activeElement as HTMLElement | null)?.blur();
      frozen.current = true; // blur 가 넣은 마지막 저장까지는 받았다. 이제부터 새 변경은 받지 않는다.
      const idle = await saving.whenIdle();
      if (!mounted.current) return;
      if (!idle.saved) {
        setConfirmError("저장하지 못했어요. 다시 저장한 뒤 확정해 주세요.");
        return;
      }
      const done = await confirmPlayProject(plan.id, idle.revision);
      if (mounted.current) onConfirmed(done);
    } catch (error) {
      if (!mounted.current) return;
      if (isSaveConflict(error)) {
        await onConflict();
        return;
      }
      const keys = error instanceof ApiError && error.status === 422 ? errorFields(error) : [];
      const short = plan.periods.filter((item) => keys.includes(item.period_key));
      if (short.length) {
        // 5개가 안 찬 첫 구간으로 보내고 AI 후보 탭을 연다 — 거기서 넣으면 된다.
        setLacking(short.map((item) => item.period_key));
        goToPeriod(plan.periods.indexOf(short[0]));
        setEditorTab("picked");
        bigDialog.current?.close();
        setConfirmError(`${short.map((item) => item.label).join(" · ")} 놀이를 5개 골라 주세요.`);
      } else setConfirmError(error instanceof Error ? error.message : "확정하지 못했어요.");
    } finally {
      confirmLock.current = false;
      frozen.current = false;
      if (mounted.current) {
        setConfirming(false);
        setAsking(false);
      }
    }
  }

  const cellFieldId = "play-project-selected-cell";
  const tabId = (index: number) => `play-project-tab-${plan.id}-${index}`;
  const panelId = `play-project-panel-${plan.id}`;
  const pickedHeadingId = `${panelId}-picked`;
  const leftTabId = (tab: string) => `${panelId}-left-${tab}`;
  const leftPanelId = (tab: string) => `${panelId}-left-${tab}-panel`;
  const pickPrefix = `${panelId}-pick`;
  const periodTabs = (
    <div
      role="tablist"
      aria-label="놀이 프로젝트 기간"
      className="flex flex-wrap gap-0.5 rounded-md border border-line bg-paper p-0.5"
    >
      {plan.periods.map((item, index) => (
        <button
          key={item.period_key}
          id={tabId(index)}
          type="button"
          role="tab"
          aria-selected={activePeriod === index}
          aria-controls={panelId}
          className={`${pageClass(activePeriod === index)} inline-flex items-center gap-1.5 ${lacking.includes(item.period_key) ? "text-[#b3261e]" : ""}`}
          onClick={() => goToPeriod(index)}
        >
          {/* 문서 위 도구줄에 들어가 좁다 — 계절 이름이 있으면 달은 마우스를 올리면 보인다. */}
          {playSeason(item).name ? (
            <span title={playSeason(item).months}>{playSeason(item).name}</span>
          ) : (
            <span className="text-[13px] font-normal">{playSeason(item).months}</span>
          )}{" "}
          <span
            className={`rounded-full px-1.5 text-xs font-bold ${lacking.includes(item.period_key) ? "bg-[#fdecea]" : "bg-[#f3efe8]"}`}
          >
            {picks[item.period_key]?.length ?? 0}/{MAX_PICKS}
          </span>
        </button>
      ))}
    </div>
  );

  // ④ 놀이 고르기.
  if (step === 0)
    return (
      <main className={workspace.page}>
        {/* 정답지 ④: 제목 · 칩 · 안내 · 저장 상태 | 계절 탭 — 한 줄. */}
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3">
            {/* 편집 화면과 같은 ← 돌아가기. */}
            <Link
              href="/plans"
              aria-label="돌아가기: 계획안"
              title="계획안"
              className={BACK_BUTTON}
            >
              {BACK_ICON}
            </Link>
            <h1 className="m-0 font-display text-[34px] font-bold leading-[1.2] text-ink">
              놀이 고르기
            </h1>
            <span className="rounded-full bg-[#eee4f4] px-3 py-1 text-[13px] font-bold text-[#5e4b96]">
              놀이 중심형
            </span>
            <span role="status" className="text-[13px] text-ink-soft">
              {SAVE_LABEL[saving.status]}
            </span>
            {saving.status === "failed" && (
              <button type="button" className={workspace.secondary} onClick={saving.retry}>
                다시 저장
              </button>
            )}
          </div>
          {/* 계절 탭은 ⑤ 문서 머리줄과 같은 것 — 넘치면 다음 줄로 내려가서 휴대전화에서도 가로로 넘치지 않는다. */}
          {periodTabs}
        </div>
        {notice && (
          <p role="status" className={workspace.notice}>
            {notice}
          </p>
        )}
        <section id={panelId} role="tabpanel" aria-labelledby={tabId(activePeriod)} tabIndex={0}>
          {renderPicking()}
        </section>
      </main>
    );

  const aside = (
    <>
      <div
        role="tablist"
        aria-label="왼쪽 패널"
        className="flex gap-5 border-b border-[#efeae2] px-6 pt-2"
        onKeyDown={onLeftTabKey}
      >
        {(["picked", "edit"] as const).map((tab) => (
          <button
            key={tab}
            type="button"
            role="tab"
            id={leftTabId(tab)}
            aria-selected={editorTab === tab}
            aria-controls={leftPanelId(tab)}
            tabIndex={editorTab === tab ? 0 : -1}
            className={tabClass(editorTab === tab)}
            onClick={() => selectLeftTab(tab)}
          >
            {tab === "edit" ? "칸 편집" : "AI 후보"}
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
        <div
          role="tabpanel"
          id={leftPanelId("picked")}
          aria-labelledby={leftTabId("picked")}
          hidden={editorTab !== "picked"}
        >
          {renderCandidates()}
        </div>
        <div
          role="tabpanel"
          id={leftPanelId("edit")}
          aria-labelledby={leftTabId("edit")}
          hidden={editorTab !== "edit"}
        >
          {renderViewer()}
        </div>
        <p role="status" className="m-0 mt-3 text-[13px] text-[#5c5243]">
          {moveNotice}
        </p>
      </div>
    </>
  );
  return (
    <AnnualFrame
      title={`${plan.school_year} 연간계획안`}
      format={plan.format}
      lead={
        <Link href="/plans" aria-label="돌아가기: 계획안" title="계획안" className={BACK_BUTTON}>
          {BACK_ICON}
        </Link>
      }
      saved={SAVE_LABEL[saving.status]}
      status={
        <span className="flex items-center gap-3">
          <PlanMemoNote plan={plan} />
        </span>
      }
      notice={
        <>
          {notice && (
            <p role="status" className="m-0 text-sm text-[#5c5243]">
              {notice}
            </p>
          )}
          {saving.status === "failed" && (
            <button type="button" className={BUTTON.outline + " self-start"} onClick={saving.retry}>
              다시 저장
            </button>
          )}
          <span role="status" className="sr-only">
            {historyNotice}
          </span>
          {confirmError && (
            <p role="alert" className="m-0 text-sm font-bold text-[#b3261e]">
              {confirmError}
            </p>
          )}
        </>
      }
      actions={
        <>
          <div className="relative">
            <button
              type="button"
              className={BUTTON.primary}
              disabled={confirming}
              onClick={() => {
                if (!gap) return setAsking(true);
                setAsking(false);
                setNudge((n) => n + 1);
              }}
            >
              확정하기
            </button>
            {nudge > 0 && gap && (
              <div className={POPOVER}>
                <PlayMonthlyConfirm
                  key={nudge}
                  shake
                  message={
                    gap.rowKey
                      ? "아직 빈칸이 남아있어요. 빈칸을 채운 뒤 확정해 주세요."
                      : `아직 고르지 않은 놀이가 남아있어요. 기간마다 ${MAX_PICKS}개를 고른 뒤 확정해 주세요.`
                  }
                  no={gap.rowKey ? "빈칸 채우기" : "놀이 고르기"}
                  onNo={() => {
                    setNudge(0);
                    if (gap.rowKey) selectCell(gap.index, gap.rowKey, gap.field);
                    else {
                      goToPeriod(gap.index);
                      setEditorTab("picked");
                    }
                  }}
                />
              </div>
            )}
            {asking && (
              <div className={POPOVER}>
                <PlayMonthlyConfirm
                  message="확정하면 고칠 수 없어요(고치려면 문서 보관함의 「수정하기」를 눌러요). 이 내용으로 월간계획안을 만들게 돼요."
                  yes={confirming ? "확정하는 중…" : "확정하기"}
                  no="더 다듬기"
                  disabled={confirming}
                  onYes={confirm}
                  onNo={() => setAsking(false)}
                />
              </div>
            )}
          </div>
        </>
      }
      aside={aside}
      docLabel={periodTabs}
      docHint={
        <div className="flex items-center gap-2">
          <UndoRedo
            disabled={confirming}
            canUndo={edit.history.undo.length > 0}
            onUndo={() => stepThrough("undo")}
            canRedo={edit.history.redo.length > 0}
            onRedo={() => stepThrough("redo")}
          />
          {sheetZoom.tools}
          <span>
            <BigView
              pages={Math.ceil(plan.periods.length / 2)}
              width={SHEET_WIDTH}
              dialog={bigDialog}
              render={(page) => (
                <PlayProjectSheet
                  plan={shown}
                  className={className}
                  picks={picks}
                  periods={[page * 2, page * 2 + 1].filter((i) => i < plan.periods.length)}
                  perPage={2}
                />
              )}
            />
          </span>
        </div>
      }
    >
      <div ref={docBox}>
        <section
          id={panelId}
          role="tabpanel"
          aria-labelledby={tabId(activePeriod)}
          style={{ zoom: sheetZoom.percent / 100, width: SHEET_WIDTH }}
          className="mx-auto"
        >
          <PlayProjectSheet
            plan={shown}
            className={className}
            picks={picks}
            periods={[activePeriod]}
            selectedCell={selectedCell}
            onSelectCell={selectCell}
            onDropPick={dropPick}
          />
        </section>
      </div>
    </AnnualFrame>
  );
}
