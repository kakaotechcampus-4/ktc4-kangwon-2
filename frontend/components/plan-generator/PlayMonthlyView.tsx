"use client";
import { useEffect, useRef, useState } from "react";
import AppHeader from "@/components/app/AppHeader";
import workspace from "@/components/workspace/Workspace.module.css";
import { ApiError } from "@/lib/api/client";
import { getMe } from "@/lib/api/auth";
import { getClasses } from "@/lib/api/classes";
import { getPlayMonthly } from "@/lib/api/playMonthly";
import type { PlayMonthlyPlan } from "@/lib/api/types";
import { usePlayMonthlySave } from "@/lib/hooks/use-play-monthly-save";
import { cellValue, overlayCells } from "@/lib/plan-generator/playMonthlyQueue";
import PlayCellEditor from "./PlayCellEditor";
import PlayMonthlySheet from "./PlayMonthlySheet";
import type { SheetZoom } from "./playProjectPagination";
import styles from "./PlayMonthlyView.module.css";

const NOTICES = {
  SAFETY_UNPLACED: ["안전교육", "주 미배치"],
  SAFETY_BLANK: ["안전교육", "주 빈 칸"],
  HABIT_BLANK: ["기본생활습관", "주 빈 칸"],
  HEALTH_BLANK: ["건강", "빈 칸"],
  NUTRITION_BLANK: ["영양", "빈 칸"],
} as const;

/** 서버가 준 notices 를 한 줄로 — 예: 「안전교육 4주 미배치 · 건강 빈 칸」. 확정을 막지 않는다. */
export function noticeSummary(notices: PlayMonthlyPlan["notices"]) {
  return (Object.keys(NOTICES) as (keyof typeof NOTICES)[])
    .map((code) => {
      const weeks = notices.filter((n) => n.code === code && n.week_id !== null).length;
      const hit = notices.some((n) => n.code === code);
      const [name, tail] = NOTICES[code];
      return !hit ? "" : weeks ? `${name} ${weeks}${tail}` : `${name} ${tail}`;
    })
    .filter(Boolean)
    .join(" · ");
}

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
  const [zoom, setZoom] = useState<SheetZoom>({ mode: "fit", percent: 100 });
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
  const header = (
    <AppHeader
      title="월간계획안 · 놀이 중심"
      description="연간에서 고른 놀이를 바탕으로 만든 월간계획안을 확인해주세요."
      divider={false}
    />
  );
  if (error)
    return (
      <>
        {header}
        <div className="px-4 lg:px-10">
          <p role="alert">{error}</p>
          {valid && <button onClick={() => setRetry((v) => v + 1)}>다시 불러오기</button>}
        </div>
      </>
    );
  if (!plan)
    return (
      <>
        {header}
        <p role="status" className="px-4 lg:px-10">
          계획안을 불러오고 있어요.
        </p>
      </>
    );
  return (
    <>
      {header}
      <PlayMonthlyBody
        key={key + ":" + (current?.version ?? 0)}
        initial={plan}
        className={names?.classId === plan.class_id ? names.name : ""}
        zoom={zoom}
        onZoomChange={setZoom}
        notice={current?.notice}
        onConflict={reloadAfterConflict}
      />
    </>
  );
}

