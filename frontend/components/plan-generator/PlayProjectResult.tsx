"use client";

import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import type { PlayProjectAnnualPlan } from "@/lib/api/types";
import workspace from "@/components/workspace/Workspace.module.css";
import PlayProjectPicking from "./PlayProjectPicking";
import PlayProjectSheet from "./PlayProjectSheet";
import PlayCellEditor from "./PlayCellEditor";
import PlayMonthlyConfirm from "./PlayMonthlyConfirm";
import AnnualFrame, {
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
  saved: "자동 저장됨",
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

// 끌어놓기: 고른 놀이를 문서의 다른 줄 자리로 옮긴다. 순서 목록만 바꾼다.
export function placePlayPick(picks: string[], rowKey: string, targetKey: string): string[] {
  const to = picks.indexOf(targetKey);
  if (!picks.includes(rowKey) || to < 0 || rowKey === targetKey) return picks;
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
const ROW = "flex items-center justify-between gap-3 rounded-xl border border-[#e8e2d8] px-4 py-3";
// 문서 기준 폭(A4 세로 비율). 「맞춤」은 이 폭을 문서 칸 폭에 맞춰 키우거나 줄인다.
const SHEET_WIDTH = 794;
const SMALL =
  "min-h-[36px] shrink-0 rounded-lg border border-[#ddd6ca] px-3 text-xs font-bold text-[#5e4b96] disabled:opacity-40";

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

  // 목록이나 문서의 놀이를 문서의 다른 줄에 끌어놓았다.
  function dropPick(rowKey: string, targetKey: string) {
    if (!periodPicks.includes(rowKey)) return;
    setMoveNotice(movedNotice(candidateName(period, rowKey), periodPicks.indexOf(targetKey)));
    applyPicks(period.period_key, (list) => placePlayPick(list, rowKey, targetKey));
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
        <h2 className="m-0 font-display text-[24px] font-bold leading-tight">
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
            className="min-h-[44px] flex-1 rounded-lg border border-[#e8e2d8] text-sm text-[#5c5243]"
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
  function renderCandidates() {
    return (
      <div className="flex flex-col gap-2">
        <h2
          id={pickedHeadingId}
          tabIndex={-1}
          className="m-0 mb-1 font-display text-[20px] font-bold leading-tight"
        >
          {seasonLabel} 놀이
        </h2>
        {pickedCandidates.map((candidate, index) => (
          <div
            key={candidate.row_key}
            className={`${ROW} cursor-grab bg-[#fbf9f5]`}
            draggable
            onDragStart={(event) => event.dataTransfer.setData("text/plain", candidate.row_key)}
          >
            <button
              type="button"
              className="flex min-w-0 flex-col text-left"
              onClick={() => selectCell(activePeriod, candidate.row_key, "play_name")}
            >
              <span className="text-[15px] font-bold">
                <span className="mr-2 text-xs text-[#5e4b96]">{index + 1}</span>
                {candidate.play_name.value}
              </span>
              <span className="truncate text-[13px] text-[#5c5243]">
                {candidate.materials.value}
              </span>
            </button>
            <button
              type="button"
              className="min-h-[36px] shrink-0 text-xs text-[#5c5243] underline"
              aria-label={`${candidate.play_name.value} 빼기`}
              onClick={() => toggleCandidate(candidate.row_key)}
            >
              빼기
            </button>
          </div>
        ))}
        {period.candidates
          .filter((candidate) => !periodPicks.includes(candidate.row_key))
          .map((candidate) => (
            <div key={candidate.row_key} className={ROW}>
              <span className="flex min-w-0 flex-col">
                <span className="text-[15px] font-bold">{candidate.play_name.value}</span>
                <span className="truncate text-[13px] text-[#5c5243]">
                  {candidate.materials.value}
                </span>
              </span>
              <button
                type="button"
                className={SMALL}
                aria-label={`${candidate.play_name.value} 넣기`}
                disabled={periodPicks.length >= MAX_PICKS}
                onClick={() => toggleCandidate(candidate.row_key)}
              >
                넣기
              </button>
            </div>
          ))}
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
      className="flex flex-wrap gap-0.5 rounded-xl border border-line bg-paper p-0.5 shadow-pg-card"
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
          {playSeason(item).name && <span>{playSeason(item).name}</span>}
          <span className="text-[13px] font-normal opacity-75">{playSeason(item).months}</span>{" "}
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
            <h1 className="m-0 font-display text-[34px] font-bold leading-none text-primary-deep">
              놀이 고르기
            </h1>
            <span className="rounded-full bg-[#eee4f4] px-3 py-1 text-[13px] font-bold text-[#5e4b96]">
              놀이 중심형
            </span>
            <span role="status" className="text-[13px] text-[#8a8178]">
              {SAVE_LABEL[saving.status]}
            </span>
            {saving.status === "failed" && (
              <button type="button" className={workspace.secondary} onClick={saving.retry}>
                다시 저장
              </button>
            )}
          </div>
          {/* 좁은 화면(< 768px)은 두 열 — 한 줄이면 휴대전화에서 페이지가 가로로 넘친다. */}
          <div
            role="tablist"
            aria-label="놀이 프로젝트 기간"
            className="grid w-full grid-cols-2 gap-1 rounded-xl bg-[#ebe5db] p-1 md:flex md:w-auto"
          >
            {plan.periods.map((item, index) => {
              const count = picks[item.period_key]?.length ?? 0;
              const on = activePeriod === index;
              return (
                <button
                  key={item.period_key}
                  id={tabId(index)}
                  type="button"
                  role="tab"
                  aria-selected={on}
                  aria-controls={panelId}
                  className={`flex min-h-[44px] items-center justify-center gap-2 whitespace-nowrap rounded-lg px-4 text-sm ${on ? "bg-white font-bold shadow-sm" : "text-[#5c5243]"} ${lacking.includes(item.period_key) ? "text-[#b3261e]" : ""}`}
                  onClick={() => goToPeriod(index)}
                >
                  <span className="font-bold">{playSeason(item).name}</span>
                  {playSeason(item).months && (
                    <span className="text-xs font-normal text-[#8a8178]">
                      {playSeason(item).months}
                    </span>
                  )}
                  <span
                    className={`text-xs ${count >= MAX_PICKS ? "font-bold text-[#3b5441]" : "text-[#8a8178]"}`}
                  >
                    {count >= MAX_PICKS ? `✓ ${count}/${MAX_PICKS}` : `${count}/${MAX_PICKS}`}
                  </span>
                </button>
              );
            })}
          </div>
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
            {tab === "picked" && (
              <span className="ml-1.5 rounded-full bg-[#efeae2] px-2 py-0.5 text-xs text-[#5c5243]">
                {period.candidates.length}
              </span>
            )}
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
      status={
        <span className="flex items-center gap-3">
          {SAVE_LABEL[saving.status]}
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
          {periodTabs}
          <div className="relative">
            <button
              type="button"
              className={BUTTON.primary}
              disabled={confirming}
              onClick={() => setAsking(true)}
            >
              확정하기
            </button>
            {asking && (
              <div className={POPOVER}>
                <PlayMonthlyConfirm
                  message="확정하면 확정을 풀기 전까지 고칠 수 없어요. 이 내용으로 월간계획안을 만들게 돼요."
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
      docLabel={null}
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
