"use client";
import { useEffect, useState } from "react";
import AppHeader from "@/components/app/AppHeader";
import workspace from "@/components/workspace/Workspace.module.css";
import { ApiError } from "@/lib/api/client";
import { getMe } from "@/lib/api/auth";
import { getClasses } from "@/lib/api/classes";
import { getPlayMonthly } from "@/lib/api/playMonthly";
import type { PlayMonthlyPlan } from "@/lib/api/types";
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

export default function PlayMonthlyView({ id }: { id: number }) {
  const valid = Number.isSafeInteger(id) && id > 0;
  const [loaded, setLoaded] = useState<{
    key: string;
    plan: PlayMonthlyPlan | null;
    error: string;
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
  const summary = noticeSummary(plan.notices);
  const rows = [...plan.together, ...plan.free_play];
  return (
    <>
      {header}
      <main className={workspace.page}>
        <div className={styles.meta}>
          <span className={workspace.badge}>{plan.status === "CONFIRMED" ? "확정됨" : "초안"}</span>
          <span>
            {plan.school_year}학년도 {plan.month}월
          </span>
          {summary && <span role="status">빈 곳 · {summary} (확정을 막지 않아요)</span>}
        </div>
        <div className={styles.layout}>
          <aside className={styles.side} aria-label="연간에서 고른 놀이">
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
            plan={plan}
            className={names?.classId === plan.class_id ? names.name : ""}
            zoom={zoom}
            onZoomChange={setZoom}
          />
        </div>
      </main>
    </>
  );
}
