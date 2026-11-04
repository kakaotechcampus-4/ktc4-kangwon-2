"use client";
import { useEffect, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { useCompactShell } from "@/components/app/compact-shell";
import workspace from "@/components/workspace/Workspace.module.css";
import { ApiError } from "@/lib/api/client";
import { getMe } from "@/lib/api/auth";
import { getClasses } from "@/lib/api/classes";
import { getPlayMonthly, unconfirmPlayMonthly } from "@/lib/api/playMonthly";
import type { PlayMonthlyPlan } from "@/lib/api/types";
import { usePlayMonthlySave } from "@/lib/hooks/use-play-monthly-save";
import { cellValue, drillTarget, overlayCells } from "@/lib/plan-generator/playMonthlyQueue";
import PlayCellEditor from "./PlayCellEditor";
import PlayMonthlyConfirmBar from "./PlayMonthlyConfirmBar";
import PlayMonthlyDrillPanel from "./PlayMonthlyDrillPanel";
import PlayMonthlyRowRemove from "./PlayMonthlyRowRemove";
import PlayMonthlySafetyPanel from "./PlayMonthlySafetyPanel";
import PlayMonthlySheet, { PAPER_WIDTH } from "./PlayMonthlySheet";
import AnnualFrame, {
  BigView,
  BUTTON,
  PlanDone,
  UNCONFIRM,
  tabClass,
  UndoRedo,
  useSheetZoom,
} from "./AnnualFrame";
import UnconfirmButton from "./UnconfirmButton";
import { PlanMemoNote } from "./PlanMemo";

const STALE_NOTICE = "다른 곳에서 바뀌었어요. 최신 내용을 다시 불러왔어요.";
const SAVE_LABEL = { idle: "", saving: "저장 중…", saved: "저장됨", failed: "저장하지 못했어요" };
const INPUT_LABELS: Record<string, string> = {
  fire_disaster_drill: "소방대피/재난대비",
  specialized_timetable: "특성화 시간표",
  special_activity_timetable: "특별활동 시간표",
  class_notice: "안내사항",
  class_birthdays: "우리반 생일",
  home_connection: "가정연계",
};

/** 고칠 수 있는 칸의 이름표. 놀이 행의 「설명」은 문서에 안 나와 행 이름을 누르면 패널에 함께 뜬다. */
export function cellLabels(plan: PlayMonthlyPlan) {
  const labels: Record<string, string> = {
    [plan.theme.item_id]: "놀이 주제",
    [plan.rationale.item_id]: "주제선정이유",
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
  const [names, setNames] = useState<{ classId: number; name: string } | null>(null);
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
  function reloadAfterConflict() {
    const mine = ++lastReload.current;
    const apply = (next: (cur: typeof loaded) => typeof loaded) =>
      mine === lastReload.current && setLoaded(next);
    getPlayMonthly(id).then(
      (fresh) =>
        apply((cur) => ({
          key,
          plan: fresh,
          error: "",
          notice: STALE_NOTICE,
          version: (cur?.version ?? 0) + 1,
        })),
      () =>
        apply(
          (cur) => cur && { ...cur, notice: "최신 내용을 불러오지 못했어요. 새로고침해 주세요." },
        ),
    );
  }
  // 확정을 풀면 응답으로 바꾸고 번호를 올려 다시 그린다 — 확정 뒤 멈춘 저장 줄을 새로 시작한다.
  function replace(fresh: PlayMonthlyPlan) {
    ++lastReload.current;
    setLoaded((cur) => ({ key, plan: fresh, error: "", version: (cur?.version ?? 0) + 1 }));
  }
  const current = loaded?.key === key ? loaded : null;
  const plan = current?.plan ?? null;
  const error = valid ? (current?.error ?? "") : "올바른 계획안 주소가 아닙니다.";
  // 반 이름은 읽기 전용 참고다. 계획안과 따로 받고, 늦거나 실패해도 문서는 먼저 그린다.
  const classId = plan?.class_id;
  useEffect(() => {
    if (classId === undefined) return;
    let live = true;
    getMe()
      .then((me) => (me.center_id ? getClasses(me.center_id) : { items: [] }))
      .then(({ items }) => {
        const name = items.find((c) => c.id === classId)?.name;
        if (live && name) setNames({ classId, name });
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [classId]);
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
      className={names?.classId === plan.class_id ? names.name : ""}
      notice={current?.notice}
      onConflict={reloadAfterConflict}
      onReplace={replace}
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
  className,
  notice,
  onConflict,
  onReplace,
}: {
  initial: PlayMonthlyPlan;
  className: string;
  notice?: string;
  onConflict: () => void;
  onReplace: (plan: PlayMonthlyPlan) => void;
}) {
  const [plan, setPlan] = useState(initial);
  // 입력 중 글(문서가 바로 따라간다) · 고른 칸 · 입력창을 다시 열 번호(되돌리기 · 거절) · 안내.
  const [live, setLive] = useState<Record<string, string>>({});
  const [selected, setSelected] = useState<string | null>(null);
  const [tab, setTab] = useState<"ai" | "edit">("edit");
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
    () => {
      setStopped(true);
      onConflict();
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
  const locked = stopped || frozen;
  const shown = overlayCells(plan, live);
  const labels = cellLabels(plan);
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
  // 안전교육 줄 · 소방대피 칸은 「AI 후보」 탭부터, 나머지는 「칸 편집」.
  const select = (id: string) => {
    setSelected(id);
    setTab(id.startsWith("safety:") || id === drillId ? "ai" : "edit");
  };
  const safetyWeek = selected?.startsWith("safety:") ? selected.slice(7) : null;
  const weekCandidate = safetyWeek
    ? (plan.safety_weeks.find((w) => w.week_id === safetyWeek)?.candidate_item_id ?? null)
    : null;
  const rows = [...plan.together, ...plan.free_play];
  const row = rows.find((r) => r.name.item_id === selected);
  // 안전교육 줄은 그 주에 둔 후보 문장을 고친다(같은 후보를 둔 다른 주도 같이 바뀐다).
  const target = safetyWeek ? weekCandidate : selected;
  const editing = !confirmed && target && labels[target] ? [target] : [];
  if (row && !confirmed) editing.push(row.description.item_id);
  const parentPlay =
    row?.parent_item_id &&
    plan.parent.plays.find((p) => p.play_name_item_id === row.parent_item_id);

  const editTab = (
    <div className="flex flex-col gap-4">
      {!selected && (
        <p className="m-0 text-sm text-[#5c5243]">문서의 칸을 누르면 여기서 고칠 수 있어요.</p>
      )}
      {selected && (
        <h2 className="m-0 text-lg font-bold">
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
      {row && (
        <div className="border-t border-[#efeae2] pt-4">
          <PlayMonthlyRowRemove
            activity={row}
            section={plan.together.includes(row) ? "함께 하는 활동" : "자유놀이"}
            onRemove={save.removeActivity}
            disabled={locked}
            isLastInSection={
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
      disabled={locked}
    />
  ) : selected && selected === drillId ? (
    <PlayMonthlyDrillPanel
      candidates={plan.drill_candidates}
      onCopy={copyDrill}
      disabled={locked}
    />
  ) : (
    <p className="m-0 text-sm text-[#5c5243]">
      안전교육이나 소방대피/재난대비 칸을 누르면 넣을 후보가 보여요.
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
  const back = (
    <Link
      href="/plans/monthly"
      aria-label="월간계획안 만들기로"
      className="flex h-11 w-11 items-center justify-center rounded-xl text-lg text-[#5c5243] no-underline hover:bg-white"
    >
      ←
    </Link>
  );
  // Ⓜ4 — 놀이 중심형은 주간 없이 다음 달 월간으로 간다. 한글 내보내기는 서버 경로가 생기면 붙인다.
  if (confirmed)
    return (
      <PlanDone
        title={`${plan.month}월 월간계획안을 확정했어요`}
        docLabel="확정된 월간계획안"
        format="PLAY_PROJECT"
        pages={[<PlayMonthlySheet key="sheet" plan={plan} className={className} />]}
        next={{
          href: "/plans/monthly",
          label: `${(plan.month % 12) + 1}월 월간 만들기 →`,
          hint: "놀이 중심형은 주간 없이 다음 달로 가요",
        }}
        unconfirm={
          <>
            {notice && <span role="status">{notice}</span>}
            {plan.parent_changed && <span role="status">상위 계획안이 바뀌었어요</span>}
            {message && <span role="status">{message}</span>}
            <UnconfirmButton
              message="확정을 풀면 다시 고칠 수 있어요."
              className={UNCONFIRM}
              run={() => unconfirmPlayMonthly(plan.id, plan.revision)}
              onDone={onReplace}
              onConflict={() => {
                setStopped(true);
                onConflict();
              }}
            />
          </>
        }
      />
    );
  return (
    <AnnualFrame
      title={`${plan.month}월 월간계획안`}
      format="PLAY_PROJECT"
      lead={back}
      status={
        <span className="flex items-center gap-3">
          <span>{SAVE_LABEL[save.status]}</span>
          <PlanMemoNote plan={plan} />
        </span>
      }
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
          <PlayMonthlyConfirmBar
            plan={plan}
            ask={
              "확정하면 확정을 풀기 전까지 고칠 수 없어요." +
              (plan.notices.length ? ` 확인할 것 ${plan.notices.length}개가 남았어요.` : "")
            }
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
              render={() => <PlayMonthlySheet plan={shown} className={className} />}
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
          className={className}
          scale={sheetZoom.percent / 100}
        />
      </div>
    </AnnualFrame>
  );
}
