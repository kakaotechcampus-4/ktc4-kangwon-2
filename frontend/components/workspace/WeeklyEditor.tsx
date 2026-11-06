"use client";

/**
 * 주간계획안 다듬기(Ⓦ3) — 월간 v1 편집(MonthlyPlanEditor)과 같은 틀 · 같은 저장 방식.
 * 문서 칸을 누르면 왼쪽 패널에서 고친다. 입력을 멈추거나 칸을 떠나면 그 칸만 저장하고,
 * 저장 · 다시 만들기 · 후보 넣기 · 칸 나누기 · 확정은 한 줄로 세워 앞 요청이 돌려준 revision 으로 보낸다.
 * 409 면 덮어쓰지 않고 다시 불러온다. 저장하지 못한 글은 남겨 다시 저장하게 한다.
 * 교사 입력 칸(가정 연계 · 행사 · 특별활동)은 AI가 쓰지 않아 다시 만들기가 없다 (계약 §6-2).
 */

import { useEffect, useRef, useState, type ReactNode } from "react";
import { ApiError } from "@/lib/api/client";
import { isSaveConflict } from "@/lib/api/plans";
import {
  addWeeklyIndoorPlay,
  confirmWeeklyPlan,
  copyWeeklyActivity,
  downloadWeeklyHwpx,
  editWeeklyCell,
  getWeeklyPlanAudit,
  orderWeeklyIndoorPlays,
  removeWeeklyActivityCell,
  removeWeeklyIndoorPlay,
  splitWeeklyActivityCell,
} from "@/lib/api/weekly";
import type { WeeklyCell, WeeklyPlan } from "@/lib/api/types";
import { DAY_NAMES, sectionName } from "@/lib/weekly/section-labels";
import PlayCellEditor from "@/components/plan-generator/PlayCellEditor";
import { findingLines } from "@/lib/monthly/findings";
import PlayMonthlyConfirm, {
  BLANK_LEAD,
  BlankRows,
} from "@/components/plan-generator/PlayMonthlyConfirm";
import { CARD, GRIP, PICKED, PUT } from "@/components/plan-generator/PlayMonthlySafetyPanel";
import AnnualFrame, {
  BACK_BUTTON,
  BACK_ICON,
  BigView,
  BUTTON,
  PlanDone,
  POPOVER,
  tabClass,
  UndoRedo,
  useSheetZoom,
} from "@/components/plan-generator/AnnualFrame";
import { PAPER_WIDTH, type Pick } from "@/components/plan-generator/PlayMonthlySheet";
import { useCompactShell } from "@/components/app/compact-shell";
import { useCellHistory } from "./useCellHistory";
import WeeklySheet, { WEEKLY_ACTIVITY_DRAG } from "./WeeklySheet";
import WeeklyIndoorPlayPanel from "./WeeklyIndoorPlayPanel";
import workspace from "./Workspace.module.css";
import { PlanMemoNote } from "@/components/plan-generator/PlanMemo";

const SAVE_LABEL = { idle: "", saving: "저장 중…", saved: "저장됨", failed: "저장하지 못했어요" };

function describe(e: unknown, fallback: string): string {
  if (e instanceof ApiError) return e.message;
  return e instanceof Error ? e.message : fallback;
}

/** 누가 쓴 값인가. 교사 수정은 생성 방식을 바꾸지 않으므로 이력에서 읽는다 (CLAUDE.md §13.2). */
export function originOf(cell: WeeklyCell, edited: Set<string>) {
  if (cell.teacher_input) return cell.value.trim() ? "직접 입력" : "";
  if (edited.has(cell.item_id)) return "교사 수정";
  const method = cell.generation?.method;
  if (method === "RULE_LLM") return "AI 초안";
  if (cell.generation?.rule_id === "weekly.activity_copy") return "후보에서 선택";
  if (method === "RULE_ONLY") return "자동 선택";
  if (method === "MANUAL") return "직접 입력";
  return "";
}

