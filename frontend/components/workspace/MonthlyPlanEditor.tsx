"use client";

/**
 * 월간계획안(v1) 편집 — 놀이 월간과 같은 배치다. 문서에서 칸을 누르면 옆 패널에서 고친다.
 * 입력을 멈추거나 칸을 떠나면 그 칸만 저장한다(v1 칸 편집 API). 저장 · 재생성 · 확정은
 * 한 줄로 세워 앞 요청이 돌려준 revision 으로 보낸다. 409 면 덮어쓰지 않고 다시 불러온다.
 * 저장하지 못한 글은 되돌리지 않고 남겨 다시 저장하게 한다 — 그동안 확정 · 반 · 월 이동은 멈춘다.
 */

import { useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { ApiError } from "@/lib/api/client";
import {
  confirmMonthlyPlan,
  copyMonthlyDrill,
  downloadMonthlyHwpx,
  editMonthlyCell,
  placeMonthlySafety,
  regenerateMonthlyCell,
  unconfirmMonthlyPlan,
} from "@/lib/api/monthly";
import { isSaveConflict } from "@/lib/api/plans";
import type { MonthlyCell, MonthlyPlan } from "@/lib/api/types";
import { sectionName } from "@/lib/monthly/section-labels";
import PlayCellEditor from "@/components/plan-generator/PlayCellEditor";
import workspace from "./Workspace.module.css";
import PlayMonthlyDrillPanel from "@/components/plan-generator/PlayMonthlyDrillPanel";
import PlayMonthlySafetyPanel from "@/components/plan-generator/PlayMonthlySafetyPanel";
import UnconfirmButton from "@/components/plan-generator/UnconfirmButton";
import PlayMonthlyConfirm from "@/components/plan-generator/PlayMonthlyConfirm";
import AnnualFrame, {
  AsideStrip,
  BigView,
  BUTTON,
  PlanDone,
  UNCONFIRM,
  tabClass,
  useSheetZoom,
} from "@/components/plan-generator/AnnualFrame";
import {
  Band,
  Cell,
  HEAD,
  LINE,
  Paper,
  PAPER_WIDTH,
  WeekHead,
  period,
  safetyCellId,
} from "@/components/plan-generator/PlayMonthlySheet";
import { noticeSummary } from "@/components/plan-generator/PlayMonthlyView";
import { useCompactShell } from "@/components/app/compact-shell";
import { PlanMemoNote } from "@/components/plan-generator/PlanMemo";

const REGENERATABLE = new Set(["focus", "outdoor_play", "basic_habit", "goals"]);
const FINDINGS: Record<string, string> = {
  ACTIVITY_REFERENCE_NOT_VERIFIED:
    "수정한 내용과 기존 참고 활동의 연결을 자동으로 확인하지 못했어요. 교사가 내용을 확인해주세요.",
  ACTIVITY_FREE_TEXT_AGE_NOT_VERIFIED:
    "직접 작성한 바깥놀이 문장의 연령 적합성은 자동으로 확인하지 못했어요. 교사가 내용을 확인해주세요.",
  ACTIVITY_AGE_UNSUPPORTED:
    "우리 반 연령을 모두 지원하지 않는 참고 활동이 있어요. 활동 내용과 대상 연령을 확인해주세요.",
  // 안전교육 배치 검증(safety_placement). 서버 문구는 영어라 코드로 옮긴다.
  SAFETY_ANNUAL_HOURS_NOT_VERIFIED:
    "계획안에는 교육 시간이 없어 안전교육 연간 법정 시간은 자동으로 확인하지 못했어요. 실제 교육 시간은 따로 확인해주세요.",
  SAFETY_OFFICIAL_GROUNDING_MISSING:
    "법정 안전교육 칸의 공식 교육 내용 근거를 확인하지 못했어요. 안전교육 내용을 확인해주세요.",
  SAFETY_SUPPLEMENTAL_GROUNDING_INVALID:
    "생활안전 칸의 참고 근거를 확인하지 못했어요. 안전교육 내용을 확인해주세요.",
};
const SAVE_LABEL = { idle: "", saving: "저장 중…", saved: "저장됨", failed: "저장하지 못했어요" };

function describe(e: unknown, fallback: string): string {
  if (e instanceof ApiError) return e.message;
  return e instanceof Error ? e.message : fallback;
}

export default function MonthlyPlanEditor({
  plan,
  onPlan,
  onConflict,
  onDelete,
  className,
  notice,
  onBack,
  flushRef,
}: {
  plan: MonthlyPlan;
  onPlan: (plan: MonthlyPlan) => void;
  /** 409 — 그 사이 바뀌었다. 다시 불러오는 일은 화면이 한다. */
  onConflict: () => void;
  onDelete: () => void;
  /** 용지 오른쪽 위 반 이름. */
  className: string;
  /** 화면이 띄우는 안내(다시 불러옴 등). */
  notice?: ReactNode;
  /** 「←」 — 화면이 열린 입력을 저장한 뒤 만들기로 돌아간다. */
  onBack: () => void;
  /** 화면이 반 · 월을 옮기기 전에 부른다 — 열린 입력을 저장하고 끝까지 기다린다. 못 저장한 칸이 남으면 false. */
  flushRef?: RefObject<(() => Promise<boolean>) | null>;
}) {
  const [live, setLive] = useState<Record<string, string>>({});
  // 고른 칸. 안전교육 후보 줄은 주 주소(`safety:<주>`) — 같은 후보를 여러 주에 둘 수 있다.
  const [selected, setSelected] = useState<string | null>(null);
  const [tab, setTab] = useState<"ai" | "edit">("edit");
  const [asking, setAsking] = useState<"" | "confirm" | "regenerate">("");
  const docBox = useRef<HTMLDivElement>(null);
  const sheetZoom = useSheetZoom(docBox, PAPER_WIDTH);
  const [bumps, setBumps] = useState<Record<string, number>>({});
  const [status, setStatus] = useState<keyof typeof SAVE_LABEL>("idle");
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [problem, setProblem] = useState("");
  // 저장 줄 — 앞 요청이 끝나야 다음이 그 revision 으로 간다. 화면이 내려간 뒤에는 저장만 마친다.
  const queue = useRef<Promise<void>>(Promise.resolve());
  const latest = useRef(plan);
  useEffect(() => {
    latest.current = plan; // 다시 불러온 최신 계획안도 받는다.
  }, [plan]);
  // 저장하지 못한 칸과 그 글. 다시 저장하거나 서버 값과 같아질 때까지 남는다.
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
  const weeks = plan.weeks.filter((w) => w.active);
  const sections = plan.sections
    .filter((s) => s.visible && s.role === "CONTENT")
    .sort((a, b) => a.order - b.order);
  // 후보가 있으면 안전교육은 후보를 주에 두는 방식이다 — 주별 칸은 서버가 편집을 막고 늘 비어 있다.
  const candidateMode = plan.safety_candidates.length > 0;
  const cells = sections.flatMap((s) =>
    candidateMode && s.section_key === "safety_education"
      ? []
      : s.cells.map((cell) => ({ section: s, cell })),
  );
  // 안전교육 후보 줄: 그 주에 지금 놓인 후보 문장을 고친다(비우면 편집기가 닫힌다).
  const safety = sections.find((s) => s.section_key === "safety_education");
  const safetyWeek = candidateMode && selected?.startsWith("safety:") ? selected.slice(7) : null;
  const weekCandidate = safetyWeek
    ? plan.safety_weeks.find((w) => w.week_id === safetyWeek)?.candidate_item_id
    : null;
  const candidate = weekCandidate
    ? plan.safety_candidates.find((c) => c.cell.item_id === weekCandidate)
    : undefined;
  const picked = confirmed
    ? null
    : ((candidate && safety
        ? { section: safety, cell: candidate.cell }
        : cells.find((c) => c.cell.item_id === selected)) ?? null);
  const blank = cells.some(({ cell }) => !cell.value.trim());
  // 안전교육 미배치 안내는 후보를 두는 방식일 때만 뜻이 있다.
  const notices = candidateMode ? plan.notices : [];
  const summary = noticeSummary(notices);

  const accept = (next: MonthlyPlan) => {
    latest.current = next;
    if (mounted.current) onPlan(next);
  };
  const conflict = () => {
    if (!mounted.current) return;
    setStatus("idle");
    onConflict();
  };
  /** 줄 끝에 붙인다. 실패해도 줄은 이어진다. */
  const enqueue = (job: () => Promise<void>) => {
    const run = queue.current.then(job);
    queue.current = run.catch(() => {});
    return run;
  };

  function saveCell(itemId: string, text: string) {
    // 편집기는 다듬은 글을 저장한다.
    const drop = () =>
      setLive((d) =>
        d[itemId]?.trim() === text
          ? Object.fromEntries(Object.entries(d).filter(([k]) => k !== itemId))
          : d,
      );
    // 바뀐 것이 없으면(보낼 것이 없던 칸) 저장 표시는 그대로 둔다.
    const settled = (changed: boolean) => {
      failed.current.delete(itemId);
      if (!mounted.current) return;
      drop();
      if (changed) setStatus(failed.current.size ? "failed" : "saved");
    };
    // 같은지는 보내기 직전에 본다 — 앞 저장이 끝난 뒤의 서버 값과 비교해야 마지막 입력을 버리지 않는다.
    enqueue(async () => {
      const cur = latest.current;
      const now = [
        ...cur.sections.flatMap((s) => s.cells),
        ...cur.safety_candidates.map((c) => c.cell),
      ].find((c) => c.item_id === itemId)?.value;
      if (now === text) return settled(failed.current.has(itemId));
      if (mounted.current) setStatus("saving");
      try {
        accept(await editMonthlyCell(cur.id, itemId, text, cur.revision));
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
    // 기다리는 사이 줄에 붙은 저장까지 기다린다.
    let tail;
    do {
      tail = queue.current;
      await tail;
    } while (tail !== queue.current);
    if (!failed.current.size) return true;
    if (mounted.current) setProblem("저장하지 못한 칸이 있어요. 「다시 저장」한 뒤 해 주세요.");
    return false;
  }
  useEffect(() => {
    if (!flushRef) return;
    // 반 · 월 이동 — 기다리는 동안 입력창 · 단추를 잠가 새 글이 이동 뒤로 새지 않게 한다.
    flushRef.current = async () => {
      if (busy) return false;
      setBusy("move");
      try {
        return await flush();
      } finally {
        if (mounted.current) setBusy("");
      }
    };
    return () => {
      flushRef.current = null;
    };
  });
  // 입력 중 · 저장 중 · 저장 실패 글이 있으면 새로고침 · 닫기 전에 묻는다.
  const unsent = status === "saving" || status === "failed" || Object.keys(live).length > 0;
  useEffect(() => {
    if (!unsent || confirmed) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [unsent, confirmed]);

  /** 열린 입력창을 닫아 마지막 글을 줄에 넣고, 줄이 빌 때까지 기다린 뒤 `job` 을 한다. */
  async function afterSaves(
    key: string,
    job: (cur: MonthlyPlan) => Promise<MonthlyPlan>,
    done: string,
  ) {
    if (busy) return;
    setBusy(key);
    setMessage("");
    setProblem("");
    try {
      if (!(await flush())) return;
      const next = await enqueue(async () => accept(await job(latest.current))).then(
        () => latest.current,
      );
      setBumps((b) => ({ ...b, "*": (b["*"] ?? 0) + 1 }));
      setMessage(done);
      return next;
    } catch (e) {
      if (isSaveConflict(e)) return conflict();
      setProblem(describe(e, "처리하지 못했어요."));
    } finally {
      if (mounted.current) setBusy("");
    }
  }

  const regenerate = (cell: MonthlyCell) =>
    afterSaves(
      cell.item_id,
      (cur) => regenerateMonthlyCell(cur.id, cell.item_id, cur.revision),
      "다시 만들었어요.",
    );
  const place = (weekId: string, candidateItemId: string | null) =>
    afterSaves(
      "safety:" + weekId,
      (cur) => placeMonthlySafety(cur.id, weekId, candidateItemId, cur.revision),
      candidateItemId ? "안전교육을 두었어요." : "안전교육을 비웠어요.",
    );
  const copyDrill = (itemId: string) =>
    afterSaves(
      "drill",
      (cur) => copyMonthlyDrill(cur.id, itemId, cur.revision),
      "훈련 후보를 넣었어요.",
    );
  const confirm = () =>
    afterSaves(
      "confirm",
      (cur) => confirmMonthlyPlan(cur.id, cur.revision),
      "확정했어요. 이제 고칠 수 없어요.",
    );

  const weekLabel = (id: string | null) => weeks.find((w) => w.week_id === id)?.label ?? "";
  const shown = (cell: MonthlyCell) => live[cell.item_id] ?? cell.value;
  const drillCell = plan.sections.find((s) => s.section_key === "drill")?.cells[0];
  // 훈련 후보가 있으면 훈련 칸도 「AI 후보」 탭부터 (놀이 월간과 같다).
  const drillId = plan.drill_candidates.length > 0 ? drillCell?.item_id : undefined;
  const stamp = (id: string) => `${bumps["*"] ?? 0}:${bumps[id] ?? 0}`;
  // 안전교육 줄 · 훈련 칸은 「AI 후보」 탭부터, 나머지는 「칸 편집」.
  const select = (id: string) => {
    setSelected(id);
    setAsking("");
    setTab(id.startsWith("safety:") || id === drillId ? "ai" : "edit");
  };
  // 칸 고르기 — 다듬기 문서만. 확정본 · 크게 보기 창은 읽기 전용이다.
  type Pick = { selected: string | null; onSelect?: (id: string) => void };
  const editing: Pick = { selected, onSelect: select };
  const still: Pick = { selected: null };
  const where = safetyWeek
    ? `${weekLabel(safetyWeek)} · 안전교육`
    : picked
      ? (picked.cell.week_id ? `${weekLabel(picked.cell.week_id)} · ` : "") +
        sectionName(picked.section.section_key, picked.section.label)
      : "";
  // 「확인할 것」 — 안전교육을 안 둔 주. 누르면 그 주 안전교육 칸으로 간다.
  const goNotice = () => {
    const first = notices[0];
    if (!first) return;
    select(safetyCellId(first.week_id));
  };
  const findings = [
    ...new Map(plan.verification.findings.map((f) => [`${f.code}|${f.section_key}`, f])).values(),
  ];
  // 맨 앞 주별 아닌 칸(주제 · 목표 등)은 위 표, 나머지는 주별 표 — 순서는 양식 그대로.
  const head = sections.findIndex((s) => s.repeat_by === "WEEK");
  const top = head < 0 ? sections : sections.slice(0, head);
  const rest = head < 0 ? [] : sections.slice(head);
  const span = Math.max(weeks.length, 1);

  const editTab = (
    <div className="flex flex-col gap-4">
      {!where && (
        <p className="m-0 text-sm text-[#5c5243]">문서의 칸을 누르면 여기서 고칠 수 있어요.</p>
      )}
      {where && (
        <div className="flex items-end justify-between gap-3">
          <div className="flex flex-col gap-1">
            <span className="text-[13px] text-[#5c5243]">{where.split(" · ")[0]}</span>
            <h2 className="m-0 text-lg font-bold">{where.split(" · ")[1] ?? where}</h2>
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
      )}
      {picked && !candidate && picked.section.repeat_by === "WEEK" && (
        <div role="group" aria-label="주 고르기" className="flex flex-wrap gap-1.5">
          {picked.section.cells.map((c) => (
            <button
              key={c.item_id}
              type="button"
              aria-pressed={c.item_id === picked.cell.item_id}
              className={`min-h-[36px] rounded-full border px-3.5 text-sm ${c.item_id === picked.cell.item_id ? "border-[#7053a0] bg-[#f6f1fb] font-bold text-[#5e4b96]" : "border-[#ddd6ca] bg-white text-[#5c5243]"}`}
              onClick={() => select(c.item_id)}
            >
              {weekLabel(c.week_id)}
            </button>
          ))}
        </div>
      )}
      {safetyWeek && !candidate && (
        <p className="m-0 text-sm text-[#5c5243]">
          「AI 후보」에서 이 주에 안전교육을 넣으면 고칠 수 있어요.
        </p>
      )}
      {picked && (
        <>
          {/* 칸 이름은 위 제목에 한 번 — 입력창 이름표는 화면 읽기용으로만 남긴다. */}
          <div
            className={`${workspace.field} [&>label]:sr-only [&_textarea]:min-h-[180px] [&_textarea]:text-base`}
          >
            <PlayCellEditor
              key={picked.cell.item_id + ":" + stamp(picked.cell.item_id)}
              id="monthly-cell"
              label={candidate ? `안전교육 후보 · ${weekLabel(safetyWeek)}` : where}
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
          <p className="m-0 text-[13px] text-[#5c5243]">
            {candidate
              ? "이 문장을 둔 다른 주도 같이 바뀌어요."
              : "고치면 오른쪽 문서에 바로 반영돼요"}
          </p>
          {picked.cell.state === "EMPTY_UNRESOLVED" && (
            <p className="m-0 text-[13px] text-[#5c5243]">
              근거가 없어 비워 두었어요. 직접 적어주세요.
            </p>
          )}
          {picked.cell.evidence.length > 0 && (
            <p className="m-0 text-[12px] text-[#5c5243]">
              근거 ·{" "}
              {[
                ...new Set(
                  picked.cell.evidence.map((e) =>
                    e.source_type === "SAFETY_RULE"
                      ? "안전교육 기준"
                      : e.display_name || e.source_type,
                  ),
                ),
              ].join(" · ")}
            </p>
          )}
          {REGENERATABLE.has(picked.section.section_key) &&
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
        <button type="button" className={BUTTON.plain} disabled={locked} onClick={onDelete}>
          지우고 다시 만들기
        </button>
      </div>
    </div>
  );
  const aiTab =
    candidateMode && safetyWeek ? (
      <PlayMonthlySafetyPanel plan={plan} weekId={safetyWeek} onPlace={place} disabled={locked} />
    ) : drillCell && selected === drillId ? (
      <PlayMonthlyDrillPanel
        candidates={plan.drill_candidates}
        current={shown(drillCell)}
        onCopy={copyDrill}
        disabled={locked}
      />
    ) : (
      <p className="m-0 text-sm text-[#5c5243]">
        {candidateMode && drillId
          ? "안전교육이나 소방대피/재난대비 칸을 누르면 넣을 후보가 보여요."
          : candidateMode
            ? "안전교육 칸을 누르면 넣을 후보가 보여요."
            : drillId
              ? "소방대피/재난대비 칸을 누르면 넣을 후보가 보여요."
              : "이 양식에는 넣을 후보가 없어요. 「칸 편집」에서 고쳐 주세요."}
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
      <AsideStrip>{where ? `${where} 칸을 골랐어요` : "아직 고른 칸이 없어요"}</AsideStrip>
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-6 py-5">
        {tab === "ai" ? aiTab : editTab}
      </div>
    </>
  );
  const one = (section: (typeof sections)[number], at: Pick) => {
    const cell = section.cells[0];
    return cell && <Cell {...at} id={cell.item_id} value={shown(cell)} />;
  };
  const row = (section: (typeof sections)[number], at: Pick) => {
    const byWeek = new Map(section.cells.map((c) => [c.week_id, c]));
    const safetyRow = candidateMode && section.section_key === "safety_education";
    return (
      <tr key={section.section_key}>
        <th scope="row" className={`${LINE} ${HEAD} px-1 py-1`}>
          {sectionName(section.section_key, section.label)}
        </th>
        {section.repeat_by !== "WEEK" ? (
          <td colSpan={span} className={`${LINE} align-top`}>
            {one(section, at)}
          </td>
        ) : (
          weeks.map((w) => {
            if (safetyRow) {
              // 그 주에 둔 후보의 표시값(서버가 붙인 머리말 포함) — 입력 중 글은 저장 응답 뒤에 반영된다. 비어 있어도 칸은 그린다.
              const sw = plan.safety_weeks.find((x) => x.week_id === w.week_id);
              return (
                <td key={w.week_id} className={`${LINE} text-center align-middle`}>
                  <Cell {...at} id={safetyCellId(w.week_id)} value={sw?.display_value ?? ""} />
                </td>
              );
            }
            const cell = byWeek.get(w.week_id);
            return (
              <td key={w.week_id} className={`${LINE} text-center align-middle`}>
                {cell && <Cell {...at} id={cell.item_id} value={shown(cell)} />}
              </td>
            );
          })
        )}
      </tr>
    );
  };
  const back = (
    <button
      type="button"
      aria-label="월간계획안 만들기로"
      disabled={locked}
      onClick={onBack}
      className="flex h-11 w-11 items-center justify-center rounded-xl text-lg text-[#5c5243] hover:bg-white disabled:opacity-40"
    >
      ←
    </button>
  );
  const askConfirm =
    "확정하면 확정을 풀기 전까지 고칠 수 없어요. 이 내용으로 주간계획안을 만들게 돼요." +
    (notices.length ? ` 확인할 것 ${notices.length}개가 남았어요.` : "");

  const docOf = (at: Pick, scale?: number) => (
    <Paper
      label="월간계획안 미리보기"
      title={`${plan.month}월 월간계획안`}
      sub={className}
      scale={scale}
    >
      <table className="w-full table-fixed border-collapse">
        <colgroup>
          <col style={{ width: "17%" }} />
          <col />
        </colgroup>
        <tbody>
          <tr>
            <th scope="row" className={`${LINE} ${HEAD} px-1 py-1`}>
              예상 기간
            </th>
            <td className={`${LINE} px-1.5 py-1`}>{period(weeks)}</td>
          </tr>
          {top.map((section) => (
            <tr key={section.section_key}>
              <th scope="row" className={`${LINE} ${HEAD} px-1 py-1`}>
                {sectionName(section.section_key, section.label)}
              </th>
              <td className={`${LINE} align-top`}>{one(section, at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {rest.length > 0 && (
        <>
          <div className="mt-2" />
          <Band>주별 놀이 계획</Band>
          <table className="w-full table-fixed border-collapse">
            <colgroup>
              <col style={{ width: "17%" }} />
              {weeks.map((w) => (
                <col key={w.week_id} />
              ))}
            </colgroup>
            <thead>
              <tr>
                <th scope="col" className={`${LINE} ${HEAD}`}>
                  구분
                </th>
                {weeks.map((w, i) => (
                  <WeekHead key={w.week_id} index={i} week={w} />
                ))}
              </tr>
            </thead>
            <tbody>{rest.map((section) => row(section, at))}</tbody>
          </table>
        </>
      )}
    </Paper>
  );
  // Ⓜ4 — 확정본 · 한글 내보내기 · 주간 만들기로.
  if (confirmed)
    return (
      <PlanDone
        title={`${plan.month}월 월간계획안을 확정했어요`}
        docLabel="확정된 월간계획안"
        format="MONTHLY_THEME"
        pages={[docOf(still)]}
        download={() => downloadMonthlyHwpx(plan.id)}
        next={{
          href: "/plans/weekly",
          label: "주간계획안 만들기 →",
          hint: `${plan.month}월 1주부터 이 월간을 바탕으로 만들어요`,
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
            <UnconfirmButton
              message="확정을 풀면 다시 고칠 수 있어요. 이미 만든 주간계획안은 그대로예요."
              className={UNCONFIRM}
              run={() => unconfirmMonthlyPlan(latest.current.id, latest.current.revision)}
              onDone={accept}
              onConflict={conflict}
            />
          </>
        }
      />
    );
  return (
    <AnnualFrame
      title={`${plan.month}월 월간계획안`}
      format="MONTHLY_THEME"
      lead={back}
      status={
        <span className="flex items-center gap-3">
          <span role="status">작성 중{status !== "idle" && ` · ${SAVE_LABEL[status]}`}</span>
          {plan.parent.theme && (
            <span className="text-[#8a8178]">연간 주제 · {plan.parent.theme}</span>
          )}
          <PlanMemoNote plan={plan} />
          {blank && (
            <span role="status" title="확정을 막지 않아요" className="text-[#8a8178]">
              빈 칸 있음
            </span>
          )}
          {notices.length > 0 && (
            <button
              type="button"
              title={summary}
              onClick={goNotice}
              className="min-h-[32px] rounded-full bg-[#fdecea] px-3 text-[13px] font-bold text-[#b3261e]"
            >
              ! 확인할 것 {notices.length}
            </button>
          )}
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
            {plan.parent_changed && <span role="status">상위 계획안이 바뀌었어요</span>}
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
                <li key={i}>{FINDINGS[f.code] ?? f.message}</li>
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
              onClick={() => setAsking("confirm")}
            >
              {busy === "confirm" ? "확정하는 중…" : "확정하기"}
            </button>
            {asking === "confirm" && (
              <div className="absolute right-0 top-full z-20 mt-2 w-[380px]">
                <PlayMonthlyConfirm
                  message={askConfirm}
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
        </>
      }
      aside={aside}
      docLabel="월별 주제형 월간 양식"
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