function PlayMonthlyBody({
  initial,
  className,
  zoom,
  onZoomChange,
  notice,
  onConflict,
}: {
  initial: PlayMonthlyPlan;
  className: string;
  zoom: SheetZoom;
  onZoomChange: (zoom: SheetZoom) => void;
  notice?: string;
  onConflict: () => void;
}) {
  const [plan, setPlan] = useState(initial);
  // 입력 중 글(문서가 바로 따라간다) · 고른 칸 · 입력창을 다시 열 번호(되돌리기 · 거절) · 안내.
  const [live, setLive] = useState<Record<string, string>>({});
  const [selected, setSelected] = useState<string | null>(null);
  const [epoch, setEpoch] = useState(0);
  const [message, setMessage] = useState("");
  const save = usePlayMonthlySave(plan, setPlan, onConflict, () => {
    setLive({});
    setEpoch((n) => n + 1);
    setMessage("저장하지 못한 칸은 원래대로 되돌렸어요.");
  });
  const confirmed = plan.status === "CONFIRMED";
  const shown = overlayCells(plan, live);
  const labels = cellLabels(plan);
  const through = (direction: "undo" | "redo") => {
    save[direction]();
    setLive({});
    setEpoch((n) => n + 1);
    setMessage(direction === "undo" ? "되돌렸어요" : "다시 했어요");
  };
  const row = [...plan.together, ...plan.free_play].find((r) => r.name.item_id === selected);
  const editing = !confirmed && selected && labels[selected] ? [selected] : [];
  if (row) editing.push(row.description.item_id);
  const clearLive = (id: string) =>
    setLive((drafts) => Object.fromEntries(Object.entries(drafts).filter(([k]) => k !== id)));
  const summary = noticeSummary(plan.notices);
  const rows = [...plan.together, ...plan.free_play];
  return (
    <>
      <main className={workspace.page}>
        <div className={styles.meta}>
          <span className={workspace.badge}>{plan.status === "CONFIRMED" ? "확정됨" : "초안"}</span>
          <span>
            {plan.school_year}학년도 {plan.month}월
          </span>
          {summary && <span role="status">빈 곳 · {summary} (확정을 막지 않아요)</span>}
          {!confirmed && (
            <>
              <span role="status">{SAVE_LABEL[save.status]}</span>
              {save.status === "failed" && (
                <button type="button" className={workspace.secondary} onClick={save.retry}>
                  다시 저장
                </button>
              )}
              {(["undo", "redo"] as const).map((direction) => (
                <button
                  key={direction}
                  type="button"
                  className={workspace.secondary}
                  disabled={direction === "undo" ? !save.canUndo : !save.canRedo}
                  onClick={() => through(direction)}
                >
                  <span aria-hidden="true">{direction === "undo" ? "⟲" : "⟳"}</span>{" "}
                  {direction === "undo" ? "되돌리기" : "다시 하기"}
                </button>
              ))}
            </>
          )}
          <span role="status">{message}</span>
        </div>
        {notice && <p role="status">{notice}</p>}
        <div className={styles.layout}>
          <aside className={styles.side} aria-label="연간에서 고른 놀이">
            {!confirmed && (
              <section aria-label="칸 편집">
                <h2>칸 편집</h2>
                {editing.length === 0 && <p>문서의 칸을 누르면 여기서 고칠 수 있어요.</p>}
                {editing.map((itemId, index) => (
                  <PlayCellEditor
                    key={itemId + ":" + epoch}
                    id={"play-monthly-cell-" + index}
                    label={labels[itemId]}
                    value={cellValue(plan, itemId) ?? ""}
                    allowBlank
                    onDraft={(text) => setLive((drafts) => ({ ...drafts, [itemId]: text }))}
                    onSave={(text) => {
                      clearLive(itemId);
                      save.editCell(itemId, text);
                    }}
                    onRevert={() => clearLive(itemId)}
                  />
                ))}
              </section>
            )}
            <h2>연간에서 고른 놀이</h2>
            <ul>
              {plan.parent.plays.map((play) => (
                <li key={play.row_key}>
                  <strong>
                    {play.play_name}
                    {play.emphasized && <span className={styles.mark}>강조</span>}
                  </strong>
                  <p>지원매체 · {play.materials}</p>
                  <p>지원 방향 · {play.support_direction}</p>
                </li>
              ))}
            </ul>
            <h2>놀이 행의 누리과정 연결</h2>
            <ul>
              {rows.map((row) => (
                <li key={row.activity_id}>
                  {row.name.value}
                  <span className={styles.chips}>
                    {row.content_ids.map((cid) => (
                      <span key={cid} className={styles.chip}>
                        {cid}
                      </span>
                    ))}
                  </span>
                </li>
              ))}
            </ul>
          </aside>
          <PlayMonthlySheet
            plan={shown}
            selected={selected}
            onSelect={confirmed ? undefined : setSelected}
            className={className}
            zoom={zoom}
            onZoomChange={onZoomChange}
          />
        </div>
      </main>
    </>
  );
}
