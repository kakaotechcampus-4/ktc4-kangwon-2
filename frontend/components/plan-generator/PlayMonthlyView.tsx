"use client";
import { useEffect, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { useCompactShell } from "@/components/app/compact-shell";
import workspace from "@/components/workspace/Workspace.module.css";
import { ApiError } from "@/lib/api/client";
import { downloadPlayMonthlyHwpx, getPlayMonthly } from "@/lib/api/playMonthly";
import type { PlayMonthlyPlan } from "@/lib/api/types";
import { usePlayMonthlySave } from "@/lib/hooks/use-play-monthly-save";
import {
  cellValue,
  drillTarget,
  overlayCells,
  removal,
  type PlaySection,
} from "@/lib/plan-generator/playMonthlyQueue";
import {
  CELL_MIN_WIDTH,
  MAX_DEPTH,
  RATIO_RANGE,
  leaves,
  locate,
  narrowest,
  splitLeaf,
  timetablePlace,
  tooNarrow,
  withRatio,
} from "@/lib/plan-generator/playMonthlyTimetable";
import PlayCellEditor from "./PlayCellEditor";
import PlayPickBoard from "@/components/plan-ui/PlayPickBoard";
import PlayMonthlyActivityPanel, {
  SECTION_LABEL,
  sectionCandidates,
} from "./PlayMonthlyActivityPanel";
import DraftSave from "@/components/plan-ui/DraftSave";
import PlayMonthlyConfirm, { BLANK_LEAD, BlankRows, PickCellHint } from "./PlayMonthlyConfirm";
import PlayMonthlyConfirmBar from "./PlayMonthlyConfirmBar";
import PlayMonthlyDrillPanel from "./PlayMonthlyDrillPanel";
import PlayMonthlyRowRemove from "./PlayMonthlyRowRemove";
import PlayMonthlySafetyPanel from "./PlayMonthlySafetyPanel";
import PlayMonthlySheet, { PAPER_WIDTH } from "./PlayMonthlySheet";
import AnnualFrame, {
  BACK_BUTTON,
  BACK_ICON,
  BigView,
  BUTTON,
  PlanDone,
  pageClass,
  tabClass,
  UndoRedo,
  useSheetZoom,
} from "./AnnualFrame";
import { PlanMemoNote } from "./PlanMemo";

const STALE_NOTICE = "다른 곳에서 바뀌었어요. 최신 내용을 다시 불러왔어요.";
const PARTIAL_NOTICE =
  "뺀 칸을 되살리다 멈췄어요. 칸은 다시 나뉘었지만 글이 다 돌아오지 않았을 수 있어요 — 확인해 주세요.";
const SAVE_LABEL = { idle: "", saving: "저장 중…", saved: "저장됨", failed: "저장하지 못했어요" };
const INPUT_LABELS: Record<string, string> = {
  fire_disaster_drill: "소방대피/재난대비",
  class_notice: "안내사항",
  class_birthdays: "우리반 생일",
  home_connection: "가정연계",
};

/** 고칠 수 있는 칸의 이름표. 놀이 행의 「설명」은 문서에 안 나와 행 이름을 누르면 패널에 함께 뜬다. */
export function cellLabels(plan: PlayMonthlyPlan) {
  const labels: Record<string, string> = {
    [plan.display.title.item_id]: "제목",
    [plan.display.age.item_id]: "연령",
    [plan.display.class_name.item_id]: "반 이름",
    [plan.display.period.item_id]: "예상 기간",
    [plan.theme.item_id]: "놀이 주제",
    [plan.rationale.item_id]: "주제선정이유",
    [plan.direction.item_id]: "예상되는 놀이 방향",
    [plan.health.cell.item_id]: "건강",
    [plan.nutrition.cell.item_id]: "영양",
  };
  for (const row of [...plan.together, ...plan.free_play]) {
    labels[row.name.item_id] = "놀이 행 이름";
    labels[row.description.item_id] = "놀이 행 설명";
  }
  const weekLabel = (id: string) => plan.weeks.find((w) => w.week_id === id)?.label ?? "";
  for (const h of plan.habits) labels[h.cell.item_id] = `기본생활습관 · ${weekLabel(h.week_id)}`;
  for (const c of plan.safety_candidates) labels[c.cell.item_id] = "안전교육 후보";
  for (const d of plan.drill_candidates) labels[d.cell.item_id] = `훈련 후보 · ${d.label}`;
  for (const t of plan.teacher_inputs) labels[t.cell.item_id] = INPUT_LABELS[t.key] ?? t.key;
  for (const c of [...plan.specialized_timetable, ...plan.special_activity.flatMap(leaves)])
    labels[c.item_id] = timetablePlace(plan, c.item_id)!;
  return labels;
}

export default function PlayMonthlyView({ id }: { id: number }) {
  const valid = Number.isSafeInteger(id) && id > 0;
  const [loaded, setLoaded] = useState<{
    key: string;
    plan: PlayMonthlyPlan | null;
    error: string;
    /** 다른 곳에서 바뀌어 다시 불러왔을 때의 안내와, 화면을 새로 그리게 하는 번호. */
    notice?: string;
    version?: number;
  } | null>(null);
  const [retry, setRetry] = useState(0);
  const key = id + ":" + retry;
  useEffect(() => {
    if (!valid) return;
    const controller = new AbortController();
    getPlayMonthly(id, controller.signal)
      .then((plan) => {
        if (!controller.signal.aborted) setLoaded({ key, plan, error: "" });
      })
      .catch((e) => {
        if (controller.signal.aborted) return;
        // 404 · 409(기존 월간 id) · 그 밖 오류는 서버 문구 그대로 안내한다.
        const error = e instanceof ApiError ? e.message : "계획안을 불러오지 못했어요.";
        setLoaded({ key, plan: null, error });
      });
    return () => controller.abort();
  }, [id, key, valid]);

  // 저장이 409 로 막히면 최신 계획안으로 바꾼다. 요청이 겹치면 마지막 응답만 반영한다.
  const lastReload = useRef(0);
  function reloadAfterConflict(partial = false) {
    const mine = ++lastReload.current;
    const apply = (next: (cur: typeof loaded) => typeof loaded) =>
      mine === lastReload.current && setLoaded(next);
    getPlayMonthly(id).then(
      (fresh) =>
        apply((cur) => ({
          key,
          plan: fresh,
          error: "",
          notice: partial ? PARTIAL_NOTICE : STALE_NOTICE,
          version: (cur?.version ?? 0) + 1,
        })),
      () =>
        apply(
          (cur) => cur && { ...cur, notice: "최신 내용을 불러오지 못했어요. 새로고침해 주세요." },
        ),
    );
  }
  const current = loaded?.key === key ? loaded : null;
  const plan = current?.plan ?? null;
  const error = valid ? (current?.error ?? "") : "올바른 계획안 주소가 아닙니다.";
  const box = (body: ReactNode) => (
    <main className="flex w-full flex-col gap-3 px-7 pb-6 pt-5 text-[#2b2826]">{body}</main>
  );
  if (error)
    return box(
      <>
        <p role="alert" className="m-0">
          {error}
        </p>
        {valid && (
          <button
            type="button"
            className={BUTTON.outline + " self-start"}
            onClick={() => setRetry((v) => v + 1)}
          >
            다시 불러오기
          </button>
        )}
      </>,
    );
  if (!plan)
    return box(
      <p role="status" className="m-0">
        계획안을 불러오고 있어요.
      </p>,
    );
  return (
    <PlayMonthlyBody
      key={key + ":" + (current?.version ?? 0)}
      initial={plan}
      notice={current?.notice}
      onConflict={reloadAfterConflict}
    />
  );
}

const CIRCLED = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩"];
const ORDINAL = ["첫", "두", "세", "네", "다섯", "여섯", "일곱", "여덟", "아홉", "열"];

/** 왼쪽 띠 · 머리에 쓰는 「어느 칸」. 안전교육 줄은 주 주소(`safety:<주>`)로 온다. */
export function placeOf(plan: PlayMonthlyPlan, id: string) {
  const week = (weekId: string) => plan.weeks.find((w) => w.week_id === weekId)?.label ?? "";
  if (id.startsWith("safety:")) return `${week(id.slice(7))} · 안전교육`;
  const together = plan.together.findIndex((r) => r.name.item_id === id);
  if (together >= 0) return `함께 하는 활동 ${CIRCLED[together] ?? together + 1}`;
  const free = plan.free_play.findIndex((r) => r.name.item_id === id);
  if (free >= 0) return `유아 예상 자유놀이 ${free + 1}`;
  return cellLabels(plan)[id] ?? "";
}

function PlayMonthlyBody({
  initial,
  notice,
  onConflict,
}: {
  initial: PlayMonthlyPlan;
  notice?: string;
  onConflict: (partial?: boolean) => void;
}) {
  const [plan, setPlan] = useState(initial);
  // 입력 중 글(문서가 바로 따라간다) · 고른 칸 · 입력창을 다시 열 번호(되돌리기 · 거절) · 안내.
  const [live, setLive] = useState<Record<string, string>>({});
  const [selected, setSelected] = useState<string | null>(null);
  const [tab, setTab] = useState<"ai" | "edit">("edit");
  // 고를 수가 모자란 채로 열면 놀이 중심형 연간 「놀이 고르기」처럼 활동 고르기 판부터(ADR-065).
  const [choosing, setChoosing] = useState<PlaySection | null>(() =>
    initial.status === "DRAFT" && initial.activity_pick != null
      ? ((["together", "free_play"] as const).find(
          (s) => initial[s].length < initial.activity_pick!,
        ) ?? null)
      : null,
  );
  const [focus, setFocus] = useState<string | null>(null);
  const docBox = useRef<HTMLDivElement>(null);
  const sheetZoom = useSheetZoom(docBox, PAPER_WIDTH);
  // 입력창을 다시 여는 번호 — "*" 는 전부(되돌리기 · 다시 하기), 칸 id 는 그 칸만(거절). 화면 번호(state)와 핸들러가 읽는 ref 를 같이 올린다.
  const [bumps, setBumps] = useState<Record<string, number>>({});
  const bumpsRef = useRef(bumps);
  const stamp = (all: Record<string, number>, id: string) => `${all["*"] ?? 0}:${all[id] ?? 0}`;
  const bump = (id = "*") => {
    bumpsRef.current = { ...bumpsRef.current, [id]: (bumpsRef.current[id] ?? 0) + 1 };
    setBumps(bumpsRef.current);
  };
  const [message, setMessage] = useState("");
  // 409 로 저장이 멈추면 최신 계획안으로 바뀔 때까지 구조 편집을 잠근다.
  const [stopped, setStopped] = useState(false);
  const clearLive = (id: string) =>
    setLive((drafts) => Object.fromEntries(Object.entries(drafts).filter(([k]) => k !== id)));
  const save = usePlayMonthlySave(
    plan,
    setPlan,
    (partial) => {
      setStopped(true);
      onConflict(partial);
    },
    (itemId, kind) => {
      if (itemId) {
        clearLive(itemId);
        bump(itemId);
      }
      setMessage(
        kind === "cell"
          ? "저장하지 못한 칸은 원래대로 되돌렸어요."
          : "저장하지 못한 변경은 원래대로 되돌렸어요.",
      );
    },
    Object.keys(live).length > 0,
  );
  const confirmed = plan.status === "CONFIRMED";
  useCompactShell(!confirmed);
  // 확정 시작(freeze)부터 끝(unfreeze)까지도 패널 · 행 빼기를 잠근다.
  const [frozen, setFrozen] = useState(false);
  // 나누기 · 되살리기는 응답이 와야 새 칸이 생겨 그동안 편집을 잠근다.
  const locked = stopped || frozen || save.structuring;
  const shown = overlayCells(plan, live);
  const labels = cellLabels(plan);
  // 고른 칸이 빼기 · 되돌리기로 사라졌으면 고름을 푼다.
  if (selected && !selected.startsWith("safety:") && !labels[selected]) setSelected(null);
  const [asking, setAsking] = useState(false);
  if (asking && locked) setAsking(false);
  const slot = selected ? locate(plan.special_activity, selected) : null;
  const removeSlot = () => {
    const parent = slot!.path.at(-2)!;
    const sibling = parent.children.find((c) => c.cell?.item_id !== selected)!;
    setAsking(false);
    if (save.removeCell(selected!)) setSelected(leaves(sibling)[0].item_id);
  };
  // 글이 있거나 되돌릴 수 없으면(형제가 나뉜 묶음) 한 번 묻는다.
  const askRemoveSlot = () => {
    const text = cellValue(plan, selected!)?.trim();
    if (text || removal(plan, selected!) === null) setAsking(true);
    else removeSlot();
  };
  // 안전교육 칸 끌어 옮기기 — 두 주의 배치를 맞바꾼다(빈 주로 옮기면 원래 주는 빈다). 되돌리기는 두 번.
  const moveSafety = (from: string, to: string) => {
    const at = (weekId: string) =>
      plan.safety_weeks.find((w) => w.week_id === weekId)?.candidate_item_id ?? null;
    const [moved, other] = [at(from), at(to)];
    save.placeSafety(to, moved);
    save.placeSafety(from, other);
  };
  // 기본생활습관 칸 끌어 옮기기 — 두 주의 칸을 통째로 맞바꾼다. 되돌리기는 한 번.
  const moveHabit = (from: string, to: string) => {
    const ids = plan.habits.map((h) => h.cell.item_id);
    const [a, b] = [from, to].map((w) => plan.habits.findIndex((h) => h.week_id === w));
    if (a < 0 || b < 0) return;
    [ids[a], ids[b]] = [ids[b], ids[a]];
    save.orderHabits(ids);
  };
  // 행 끌어 옮기기 · 위로 · 아래로 — 같은 목록 안에서 끈 행을 놓은 행 자리에 넣는다. 되돌리기는 한 번.
  const moveRow = (section: PlaySection, from: string, to: string) => {
    const ids = plan[section].map((r) => r.activity_id).filter((id) => id !== from);
    ids.splice(
      plan[section].findIndex((r) => r.activity_id === to),
      0,
      from,
    );
    save.orderActivities(section, ids);
  };
  const through = (direction: "undo" | "redo") => {
    if (!save[direction]()) return;
    setLive({});
    bump();
    setMessage("");
  };
  const copyDrill = (candidateId: string) => {
    if (!save.copyDrill(candidateId)) return;
    const target = drillTarget(plan);
    if (target) {
      clearLive(target);
      bump(target);
    }
  };
  const drillId = drillTarget(plan);
  // 「AI 후보에서 고르기」 칸은 고르기 판을 연다. 안전교육 줄 · 소방대피 칸은 「AI 후보」 탭부터, 나머지는 「칸 편집」.
  const select = (id: string) => {
    if (id.startsWith("pick:")) return setChoosing(id.slice(5) as PlaySection);
    setSelected(id);
    setTab(id.startsWith("safety:") || id === drillId ? "ai" : "edit");
  };
  const safetyWeek = selected?.startsWith("safety:") ? selected.slice(7) : null;
  const weekCandidate = safetyWeek
    ? (plan.safety_weeks.find((w) => w.week_id === safetyWeek)?.candidate_item_id ?? null)
    : null;
  const rows = [...plan.together, ...plan.free_play];
  const row = rows.find((r) => r.name.item_id === selected);
  // AI 후보에서 고르는 계획안(ADR-065): 그 목록의 행을 고르면 「AI 후보」에 그 목록 후보가 뜬다.
  const picking = plan.activity_pick != null;
  const pickSection: PlaySection | null =
    picking && row ? (plan.together.includes(row) ? "together" : "free_play") : null;
  // AI 후보 행은 빼면 후보로 돌아간다 — 「AI 후보」의 [빼기]를 쓰고, 되돌릴 수 없는 「이 활동 빼기」는 교사가 더한 행만.
  const candidateRow = !!row && (plan.activity_candidates ?? []).includes(row.activity_id);
  const short = picking
    ? (["together", "free_play"] as const).filter((s) => plan[s].length !== plan.activity_pick)
    : [];
  // 안전교육 줄은 그 주에 둔 후보 문장을 고친다(같은 후보를 둔 다른 주도 같이 바뀐다).
  const target = safetyWeek ? weekCandidate : selected;
  const editing = !confirmed && target && labels[target] ? [target] : [];
  if (row && !confirmed) editing.push(row.description.item_id);
  // 문서에서 「+ 채우기」로 보이는 칸(선생님 입력 칸 · 시간표는 뺀다)을 묶음별로 센다.
  const empty = (id: string) => {
    if (!id.startsWith("safety:")) return !cellValue(shown, id)?.trim();
    const c = plan.safety_weeks.find((w) => w.week_id === id.slice(7))?.candidate_item_id;
    return !c || !cellValue(shown, c)?.trim();
  };
  const groups = (
    [
      ["safety", "안전교육", plan.safety_weeks.map((w) => "safety:" + w.week_id)],
      ["theme", "놀이 주제", [plan.theme.item_id]],
      ["rationale", "주제선정이유", [plan.rationale.item_id]],
      ["together", "함께 하는 활동", plan.together.map((r) => r.name.item_id)],
      ["free_play", "유아 예상 자유놀이", plan.free_play.map((r) => r.name.item_id)],
      ["habits", "기본생활습관", plan.habits.map((h) => h.cell.item_id)],
      ["health", "건강", [plan.health.cell.item_id]],
      ["nutrition", "영양", [plan.nutrition.cell.item_id]],
    ] as const
  ).map(([key, label, ids]) => ({ key, label, ids: ids.filter(empty) }));
  const blankRows = [
    // 고를 수가 모자란 목록 — 빈칸과 달리 이대로는 확정할 수 없다.
    ...short.map((s) => ({
      key: "pick:" + s,
      label: `${SECTION_LABEL[s]} · AI 후보 고르기`,
      count: Math.max(0, plan.activity_pick! - plan[s].length),
      onJump: () => select("pick:" + s),
    })),
    ...groups
      .filter((g) => g.ids.length)
      .map(({ key, label, ids }) => ({
        key,
        label,
        count: ids.length,
        safety: key === "safety",
        onJump: () => select(ids[0]),
      })),
  ];
  const parentPlay =
    row?.parent_item_id &&
    plan.parent.plays.find((p) => p.play_name_item_id === row.parent_item_id);

  const editTab = (
    <div className="flex flex-col gap-4">
      {!selected && <PickCellHint>문서에서 고칠 칸을 눌러 주세요.</PickCellHint>}
      {selected && (
        <h2 className="m-0 text-[20px] font-bold leading-tight">
          {/* 놀이 행은 문서 순서(함께 하는 활동 위→아래, 그다음 자유놀이)로 「n 번째 칸」. */}
          {row
            ? `${ORDINAL[rows.indexOf(row)] ?? rows.indexOf(row) + 1} 번째 칸`
            : placeOf(plan, selected)}
        </h2>
      )}
      {parentPlay && (
        <p className="m-0 rounded-lg bg-[#f7f4ee] px-3 py-2 text-[13px] text-[#5c5243]">
          연간 놀이 ‘{parentPlay.play_name}’에서 이어졌어요
          {parentPlay.emphasized && " · 이번 달에 더 집중해요"}
        </p>
      )}
      {safetyWeek && !weekCandidate && (
        <p className="m-0 text-sm text-[#5c5243]">
          「AI 후보」에서 이 주에 안전교육을 넣으면 고칠 수 있어요.
        </p>
      )}
      {editing.map((itemId, index) => {
        const mine = stamp(bumps, itemId);
        return (
          // 칸 하나면 이름은 위 제목에 한 번 — 입력창 이름표는 화면 읽기용으로만.
          <div
            key={itemId}
            className={`${workspace.field} ${editing.length === 1 ? "[&_label]:sr-only" : ""}`}
          >
            <PlayCellEditor
              key={itemId + ":" + mine}
              id={"play-monthly-cell-" + index}
              label={
                safetyWeek && itemId === weekCandidate
                  ? `안전교육 후보 · ${placeOf(plan, selected!).split(" · ")[0]}`
                  : labels[itemId]
              }
              value={cellValue(plan, itemId) ?? ""}
              allowBlank
              readOnly={locked}
              onDraft={(text) => setLive((drafts) => ({ ...drafts, [itemId]: text }))}
              onSave={(text) => {
                // 거절 · 되돌리기로 다시 열린 뒤 옛 입력창이 사라지며 보내는 글은 버린다.
                if (mine !== stamp(bumpsRef.current, itemId)) return;
                if (save.editCell(itemId, text)) clearLive(itemId);
              }}
              onRevert={() => clearLive(itemId)}
            />
          </div>
        );
      })}
      {safetyWeek && weekCandidate && (
        <p className="m-0 text-[13px] text-[#5c5243]">이 문장을 둔 다른 주도 같이 바뀌어요.</p>
      )}
      {slot && (
        <div className="flex flex-col gap-3 border-t border-[#efeae2] pt-4">
          <SlotTools
            plan={plan}
            itemId={selected!}
            slot={slot}
            disabled={locked}
            onSplit={(axis) => save.splitCell(selected!, axis)}
            onRemove={askRemoveSlot}
            onRatio={save.resizeSplit}
          />
          {asking && (
            <PlayMonthlyConfirm
              message={
                (cellValue(plan, selected!)?.trim() ? "이 칸의 글이 문서에서 빠져요. " : "") +
                (removal(plan, selected!) === null
                  ? "옆 칸이 나뉘어 있어 되돌릴 수 없어요. 뺄까요?"
                  : "뺄까요?")
              }
              yes="빼기"
              disabled={locked}
              onYes={removeSlot}
              onNo={() => setAsking(false)}
            />
          )}
        </div>
      )}
      {row && (
        <RowOrder
          rows={plan.together.includes(row) ? plan.together : plan.free_play}
          row={row}
          disabled={locked}
          onMove={(to) =>
            moveRow(plan.together.includes(row) ? "together" : "free_play", row.activity_id, to)
          }
        />
      )}
      {row && candidateRow && (
        <p className="m-0 border-t border-[#efeae2] pt-4 text-[13px] text-[#5c5243]">
          「AI 후보」에서 − 를 누르면 후보로 돌아가요.
        </p>
      )}
      {row && !candidateRow && (
        <div className="border-t border-[#efeae2] pt-4">
          <PlayMonthlyRowRemove
            activity={row}
            section={plan.together.includes(row) ? "함께 하는 활동" : "자유놀이"}
            onRemove={save.removeActivity}
            disabled={locked}
            isLastInSection={
              !picking &&
              (plan.together.includes(row) ? plan.together : plan.free_play).length === 1
            }
          />
        </div>
      )}
    </div>
  );
  const aiTab = safetyWeek ? (
    <PlayMonthlySafetyPanel
      plan={plan}
      weekId={safetyWeek}
      onPlace={save.placeSafety}
      onWeek={(weekId) => select("safety:" + weekId)}
      disabled={locked}
    />
  ) : pickSection ? (
    <PlayMonthlyActivityPanel
      plan={plan}
      section={pickSection}
      onPick={save.pickActivity}
      onRemove={save.removeActivity}
      disabled={locked}
    />
  ) : selected && selected === drillId ? (
    <PlayMonthlyDrillPanel
      candidates={plan.drill_candidates}
      current={plan.teacher_inputs.find((t) => t.key === "fire_disaster_drill")?.cell.value ?? ""}
      onCopy={copyDrill}
      onClear={() => {
        if (drillId && save.editCell(drillId, "")) {
          clearLive(drillId);
          bump(drillId);
        }
      }}
      disabled={locked}
    />
  ) : (
    <PickCellHint>칸을 누르면 후보가 보여요.</PickCellHint>
  );
  const aside = (
    <>
      <div
        role="tablist"
        aria-label="고치는 방법"
        className="flex gap-1 border-b border-line px-6 pt-3"
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
  const back = (
    <Link
      href="/plans/monthly"
      aria-label="월간계획안 만들기로"
      title="월간계획안 만들기로"
      className={BACK_BUTTON}
    >
      {BACK_ICON}
    </Link>
  );
  // Ⓜ4 — 놀이 중심형은 주간 없이 다음 달 월간으로 간다.
  if (confirmed)
    return (
      <PlanDone
        title={`${plan.month}월 월간계획안`}
        download={(format) => downloadPlayMonthlyHwpx(plan.id, format)}
        docLabel="확정된 월간계획안"
        format="PLAY_PROJECT"
        pages={[<PlayMonthlySheet key="sheet" plan={plan} />]}
        next={{
          href: "/plans/monthly",
          label: `${(plan.month % 12) + 1}월 월간 만들기`,
        }}
        notes={
          <>
            {notice && <span role="status">{notice}</span>}
            {plan.parent_changed && <span role="status">상위 계획안이 바뀌었어요</span>}
            {message && <span role="status">{message}</span>}
          </>
        }
      />
    );
  if (choosing) {
    const max = plan.activity_pick!;
    const picked = plan[choosing].map((r) => r.activity_id);
    const goTo = (s: PlaySection | null) => {
      setFocus(null);
      setChoosing(s);
    };
    const toggle = (id: string) => {
      if (locked) return;
      if (picked.includes(id)) save.removeActivity(id);
      else save.pickActivity(id);
    };
    return (
      <main className={workspace.page}>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3">
            {back}
            <h1 className="penMark m-0 font-display text-[34px] font-bold leading-[1.2] text-ink">
              활동 고르기
            </h1>
            <span className="-rotate-2 border border-black/10 bg-[#eee4f4] px-3 py-0.5 font-display text-[18px] font-bold text-[#5e4b96] shadow-pg-card">
              놀이 중심형
            </span>
            <span role="status" className="text-[13px] text-ink-soft">
              {SAVE_LABEL[save.status]}
            </span>
            {save.status === "failed" && (
              <button type="button" className={workspace.secondary} onClick={save.retry}>
                다시 저장
              </button>
            )}
          </div>
          <div
            role="tablist"
            aria-label="고를 목록"
            className="flex flex-wrap gap-0.5 rounded-md border border-line bg-paper p-0.5"
          >
            {(["together", "free_play"] as const).map((s) => (
              <button
                key={s}
                type="button"
                role="tab"
                aria-selected={choosing === s}
                className={`${pageClass(choosing === s)} inline-flex items-center gap-1.5`}
                onClick={() => goTo(s)}
              >
                {SECTION_LABEL[s]}{" "}
                <span className="rounded-full bg-[#f3efe8] px-1.5 text-xs font-bold">
                  {plan[s].length}/{max}
                </span>
              </button>
            ))}
          </div>
        </div>
        {(notice || message) && (
          <p role="status" className={workspace.notice}>
            {notice || message}
          </p>
        )}
        <PlayPickBoard
          subject={SECTION_LABEL[choosing]}
          max={max}
          candidates={sectionCandidates(plan, choosing).map(({ row }) => ({
            key: row.activity_id,
            name: row.name.value.trim() || "(빈 후보)",
            summary: row.description.value,
            fields: [{ label: "설명", lines: [row.description.value] }],
            trendApplied: row.trend_applied,
          }))}
          picked={picked}
          focus={focus}
          idPrefix={`play-monthly-${plan.id}-pick`}
          onFocus={setFocus}
          onToggle={toggle}
          onRemove={(id) => {
            toggle(id);
            document.getElementById(`play-monthly-${plan.id}-pick-heading`)?.focus();
          }}
          onNext={() => goTo(choosing === "together" ? "free_play" : null)}
          nextLabel={
            choosing === "together" ? `${SECTION_LABEL.free_play} 고르러 가기` : "문서 만들기"
          }
          onFinishEarly={choosing === "together" ? () => goTo(null) : undefined}
        />
      </main>
    );
  }
  return (
    <AnnualFrame
      title={`${plan.month}월 월간계획안`}
      format="PLAY_PROJECT"
      lead={back}
      saved={SAVE_LABEL[save.status]}
      status={<PlanMemoNote plan={plan} />}
      notice={
        (notice || message || plan.parent_changed || save.status === "failed") && (
          <div className="flex flex-wrap items-center gap-3 text-sm text-[#5c5243]">
            {notice && <span role="status">{notice}</span>}
            {plan.parent_changed && <span role="status">상위 계획안이 바뀌었어요</span>}
            {message && <span role="status">{message}</span>}
            {save.status === "failed" && (
              <button type="button" className={BUTTON.outline} onClick={save.retry}>
                다시 저장
              </button>
            )}
          </div>
        )
      }
      actions={
        <>
          {!confirmed && (
            <DraftSave disabled={locked} save={async () => (await save.whenIdle()).saved} />
          )}
          <PlayMonthlyConfirmBar
            plan={plan}
            ask={
              short.length
                ? `함께 하는 활동 · 자유놀이는 AI 후보에서 ${plan.activity_pick}개씩 골라야 확정할 수 있어요.`
                : ""
            }
            // 빈칸으로 가면 확정 창을 닫는다(주제형 월간 · 주간과 같다).
            blanks={(close) => (
              <BlankRows
                lead={short.length ? "남은 빈칸이 있어요." : BLANK_LEAD}
                rows={blankRows.map((r) => ({
                  ...r,
                  onJump: () => {
                    close();
                    r.onJump();
                  },
                }))}
              />
            )}
            whenIdle={save.whenIdle}
            freeze={() => {
              setFrozen(true);
              save.freeze();
            }}
            unfreeze={() => {
              setFrozen(false);
              save.unfreeze();
            }}
            onConfirmed={setPlan}
            onConflict={() => {
              setStopped(true);
              onConflict();
            }}
          />
        </>
      }
      aside={aside}
      docLabel={null}
      docHint={
        <div className="flex items-center gap-2">
          <UndoRedo
            disabled={locked}
            canUndo={save.canUndo}
            onUndo={() => through("undo")}
            canRedo={save.canRedo}
            onRedo={() => through("redo")}
          />
          {sheetZoom.tools}
          <span>
            <BigView
              pages={1}
              width={PAPER_WIDTH}
              render={() => <PlayMonthlySheet plan={shown} />}
            />
          </span>
        </div>
      }
    >
      <div ref={docBox}>
        <PlayMonthlySheet
          plan={shown}
          selected={selected}
          onSelect={select}
          scale={sheetZoom.percent / 100}
          onRatio={locked ? undefined : save.resizeSplit}
          onSize={locked ? undefined : save.resizeTable}
          onMoveSafety={locked ? undefined : moveSafety}
          onPlaceSafety={locked ? undefined : save.placeSafety}
          onDropDrill={locked ? undefined : copyDrill}
          onMoveHabit={locked ? undefined : moveHabit}
          onMoveRow={locked ? undefined : moveRow}
        />
      </div>
    </AnnualFrame>
  );
}

const TOOL =
  "flex min-h-[36px] items-center gap-1.5 rounded-md px-2.5 text-[13px] font-semibold disabled:opacity-40";
/** 끌기의 키보드 대안 — 고른 행을 같은 목록 안에서 한 칸 위 · 아래로. */
function RowOrder({
  rows,
  row,
  disabled,
  onMove,
}: {
  rows: PlayMonthlyPlan["together"];
  row: PlayMonthlyPlan["together"][number];
  disabled: boolean;
  onMove: (toId: string) => void;
}) {
  const at = rows.indexOf(row);
  const step = (delta: -1 | 1) => {
    const to = rows[at + delta];
    return (
      <button
        type="button"
        className={`${TOOL} text-[#5e4b96] hover:bg-[#f6f1fb]`}
        disabled={disabled || !to}
        onClick={() => onMove(to.activity_id)}
      >
        {delta < 0 ? "↑ 위로 옮기기" : "↓ 아래로 옮기기"}
      </button>
    );
  };
  return (
    <div role="group" aria-label="행 순서" className="flex flex-wrap items-center gap-2">
      <div className="inline-flex rounded-lg border border-[#ddd6ca] bg-white p-0.5">
        {step(-1)}
        {step(1)}
      </div>
    </div>
  );
}

/** 16px 선 그림 — 칸 나누기 도구. */
const icon = (d: string) => (
  <svg
    aria-hidden="true"
    viewBox="0 0 16 16"
    className="h-4 w-4 shrink-0"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
  >
    <rect x="2" y="2.5" width="12" height="11" rx="1.5" />
    <path d={d} />
  </svg>
);

/**
 * 특별활동 칸 도구 — 나누기 두 가지(한 묶음) · 빼기, 나뉜 칸이면 그 칸의 크기.
 * 한도(깊이 · 칸 폭 3.5%)를 넘는 단추는 끈다. 최종 검사는 서버가 한다.
 */
function SlotTools({
  plan,
  itemId,
  slot,
  disabled,
  onSplit,
  onRemove,
  onRatio,
}: {
  plan: PlayMonthlyPlan;
  itemId: string;
  slot: NonNullable<ReturnType<typeof locate>>;
  disabled: boolean;
  onSplit: (axis: "VERTICAL" | "HORIZONTAL") => void;
  onRemove: () => void;
  onRatio: (splitId: string, ratio: number) => void;
}) {
  const day = plan.special_activity[slot.day];
  const width = plan.special_activity_size.column_widths[slot.day];
  const cramped = (axis: "VERTICAL" | "HORIZONTAL") =>
    axis === "HORIZONTAL" &&
    narrowest(splitLeaf(day, itemId, axis, "", slot.path.at(-1)!.cell!), width) < CELL_MIN_WIDTH;
  const parent = slot.path.at(-2);
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        {/* 주간 대·소집단 칸 나누기와 같은 말(WeeklyEditor). */}
        <div
          role="group"
          aria-label="칸 나누기"
          className="inline-flex rounded-lg border border-[#ddd6ca] bg-white p-0.5"
        >
          {(["VERTICAL", "HORIZONTAL"] as const).map((axis) => (
            <button
              key={axis}
              type="button"
              className={`${TOOL} text-[#5e4b96] hover:bg-[#f6f1fb]`}
              disabled={disabled || slot.path.length - 1 >= MAX_DEPTH || cramped(axis)}
              onClick={() => onSplit(axis)}
            >
              {icon(axis === "VERTICAL" ? "M2 8h12" : "M8 2.5v11")}
              {axis === "VERTICAL" ? "위아래로 나누기" : "좌우로 나누기"}
            </button>
          ))}
        </div>
        <button
          type="button"
          className={`${TOOL} text-[#a2492f] hover:bg-[#fbf0ec]`}
          disabled={disabled || !parent}
          onClick={onRemove}
        >
          {icon("M5.5 8h5")}이 칸 빼기
        </button>
      </div>
      {parent && (
        <SlotSize
          plan={plan}
          day={slot.day}
          parent={parent}
          first={parent.children[0] === slot.path.at(-1)}
          disabled={disabled}
          onRatio={onRatio}
        />
      )}
    </>
  );
}

/** 나뉜 칸의 크기 — 경계(`split_id`) 비율을 이 칸 쪽 몫으로 보여 주고 5씩 바꾼다(비율 10~90 · 칸 폭 3.5%). */
function SlotSize({
  plan,
  day,
  parent,
  first,
  disabled,
  onRatio,
}: {
  plan: PlayMonthlyPlan;
  day: number;
  parent: PlayMonthlyPlan["special_activity"][number];
  first: boolean;
  disabled: boolean;
  onRatio: (splitId: string, ratio: number) => void;
}) {
  const ratio = parent.ratio!;
  const share = first ? ratio : 100 - ratio;
  const what = parent.axis === "VERTICAL" ? "높이" : "너비";
  const next = (delta: number) => (first ? ratio + delta : ratio - delta);
  const ok = (r: number) =>
    r >= RATIO_RANGE[0] &&
    r <= RATIO_RANGE[1] &&
    !tooNarrow(
      plan.special_activity.map((d, i) => (i === day ? withRatio(d, parent.split_id!, r) : d)),
      plan.special_activity_size.column_widths,
    );
  const step = (delta: number, label: string) => (
    <button
      type="button"
      aria-label={`이 칸 ${what} ${label}`}
      className="flex h-9 w-9 items-center justify-center rounded-md text-[18px] font-bold text-[#5e4b96] hover:bg-[#f6f1fb] disabled:opacity-40"
      disabled={disabled || !ok(next(delta))}
      onClick={() => onRatio(parent.split_id!, next(delta))}
    >
      {delta < 0 ? "−" : "+"}
    </button>
  );
  return (
    <div role="group" aria-label={`이 칸 ${what}`} className="flex items-center gap-3">
      <span className="text-sm text-[#5c5243]">이 칸 {what}</span>
      <div className="inline-flex items-center rounded-lg border border-[#ddd6ca] bg-white p-0.5">
        {step(-5, "줄이기")}
        <span className="min-w-[3.5em] text-center text-sm font-bold tabular-nums">{share}%</span>
        {step(5, "키우기")}
      </div>
    </div>
  );
}