/** 「교사 수정」 칸 — 칸마다 마지막 이력이 TEACHER_EDITED 인 것. */
function useEdited(plan: WeeklyPlan) {
  const [edited, setEdited] = useState<Set<string>>(new Set());
  useEffect(() => {
    let alive = true;
    getWeeklyPlanAudit(plan.id)
      .then(({ items }) => {
        const last = new Map<string, string>();
        for (const e of items)
          if (e.item_id && ["TEACHER_EDITED", "REGENERATED", "CANDIDATE_COPIED"].includes(e.type))
            last.set(e.item_id, e.type);
        if (alive)
          setEdited(new Set([...last].filter(([, t]) => t === "TEACHER_EDITED").map(([id]) => id)));
      })
      .catch(() => alive && setEdited(new Set()));
    return () => {
      alive = false;
    };
  }, [plan.id, plan.revision]);
  return edited;
}

export default function WeeklyEditor({
  plan,
  onPlan,
  onConflict,
  onBack,
  className,
  notice,
}: {
  plan: WeeklyPlan;
  onPlan: (plan: WeeklyPlan) => void;
  /** 409 — 그 사이 바뀌었다. 다시 불러오는 일은 화면이 한다. */
  onConflict: () => void;
  /** 「←」 — 열린 입력을 다 저장한 뒤 만들기로 돌아간다. */
  onBack: () => void;
  /** 용지 오른쪽 위 반 이름. */
  className: string;
  /** 화면이 띄우는 안내(다시 불러옴 등). */
  notice?: ReactNode;
}) {
  const [live, setLive] = useState<Record<string, string>>({});
  const [selected, setSelected] = useState<string | null>(null);
  const [tab, setTab] = useState<"ai" | "edit">("edit");
  const [asking, setAsking] = useState<"" | "confirm">("");
  // 「이 칸 빼기」를 묻는 칸 — 글이 있는 칸은 되돌릴 수 없어 한 번 묻는다.
  const [dropAsk, setDropAsk] = useState<string | null>(null);
  const history = useCellHistory();
  const docBox = useRef<HTMLDivElement>(null);
  const sheetZoom = useSheetZoom(docBox, PAPER_WIDTH);
  const [bump, setBump] = useState(0);
  const [status, setStatus] = useState<keyof typeof SAVE_LABEL>("idle");
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  // 머리줄 안내를 지우는 타이머 — 마지막 안내의 것만 남긴다(같은 문구가 이어져도 일찍 지우지 않는다).
  const flash = useRef<ReturnType<typeof setTimeout>>(undefined);
  const [problem, setProblem] = useState("");
  const edited = useEdited(plan);
  // 저장 줄 — 앞 요청이 끝나야 다음이 그 revision 으로 간다. 화면이 내려간 뒤에는 저장만 마친다.
  const queue = useRef<Promise<void>>(Promise.resolve());
  const latest = useRef(plan);
  useEffect(() => {
    latest.current = plan;
  }, [plan]);
  const failed = useRef(new Map<string, string>());
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const confirmed = plan.status === "CONFIRMED";
  useCompactShell(!confirmed);
  const locked = !!busy;
  const month = Number(plan.target_month.slice(5, 7));
  const sections = plan.sections.filter((s) => s.visible);
  const cells = sections.flatMap((section) => section.cells.map((cell) => ({ section, cell })));
  const picked = confirmed ? null : (cells.find((c) => c.cell.item_id === selected) ?? null);
  const grids = plan.activity_grids ?? [];
  // 후보는 한 목록에 온다 — 실내 자유놀이 후보(section_key indoor_play)는 따로 쓴다.
  const allCandidates = plan.activity_candidates ?? [];
  const candidates = allCandidates.filter((c) => c.section_key !== "indoor_play");
  const indoorSelection = !!plan.indoor_play_selection;
  const gridCell = !!picked && grids.length > 0 && picked.section.section_key === "group_activity";
  // 후보형 실내 자유놀이 칸 — 목록에 넣고 · 빼고 · 순서를 바꾼다. AI 재생성은 없다(422).
  const indoorCell = !!picked && indoorSelection && picked.section.section_key === "indoor_play";

  const accept = (next: WeeklyPlan) => {
    latest.current = next;
    if (mounted.current) onPlan(next);
  };
  const conflict = () => {
    if (!mounted.current) return;
    setStatus("idle");
    onConflict();
  };
  const enqueue = (job: () => Promise<void>) => {
    const run = queue.current.then(job);
    queue.current = run.catch(() => {});
    return run;
  };

  function saveCell(itemId: string, text: string, replay?: "undo" | "redo") {
    const settled = (changed: boolean) => {
      failed.current.delete(itemId);
      if (!mounted.current) return;
      setLive((d) =>
        d[itemId] === text
          ? Object.fromEntries(Object.entries(d).filter(([k]) => k !== itemId))
          : d,
      );
      if (!changed) return;
      setStatus(failed.current.size ? "failed" : "saved");
      // 다시 저장해 모두 저장되면 실패 문구도 지운다.
      if (!failed.current.size) setMessage("");
    };
    // 같은지는 보내기 직전에 본다 — 앞 저장이 끝난 뒤의 서버 값과 비교해야 마지막 입력을 버리지 않는다.
    enqueue(async () => {
      const cur = latest.current;
      const now = cur.sections.flatMap((s) => s.cells).find((c) => c.item_id === itemId)?.value;
      if (now === text) return settled(failed.current.has(itemId));
      if (mounted.current) setStatus("saving");
      try {
        accept(await editWeeklyCell(cur.id, itemId, text, cur.revision));
        history.record(itemId, now ?? "", text, replay);
        // 되돌리기 · 다시 하기는 열린 입력창을 저장된 글로 다시 연다.
        if (replay && mounted.current) setBump((n) => n + 1);
        settled(true);
      } catch (e) {
        if (isSaveConflict(e)) return conflict();
        failed.current.set(itemId, text);
        if (!mounted.current) return;
        setStatus("failed");
        clearTimeout(flash.current);
        setMessage(
          "저장하지 못했어요. 쓴 글은 그대로 두었어요 — 「다시 저장」을 눌러 주세요. " +
            describe(e, ""),
        );
      }
    }).catch(() => {});
  }
  const retry = () => failed.current.forEach((text, itemId) => saveCell(itemId, text));

  /** 열린 입력창을 닫아 마지막 글을 줄에 넣고 줄이 빌 때까지 기다린다. 못 저장한 칸이 남으면 false. */
  async function flush() {
    (document.activeElement as HTMLElement | null)?.blur();
    let tail;
    do {
      tail = queue.current;
      await tail;
    } while (tail !== queue.current);
    if (!failed.current.size) return true;
    if (mounted.current) setProblem("저장하지 못한 칸이 있어요. 「다시 저장」한 뒤 해 주세요.");
    return false;
  }
  const unsent = status === "saving" || status === "failed" || Object.keys(live).length > 0;
  useEffect(() => {
    if (!unsent || confirmed) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [unsent, confirmed]);

  /** 열린 입력을 다 저장한 뒤 `job` 을 한다. */
  async function afterSaves(
    key: string,
    job: (cur: WeeklyPlan) => Promise<WeeklyPlan>,
    done: string,
  ) {
    if (busy) return;
    setBusy(key);
    setMessage("");
    setProblem("");
    try {
      if (!(await flush())) return;
      await enqueue(async () => accept(await job(latest.current)));
      setBump((b) => b + 1);
      setMessage(done);
      // 알림은 머리줄 저장 표시 자리에 잠깐 — 패널을 밀지 않고 저절로 사라진다.
      clearTimeout(flash.current);
      flash.current = setTimeout(() => mounted.current && setMessage(""), 4000);
    } catch (e) {
      if (isSaveConflict(e)) return conflict();
      setProblem(describe(e, "처리하지 못했어요."));
    } finally {
      if (mounted.current) setBusy("");
    }
  }
  const leave = async (move: () => void) => {
    if (busy) return;
    setBusy("move");
    try {
      if (await flush()) move();
    } finally {
      if (mounted.current) setBusy("");
    }
  };

  const put = (cellId: string, candidateId: string) =>
    afterSaves(
      "copy",
      async (cur) => {
        const next = await copyWeeklyActivity(cur.id, cellId, candidateId, cur.revision);
        const text = (p: WeeklyPlan) =>
          p.sections.flatMap((x) => x.cells).find((c) => c.item_id === cellId)?.value ?? "";
        // 넣기도 칸 글 변경이라 되돌리기로 되돌린다(월간과 같다).
        history.record(cellId, text(cur), text(next));
        return next;
      },
      "후보를 넣었어요.",
    );
  // 문서 칸에 놓은 후보 — 빈 후보나 이미 그 글인 칸이면 넣지 않고 그 칸만 고른다.
  const putDropped = (cellId: string, candidateId: string) => {
    const c = candidates.find((x) => x.cell.item_id === candidateId);
    const cell = cells.find((x) => x.cell.item_id === cellId)?.cell;
    if (!c || !cell) return;
    select(cellId);
    if (c.cell.value.trim() && shown(cell).trim() !== `[${c.activity_type}] ${c.name}`)
      void put(cellId, candidateId);
  };
  const split = (cellId: string, axis: "VERTICAL" | "HORIZONTAL") =>
    afterSaves(
      "split",
      (cur) => splitWeeklyActivityCell(cur.id, cellId, axis, cur.revision),
      "칸을 나눴어요.",
    );
  const indoorRows = (p: WeeklyPlan) =>
    p.sections.find((x) => x.section_key === "indoor_play")?.cells ?? [];
  // 뺀 칸은 되돌리기 · 다시 저장 목록에서도 지운다(없는 칸에 저장을 되풀이하지 않게).
  const dropped = (itemId: string, next: WeeklyPlan) => {
    history.forget(itemId);
    failed.current.delete(itemId);
    return next;
  };
  const remove = (cellId: string) =>
    afterSaves(
      "remove",
      async (cur) => dropped(cellId, await removeWeeklyActivityCell(cur.id, cellId, cur.revision)),
      "칸을 뺐어요.",
    );
  const addIndoor = (candidateId: string | null) =>
    afterSaves(
      "indoor",
      async (cur) => {
        const next = await addWeeklyIndoorPlay(cur.id, candidateId, cur.revision);
        // 직접 쓸 빈 줄은 「AI 후보」 목록에 빈칸으로 보인다 — 그 줄을 고르고 화면은 그대로(PM 2026-11-06).
        if (!candidateId) {
          const added = indoorRows(next).find(
            (c) => !indoorRows(cur).some((o) => o.item_id === c.item_id),
          );
          if (added) setSelected(added.item_id);
        }
        return next;
      },
      // 놀이를 넣은 것은 문서에 바로 보여 따로 알리지 않는다(PM 2026-11-06).
      candidateId ? "" : "직접 쓸 놀이 칸을 더했어요.",
    );
  const orderIndoor = (ids: string[]) =>
    afterSaves(
      "indoor",
      (cur) => orderWeeklyIndoorPlays(cur.id, ids, cur.revision),
      "순서를 바꿨어요.",
    );
  // 고른 줄을 빼면 옆 줄을 골라 「AI 후보」 화면을 그대로 둔다 — 「칸 편집」으로 넘어가지 않는다(PM 2026-11-06).
  const removeIndoor = (itemId: string) =>
    afterSaves(
      "indoor",
      async (cur) => {
        const next = dropped(itemId, await removeWeeklyIndoorPlay(cur.id, itemId, cur.revision));
        if (selected === itemId) {
          const at = indoorRows(cur).findIndex((c) => c.item_id === itemId);
          const left = indoorRows(next);
          setSelected(left[Math.min(at, left.length - 1)]?.item_id ?? null);
        }
        return next;
      },
      "",
    );
  const confirm = () =>
    afterSaves(
      "confirm",
      (cur) => confirmWeeklyPlan(cur.id, cur.revision),
      "확정했어요. 고치려면 문서 보관함의 「수정하기」를 눌러 주세요.",
    );

  const shown = (cell: WeeklyCell) => live[cell.item_id] ?? cell.value;
  // 확정 전에 알릴 빈 칸(입력 중 글 포함). 선생님이 직접 쓰는 칸(행사 등)은 빼고 본다.
  const blanks = cells.filter(({ cell }) => !cell.teacher_input && !shown(cell).trim());
  // 확정 확인은 한 번 — 남은 빈칸은 줄마다 세어 같은 상자에 보이고, 누르면 그 줄 첫 빈칸으로 간다.
  const blankRows = sections
    .map((s) => ({ s, empty: blanks.filter((b) => b.section === s) }))
    .filter((r) => r.empty.length)
    .map(({ s, empty }) => ({
      key: s.section_key,
      label: sectionName(s.section_key, s.label),
      count: empty.length,
      safety: s.section_key === "safety_education",
      onJump: () => select(empty[0].cell.item_id),
    }));
  /** 열린 입력창 글을 먼저 줄에 넣고, 그 저장까지 끝난 목록에서 한 걸음을 꺼내 다시 저장한다. */
  const through = (direction: "undo" | "redo") => {
    (document.activeElement as HTMLElement | null)?.blur();
    enqueue(async () => {
      const step = history.pop(direction);
      if (step) saveCell(step.itemId, step.text, direction);
    }).catch(() => {});
  };
  const dayOf = (cell: WeeklyCell) => (cell.day ? (DAY_NAMES[cell.day] ?? cell.day) : "");
  // 대·소집단활동 칸(후보가 있을 때) · 후보형 실내 자유놀이 칸은 「AI 후보」 탭부터, 나머지는 「칸 편집」.
  const select = (id: string) => {
    setSelected(id);
    setAsking("");
    const key = cells.find((c) => c.cell.item_id === id)?.section.section_key;
    setTab(
      (grids.length && candidates.length && key === "group_activity") ||
        (indoorSelection && key === "indoor_play")
        ? "ai"
        : "edit",
    );
  };
  const editing: Pick = { selected, onSelect: select };
  const still: Pick = { selected: null };
  const name = picked ? sectionName(picked.section.section_key, picked.section.label) : "";
  const where = picked ? (picked.cell.day ? `${dayOf(picked.cell)}요일 · ` : "") + name : "";
  const origin = picked ? originOf(picked.cell, edited) : "";

  // 넣은 후보의 설명 — 칸에는 「[종류] 이름」만 옮기고 설명은 읽기만 한다(ADR-054). 넣은 후보는 후보 목록에서
  // 숨기므로 「칸 편집」에 보인다(PM 2026-11-06). 글이 그대로면 이름으로, 고쳤으면 같은 근거를 가진 후보 하나로 찾는다.
  const sourceOf = (cell: WeeklyCell, key: string) => {
    const text = shown(cell).trim();
    const pool = allCandidates.filter(
      (c) => (c.section_key ?? "group_activity") === key && c.name.trim(),
    );
    const named = pool.find((c) =>
      [`[${c.activity_type}] - ${c.name}`, `[${c.activity_type}] ${c.name}`].includes(text),
    );
    if (named || !cell.evidence?.length) return named;
    const same = pool.filter(
      (c) => JSON.stringify(c.cell.evidence) === JSON.stringify(cell.evidence),
    );
    return same.length === 1 ? same[0] : undefined;
  };
  const source = picked ? sourceOf(picked.cell, picked.section.section_key) : undefined;
  const note = source ? source.description.trim() || source.cell.value.trim() : "";

  const editTab = (
    <div className="flex flex-col gap-4">
      {!picked && <p className="m-0 text-sm text-[#5c5243]">문서에서 고칠 칸을 눌러 주세요.</p>}
      {picked && (
        <>
          <div className="flex items-end justify-between gap-3">
            <div className="flex items-center gap-2">
              {/* 요일은 문서에서 칸을 눌러 고른다 — 「요일 고르기」 단추는 두지 않는다(월간 「주 고르기」를 뺀 것과 같다). */}
              <h2 className="m-0 text-[20px] font-bold leading-tight">{where}</h2>
              {origin && (
                <span className="rounded-full bg-[#efeae2] px-2 py-0.5 text-[11px] font-bold text-[#5c5243]">
                  {origin}
                </span>
              )}
            </div>
          </div>
          {/* 칸 이름은 위 제목에 한 번 — 입력창 이름표는 화면 읽기용으로만 남긴다(월간과 같은 입력창). */}
          <div
            className={`${workspace.field} [&_label]:sr-only [&_textarea]:min-h-[180px] [&_textarea]:text-base`}
          >
            <PlayCellEditor
              key={picked.cell.item_id + ":" + bump}
              id="weekly-cell"
              label={where}
              value={shown(picked.cell)}
              allowBlank
              readOnly={locked}
              onDraft={(text) => setLive((d) => ({ ...d, [picked.cell.item_id]: text }))}
              onSave={(text) => saveCell(picked.cell.item_id, text)}
              onRevert={() =>
                setLive((d) =>
                  Object.fromEntries(Object.entries(d).filter(([k]) => k !== picked.cell.item_id)),
                )
              }
            />
          </div>
          {picked.cell.teacher_input && (
            <p className="m-0 text-[13px] text-[#5c5243]">
              선생님이 직접 쓰는 칸이에요. AI가 쓰지 않아요 — 비워 두어도 확정할 수 있어요.
            </p>
          )}
          {note && (
            <section
              aria-labelledby="weekly-cell-note"
              className="flex flex-col gap-1.5 rounded-md bg-[#f7f4ee] p-3"
            >
              <h3 id="weekly-cell-note" className="m-0 text-[13px] font-bold text-ink">
                놀이 설명
              </h3>
              <p className="m-0 whitespace-pre-line text-[14px] leading-relaxed text-[#2b2826]">
                {note}
              </p>
            </section>
          )}
          {gridCell && (
            <div
              role="group"
              aria-label="칸 나누기"
              className="flex flex-wrap gap-2 border-t border-[#efeae2] pt-4"
            >
              <button
                type="button"
                className={BUTTON.outline}
                disabled={locked}
                onClick={() => void split(picked.cell.item_id, "VERTICAL")}
              >
                위아래로 나누기
              </button>
              <button
                type="button"
                className={BUTTON.outline}
                disabled={locked}
                onClick={() => void split(picked.cell.item_id, "HORIZONTAL")}
              >
                좌우로 나누기
              </button>
              <button
                type="button"
                className={BUTTON.quiet}
                // 흐린 까닭을 알린다 — 그날 칸이 하나뿐이면 뺄 수 없다.
                title={
                  picked.section.cells.filter((c) => c.day === picked.cell.day).length === 1
                    ? "나눈 칸만 뺄 수 있어요"
                    : undefined
                }
                disabled={
                  locked ||
                  picked.section.cells.filter((c) => c.day === picked.cell.day).length === 1
                }
                onClick={() => {
                  const id = picked.cell.item_id;
                  if ((live[id] ?? picked.cell.value)?.trim()) setDropAsk(id);
                  else void remove(id);
                }}
              >
                이 칸 빼기
              </button>
            </div>
          )}
          {dropAsk === picked.cell.item_id && (
            <PlayMonthlyConfirm
              message="이 칸의 글이 문서에서 빠지고, 되돌릴 수 없어요. 뺄까요?"
              yes="빼기"
              disabled={locked}
              onYes={() => {
                setDropAsk(null);
                void remove(picked.cell.item_id);
              }}
              onNo={() => setDropAsk(null)}
            />
          )}
        </>
      )}
    </div>
  );

  const aiTab = indoorCell ? (
    <WeeklyIndoorPlayPanel
      plan={plan}
      disabled={locked}
      selected={selected}
      shown={shown}
      onAdd={(id) => void addIndoor(id)}
      onOrder={(ids) => void orderIndoor(ids)}
      onRemove={(id) => void removeIndoor(id)}
      onWrite={(id) => {
        setSelected(id);
        setTab("edit");
      }}
    />
  ) : gridCell && candidates.length ? (
    <section aria-label="활동 후보" className="flex flex-col gap-4">
      <h2 className="m-0 text-[18px] font-bold leading-tight">{where} 칸에 넣을 활동</h2>
      <ul className="m-0 flex list-none flex-col gap-2 p-0">
        {/* 넣은 후보는 맨 위로 — 안전교육 후보와 같다. 서버는 「[종류] 이름」으로 복사한다(weekly_activities.copy). */}
        {[...candidates]
          .map((c) => ({
            c,
            here:
              !!c.cell.value.trim() &&
              shown(picked.cell).trim() === `[${c.activity_type}] ${c.name}`,
          }))
          .sort((a, b) => Number(b.here) - Number(a.here))
          .map(({ c, here }) => {
            const text = c.cell.value.trim();
            return (
              <li
                key={c.cell.item_id}
                // 카드를 끌어 문서의 다른 요일 칸에 놓아도 넣는다(월간 안전교육 후보와 같다).
                draggable={!locked && !!text}
                onDragStart={(event) =>
                  event.dataTransfer.setData("text/plain", WEEKLY_ACTIVITY_DRAG + c.cell.item_id)
                }
                className={`${CARD} ${!locked && text ? "cursor-grab active:cursor-grabbing" : ""} ${here ? PICKED : "border-[#e8e2d8]"}`}
              >
                {GRIP}
                <div className="min-w-0 flex-1 whitespace-pre-line text-[14px]">
                  <strong>[{c.activity_type}]</strong> {text || "(빈 후보)"}
                </div>
                <button
                  type="button"
                  aria-label={`${where}에 넣기: ${text || "빈 후보"}`}
                  className={PUT}
                  disabled={locked || !text || here}
                  onClick={() => void put(picked.cell.item_id, c.cell.item_id)}
                >
                  {here ? "넣음" : "넣기"}
                </button>
              </li>
            );
          })}
      </ul>
    </section>
  ) : (
    <p className="m-0 text-sm text-[#5c5243]">
      {grids.length && candidates.length && indoorSelection
        ? "대·소집단활동이나 이번 주 놀이 칸을 누르면 넣을 후보가 보여요."
        : grids.length && candidates.length
          ? "대·소집단활동 칸을 누르면 넣을 활동 후보가 보여요."
          : indoorSelection
            ? "이번 주 놀이 칸을 누르면 넣을 놀이 후보가 보여요."
            : "이 주에는 넣을 후보가 없어요. 「칸 편집」에서 고쳐 주세요."}
    </p>
  );

  const hasAi = (grids.length > 0 && candidates.length > 0) || indoorSelection;
  const aside = (
    <>
      {/* 넣을 후보가 없는 양식이면 탭 없이 칸 편집만 — 빈 「AI 후보」 탭을 두지 않는다. */}
      {hasAi && (
        <div
          role="tablist"
          aria-label="고치는 방법"
          className="flex gap-5 border-b border-[#efeae2] px-6 pt-2"
        >
          {(["ai", "edit"] as const).map((key) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={tab === key}
              className={tabClass(tab === key)}
              onClick={() => setTab(key)}
            >
              {key === "ai" ? "AI 후보" : "칸 편집"}
            </button>
          ))}
        </div>
      )}
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-6 py-5">
        {hasAi && tab === "ai" ? aiTab : editTab}
      </div>
    </>
  );

  const docOf = (at: Pick, scale?: number) => (
    <WeeklySheet
      title={`${plan.week_period.label} 주간놀이계획안`}
      sub={className}
      start={plan.week_period.start_date}
      end={plan.display_end_date}
      days={plan.operating_days}
      sections={plan.sections}
      grids={grids}
      at={at}
      shown={shown}
      scale={scale}
      onPut={at === editing && !locked && candidates.length ? putDropped : undefined}
    />
  );
  // 주 이름은 서버가 「11월 4주」처럼 달까지 붙여 준다.
  const title = `${plan.week_period.label} 주간계획안`;
  const back = (
    <button
      type="button"
      aria-label="주간계획안 만들기로"
      title="주간계획안 만들기로"
      disabled={locked}
      onClick={() => void leave(onBack)}
      className={BACK_BUTTON}
    >
      {BACK_ICON}
    </button>
  );
  const findings = findingLines(plan.verification.findings);

  // Ⓦ4 — 확정본 · 한글 내보내기 · 다음 주 만들기. 같은 주소라 링크 대신 화면을 바꾼다.
  if (confirmed)
    return (
      <PlanDone
        title={`${title}을 확정했어요`}
        docLabel="확정된 주간계획안"
        format="MONTHLY_THEME"
        pages={[docOf(still)]}
        download={(format) => downloadWeeklyHwpx(plan.id, format)}
        next={{
          href: `/plans/weekly?month=${month}`,
          label: "다음 주 계획안 만들기 →",
          hint: `${month}월 월간에서 아직 만들지 않은 주를 이어서 만들어요`,
          onClick: onBack,
        }}
        notes={
          <>
            {notice}
            {problem && (
              <p role="alert" className="m-0 text-[#8a2f2f]">
                {problem}
              </p>
            )}
            {message && <span role="status">{message}</span>}
            {plan.parent_changed && <span role="status">월간계획안이 바뀌었어요</span>}
          </>
        }
      />
    );

  return (
    <AnnualFrame
      title={title}
      format="MONTHLY_THEME"
      lead={back}
      // 저장 중 · 실패가 안내보다 먼저다.
      saved={status === "saving" || status === "failed" || !message ? SAVE_LABEL[status] : message}
      status={<PlanMemoNote plan={plan} />}
      notice={
        <div className="flex flex-col gap-1 text-sm text-[#5c5243]">
          {notice}
          {problem && (
            <p role="alert" className="m-0 text-[#8a2f2f]">
              {problem}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-3">
            {plan.parent_changed && <span role="status">월간계획안이 바뀌었어요</span>}
            {status === "failed" && <span role="status">{message}</span>}
            {status === "failed" && (
              <button type="button" className={BUTTON.outline} disabled={locked} onClick={retry}>
                다시 저장
              </button>
            )}
          </div>
          {findings.length > 0 && (
            <ul className="m-0 flex list-disc flex-col gap-0.5 pl-5 text-[13px]">
              {findings.map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          )}
        </div>
      }
      actions={
        <>
          <div className="relative">
            <button
              type="button"
              className={BUTTON.primary}
              disabled={locked}
              // 남은 빈칸은 확인 상자에 함께 보인다. 근거가 없어 비운 칸도 있어 그대로 확정도 된다
              // (꼭 필요한 칸 — 놀이 주제 등 — 은 서버가 확정을 거절한다).
              onClick={() => setAsking("confirm")}
            >
              {busy === "confirm" ? "확정하는 중…" : "확정하기"}
            </button>
            {asking === "confirm" && (
              <div className={POPOVER}>
                <PlayMonthlyConfirm
                  title="주간계획안을 확정할까요?"
                  message="확정하면 고칠 수 없어요. 고치려면 문서 보관함에서 「수정하기」를 눌러요."
                  yes="확정하기"
                  no="더 다듬기"
                  disabled={locked}
                  onYes={() => {
                    setAsking("");
                    void confirm();
                  }}
                  onNo={() => setAsking("")}
                >
                  <BlankRows rows={blankRows} lead={BLANK_LEAD} />
                </PlayMonthlyConfirm>
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
            disabled={locked}
            canUndo={history.canUndo}
            onUndo={() => through("undo")}
            canRedo={history.canRedo}
            onRedo={() => through("redo")}
          />
          {sheetZoom.tools}
          <span>
            <BigView pages={1} width={PAPER_WIDTH} render={() => docOf(still)} />
          </span>
        </div>
      }
    >
      <div ref={docBox}>{docOf(editing, sheetZoom.percent / 100)}</div>
    </AnnualFrame>
  );
}
