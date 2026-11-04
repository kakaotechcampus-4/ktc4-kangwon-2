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
  regenerateWeeklyCell,
  removeWeeklyActivityCell,
  removeWeeklyIndoorPlay,
  splitWeeklyActivityCell,
  unconfirmWeeklyPlan,
} from "@/lib/api/weekly";
import type { WeeklyCell, WeeklyPlan } from "@/lib/api/types";
import { DAY_NAMES, sectionName } from "@/lib/weekly/section-labels";
import PlayCellEditor from "@/components/plan-generator/PlayCellEditor";
import PlayMonthlyConfirm from "@/components/plan-generator/PlayMonthlyConfirm";
import UnconfirmButton from "@/components/plan-generator/UnconfirmButton";
import { CARD, PICKED, PUT } from "@/components/plan-generator/PlayMonthlySafetyPanel";
import AnnualFrame, {
  BACK_BUTTON,
  BACK_ICON,
  BigView,
  BUTTON,
  PlanDone,
  POPOVER,
  UNCONFIRM,
  tabClass,
  useSheetZoom,
} from "@/components/plan-generator/AnnualFrame";
import { PAPER_WIDTH, type Pick } from "@/components/plan-generator/PlayMonthlySheet";
import { useCompactShell } from "@/components/app/compact-shell";
import WeeklySheet from "./WeeklySheet";
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
  onDelete,
  onBack,
  className,
  notice,
}: {
  plan: WeeklyPlan;
  onPlan: (plan: WeeklyPlan) => void;
  /** 409 — 그 사이 바뀌었다. 다시 불러오는 일은 화면이 한다. */
  onConflict: () => void;
  onDelete: () => void;
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
  const [asking, setAsking] = useState<"" | "confirm" | "regenerate">("");
  const docBox = useRef<HTMLDivElement>(null);
  const sheetZoom = useSheetZoom(docBox, PAPER_WIDTH);
  const [bump, setBump] = useState(0);
  const [status, setStatus] = useState<keyof typeof SAVE_LABEL>("idle");
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
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
  const theme = cells.find((c) => c.section.section_key === "theme")?.cell;

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

  function saveCell(itemId: string, text: string) {
    const settled = (changed: boolean) => {
      failed.current.delete(itemId);
      if (!mounted.current) return;
      setLive((d) =>
        d[itemId] === text
          ? Object.fromEntries(Object.entries(d).filter(([k]) => k !== itemId))
          : d,
      );
      if (changed) setStatus(failed.current.size ? "failed" : "saved");
    };
    // 같은지는 보내기 직전에 본다 — 앞 저장이 끝난 뒤의 서버 값과 비교해야 마지막 입력을 버리지 않는다.
    enqueue(async () => {
      const cur = latest.current;
      const now = cur.sections.flatMap((s) => s.cells).find((c) => c.item_id === itemId)?.value;
      if (now === text) return settled(failed.current.has(itemId));
      if (mounted.current) setStatus("saving");
      try {
        accept(await editWeeklyCell(cur.id, itemId, text, cur.revision));
        settled(true);
      } catch (e) {
        if (isSaveConflict(e)) return conflict();
        failed.current.set(itemId, text);
        if (!mounted.current) return;
        setStatus("failed");
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

  const regenerate = (cell: WeeklyCell) =>
    afterSaves(
      cell.item_id,
      (cur) => regenerateWeeklyCell(cur.id, cell.item_id, cur.revision),
      "다시 만들었어요.",
    );
  const put = (cellId: string, candidateId: string) =>
    afterSaves(
      "copy",
      (cur) => copyWeeklyActivity(cur.id, cellId, candidateId, cur.revision),
      "후보를 넣었어요.",
    );
  const split = (cellId: string, axis: "VERTICAL" | "HORIZONTAL") =>
    afterSaves(
      "split",
      (cur) => splitWeeklyActivityCell(cur.id, cellId, axis, cur.revision),
      "칸을 나눴어요.",
    );
  const remove = (cellId: string) =>
    afterSaves(
      "remove",
      (cur) => removeWeeklyActivityCell(cur.id, cellId, cur.revision),
      "칸을 뺐어요.",
    );
  const addIndoor = (candidateId: string | null) =>
    afterSaves(
      "indoor",
      async (cur) => {
        const next = await addWeeklyIndoorPlay(cur.id, candidateId, cur.revision);
        // 직접 쓸 빈 줄은 「AI 후보」 목록에 안 보인다 — 바로 「칸 편집」에서 그 줄을 쓰게 한다.
        if (!candidateId) {
          const ids = (p: WeeklyPlan) =>
            p.sections.find((x) => x.section_key === "indoor_play")?.cells ?? [];
          const added = ids(next).find((c) => !ids(cur).some((o) => o.item_id === c.item_id));
          if (added) {
            setSelected(added.item_id);
            setTab("edit");
          }
        }
        return next;
      },
      candidateId ? "이번 주 놀이에 넣었어요." : "직접 쓸 놀이 칸을 더했어요.",
    );
  const orderIndoor = (ids: string[]) =>
    afterSaves(
      "indoor",
      (cur) => orderWeeklyIndoorPlays(cur.id, ids, cur.revision),
      "순서를 바꿨어요.",
    );
  const removeIndoor = (itemId: string) => {
    if (selected === itemId) setSelected(null);
    return afterSaves(
      "indoor",
      (cur) => removeWeeklyIndoorPlay(cur.id, itemId, cur.revision),
      "이번 주 놀이에서 뺐어요.",
    );
  };
  const confirm = () =>
    afterSaves(
      "confirm",
      (cur) => confirmWeeklyPlan(cur.id, cur.revision),
      "확정했어요. 이제 고칠 수 없어요.",
    );

  const shown = (cell: WeeklyCell) => live[cell.item_id] ?? cell.value;
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
  // 같은 요일에 칸이 여럿(나눈 칸)이면 「월 1」 · 「월 2」.
  const dayLabel = (section: (typeof sections)[number], cell: WeeklyCell) => {
    const same = section.cells.filter((c) => c.day === cell.day);
    return dayOf(cell) + (same.length > 1 ? ` ${same.indexOf(cell) + 1}` : "");
  };

  const editTab = (
    <div className="flex flex-col gap-4">
      {!picked && (
        <p className="m-0 text-sm text-[#5c5243]">문서의 칸을 누르면 여기서 고칠 수 있어요.</p>
      )}
      {picked && (
        <>
          <div className="flex items-end justify-between gap-3">
            <div className="flex items-center gap-2">
              <h2 className="m-0 text-lg font-bold">{name}</h2>
              {origin && (
                <span className="rounded-full bg-[#efeae2] px-2 py-0.5 text-[11px] font-bold text-[#5c5243]">
                  {origin}
                </span>
              )}
            </div>
            {/* 저장 상태를 입력창 가까이에도 — 읽어 주는 건 위 상태 줄(role=status) 하나. */}
            {status !== "idle" && (
              <span
                aria-hidden="true"
                className={`shrink-0 text-[13px] ${status === "failed" ? "font-bold text-[#a2492f]" : "text-[#8a8178]"}`}
              >
                {SAVE_LABEL[status]}
              </span>
            )}
          </div>
          {picked.section.repeat_by === "DAY" && (
            <div role="group" aria-label="요일 고르기" className="flex flex-wrap gap-1.5">
              {picked.section.cells.map((c) => (
                <button
                  key={c.item_id}
                  type="button"
                  aria-pressed={c.item_id === picked.cell.item_id}
                  className={`min-h-[36px] rounded-full border px-3.5 text-sm ${c.item_id === picked.cell.item_id ? "border-[#7053a0] bg-[#f6f1fb] font-bold text-[#5e4b96]" : "border-[#ddd6ca] bg-white text-[#5c5243]"}`}
                  onClick={() => select(c.item_id)}
                >
                  {dayLabel(picked.section, c)}
                </button>
              ))}
            </div>
          )}
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
              maxLength={Infinity}
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
          {picked.cell.state === "EMPTY_UNRESOLVED" && (
            <p className="m-0 text-[13px] text-[#5c5243]">
              근거가 없어 비워 두었어요. 직접 적어주세요.
            </p>
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
                disabled={
                  locked ||
                  picked.section.cells.filter((c) => c.day === picked.cell.day).length === 1
                }
                onClick={() => void remove(picked.cell.item_id)}
              >
                이 칸 빼기
              </button>
            </div>
          )}
          {/* RULE_ONLY(옛) 주간은 Core 가 바깥놀이만 다시 만든다. */}
          {!picked.cell.teacher_input &&
            !gridCell &&
            !indoorCell &&
            (plan.generation_mode !== "RULE_ONLY" ||
              picked.section.section_key === "outdoor_play") && (
              <div className="flex flex-col gap-2 border-t border-[#efeae2] pt-4">
                <button
                  type="button"
                  className={BUTTON.outline}
                  disabled={locked}
                  onClick={() => setAsking("regenerate")}
                >
                  {busy === picked.cell.item_id ? "다시 만드는 중…" : "AI로 이 칸 다시 만들기"}
                </button>
                {asking === "regenerate" && (
                  <PlayMonthlyConfirm
                    message="이 칸을 다시 만들면 지금 내용이 바뀌어요. 다시 만들까요?"
                    yes="다시 만들기"
                    disabled={locked}
                    onYes={() => {
                      setAsking("");
                      void regenerate(picked.cell);
                    }}
                    onNo={() => setAsking("")}
                  />
                )}
              </div>
            )}
        </>
      )}
      <div className="flex flex-col items-start gap-2 border-t border-[#efeae2] pt-3 text-sm">
        <button
          type="button"
          className={BUTTON.plain}
          disabled={locked}
          onClick={() => void leave(onDelete)}
        >
          지우고 다시 만들기
        </button>
      </div>
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
    />
  ) : gridCell && candidates.length ? (
    <section aria-label="활동 후보" className="flex flex-col gap-4">
      <h2 className="m-0 text-[15px] font-bold">{where} 칸에 넣을 활동</h2>
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
              <li key={c.cell.item_id} className={`${CARD} ${here ? PICKED : "border-[#e8e2d8]"}`}>
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

  const aside = (
    <>
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
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-6 py-5">
        {tab === "ai" ? aiTab : editTab}
      </div>
    </>
  );

  const docOf = (at: Pick, scale?: number) => (
    <WeeklySheet
      title={`${month}월 ${plan.week_period.label} 주간놀이계획안`}
      sub={className}
      start={plan.week_period.start_date}
      end={plan.display_end_date}
      days={plan.operating_days}
      sections={plan.sections}
      grids={grids}
      at={at}
      shown={shown}
      scale={scale}
    />
  );
  const title = `${month}월 ${plan.week_period.label} 주간계획안`;
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
  const findings = plan.verification.findings;

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
        unconfirm={
          <>
            {notice}
            {problem && (
              <p role="alert" className="m-0 text-[#8a2f2f]">
                {problem}
              </p>
            )}
            {message && <span role="status">{message}</span>}
            {plan.parent_changed && <span role="status">월간계획안이 바뀌었어요</span>}
            <UnconfirmButton
              message="확정을 풀면 다시 고칠 수 있어요."
              className={UNCONFIRM}
              run={() => unconfirmWeeklyPlan(latest.current.id, latest.current.revision)}
              onDone={accept}
              onConflict={conflict}
            />
          </>
        }
      />
    );

  return (
    <AnnualFrame
      title={title}
      format="MONTHLY_THEME"
      lead={back}
      status={
        <span className="flex items-center gap-3">
          <span role="status">{SAVE_LABEL[status]}</span>
          <PlanMemoNote plan={plan} />
        </span>
      }
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
            <span role="status">{message}</span>
            {status === "failed" && (
              <button type="button" className={BUTTON.outline} disabled={locked} onClick={retry}>
                다시 저장
              </button>
            )}
          </div>
          {findings.length > 0 && (
            <ul className="m-0 flex list-disc flex-col gap-0.5 pl-5 text-[13px]">
              {findings.map((f, i) => (
                <li key={i}>{f.message}</li>
              ))}
            </ul>
          )}
        </div>
      }
      actions={
        <div className="relative">
          <button
            type="button"
            className={BUTTON.primary}
            disabled={locked}
            onClick={() => {
              // 놀이 주제가 비면 서버가 확정을 받지 않는다 — 그 칸으로 데려간다.
              if (theme && !shown(theme).trim()) {
                select(theme.item_id);
                setProblem("놀이 주제를 적어야 확정할 수 있어요.");
              } else setAsking("confirm");
            }}
          >
            {busy === "confirm" ? "확정하는 중…" : "확정하기"}
          </button>
          {asking === "confirm" && (
            <div className={POPOVER}>
              <PlayMonthlyConfirm
                message="확정하면 확정을 풀기 전까지 고칠 수 없어요. 확정한 주간은 한글 파일로 내려받을 수 있어요."
                yes="확정하기"
                no="더 다듬기"
                disabled={locked}
                onYes={() => {
                  setAsking("");
                  void confirm();
                }}
                onNo={() => setAsking("")}
              />
            </div>
          )}
        </div>
      }
      aside={aside}
      docLabel={null}
      docHint={
        <div className="flex items-center gap-1">
          {sheetZoom.tools}
          <span className="ml-2">
            <BigView pages={1} render={() => docOf(still)} />
          </span>
        </div>
      }
    >
      <div ref={docBox}>{docOf(editing, sheetZoom.percent / 100)}</div>
    </AnnualFrame>
  );
}
