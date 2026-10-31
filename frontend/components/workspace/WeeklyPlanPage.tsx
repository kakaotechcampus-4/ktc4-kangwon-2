"use client";

/**
 * 주간계획안 화면 (FR-304 · docs/weekly-plan-contract.md) — A안 카드형.
 *
 * 칸 12개를 목적별로 묶는다: 이번 주 방향 · 놀이와 활동 · 생활 · 안전 · 선생님이 직접 쓰는 칸.
 * 칸마다 누가 쓴 값인지(AI 초안 · 자동 선택 · 교사 수정 · 직접 입력)를 보인다.
 *
 * **월간을 확정해야 들어온다** (§4-1 G3). 주는 부모 월간이 준 `week_id` 만 쓴다 (§3-1).
 * **교사 입력 칸 셋은 만들지 않는다** (§6-2) — 다시 만들기 단추를 안 띄운다.
 * **확정 취소가 없다** (ADR-030 PM-03). 확정 전에 지우고 다시 만드는 길만 둔다.
 * 제출 문서는 표 양식이다 — 확정본만 한글 파일로 내려받는다.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError } from "@/lib/api/client";
import { getMonthlyPlan, listMonthlyPlans } from "@/lib/api/monthly";
import { classServerId, syncClass } from "@/lib/api/onboarding";
import type { MonthlyPlan, WeeklyCell, WeeklyPlan, WeeklyPlanSummary } from "@/lib/api/types";
import {
  confirmWeeklyPlan,
  createWeeklyPlan,
  deleteWeeklyPlan,
  downloadWeeklyHwpx,
  editWeeklyCell,
  getWeeklyPlan,
  getWeeklyPlanAudit,
  listWeeklyPlans,
  regenerateWeeklyCell,
} from "@/lib/api/weekly";
import { useHwpxDownload } from "@/lib/hooks/use-hwpx-download";
import { loadClassSettings, primaryClassFor } from "@/lib/onboarding/settings";
import { useClientState } from "@/lib/hooks/use-client-state";
import { archivePlanEntry } from "@/lib/workspace/document-archive";
import { DAY_NAMES, sectionName } from "@/lib/weekly/section-labels";
import { WorkspacePage, Empty, Message } from "./WorkspaceUI";
import s from "./WeeklyPlanPage.module.css";

function describe(e: unknown, fallback: string): string {
  if (e instanceof ApiError) return e.message;
  return e instanceof Error ? e.message : fallback;
}

const MONTHS = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2];
const ALL_DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT"];

/** 묶음. 여기 없는 칸은 「그 밖의 칸」에 모은다 — 서버가 준 칸을 숨기지 않는다. */
const GROUPS: { title: string; keys: string[] }[] = [
  { title: "이번 주 방향", keys: ["theme", "focus", "goals"] },
  {
    title: "놀이와 활동",
    keys: ["indoor_play", "group_activity", "outdoor_play", "indoor_alternative"],
  },
  { title: "생활 · 안전", keys: ["basic_habit", "safety_education"] },
];

/** `2026-09-07` → `9. 7.(월)` */
function shortDate(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  const day = ["일", "월", "화", "수", "목", "금", "토"][d.getDay()];
  return `${d.getMonth() + 1}. ${d.getDate()}.(${day})`;
}

type Origin = { label: string; tone: string } | null;

/** 누가 쓴 값인가. 교사 수정은 생성 방식을 바꾸지 않으므로 이력에서 읽는다 (CLAUDE.md §13.2). */
function originOf(cell: WeeklyCell, edited: Set<string>): Origin {
  if (cell.teacher_input)
    return cell.value.trim() ? { label: "직접 입력", tone: s.chipManual } : null;
  if (edited.has(cell.item_id)) return { label: "교사 수정", tone: s.chipEdited };
  const method = cell.generation?.method;
  if (method === "RULE_LLM") return { label: "AI 초안", tone: s.chip };
  if (method === "RULE_ONLY") return { label: "자동 선택", tone: s.chipRule };
  if (method === "MANUAL") return { label: "직접 입력", tone: s.chipManual };
  return null;
}

/** 무엇에 기댔는가 — 한 줄. */
function sourceOf(cell: WeeklyCell): string {
  const parts: string[] = [];
  const samples = cell.evidence.filter((e) => e.source_type === "INSTITUTION_SAMPLE").length;
  if (samples) parts.push(`근거 기관 자료 ${samples}건`);
  if (cell.evidence.some((e) => e.source_type === "ACTIVITY_REFERENCE"))
    parts.push("활동 참고자료에서 고름");
  if (cell.parent_snapshots.length || cell.evidence.some((e) => e.source_type === "PARENT_PLAN"))
    parts.push("월간계획안에서 이어받음");
  return parts.join(" · ");
}

function readArchiveEntry() {
  return archivePlanEntry(typeof window === "undefined" ? "" : window.location.search);
}

export default function WeeklyPlanPage() {
  const [entry] = useClientState(readArchiveEntry, null);
  const [classId, setClassId] = useState<number | null>(null);
  const [className, setClassName] = useState("");
  const [month, setMonth] = useClientState(
    () => readArchiveEntry()?.month ?? new Date().getMonth() + 1,
    new Date().getMonth() + 1,
  );
  /** 그 달 월간계획안. 확정본이어야 주간을 만들 수 있다 (G3). */
  const [monthly, setMonthly] = useState<MonthlyPlan | null>(null);
  const [summaries, setSummaries] = useState<WeeklyPlanSummary[]>([]);
  const [weekId, setWeekId] = useState("");
  const [plan, setPlan] = useState<WeeklyPlan | null>(null);
  const [edited, setEdited] = useState<Set<string>>(new Set());
  const [editing, setEditing] = useState<{ itemId: string; draft: string } | null>(null);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [problem, setProblem] = useState("");
  const hwpx = useHwpxDownload(setMessage);

  const loadMonthly = useCallback(async (id: number, target: number) => {
    const { items } = await listMonthlyPlans(id);
    const found = items.find((p) => p.month === target && p.status === "CONFIRMED");
    return found ? await getMonthlyPlan(found.id) : null;
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const settings = loadClassSettings();
        const primary =
          settings &&
          (entry
            ? settings.classes.find((c) => classServerId(c.id) === entry.classId)
            : primaryClassFor(settings));
        if (!settings || !primary) throw new Error("반 정보를 먼저 저장해주세요.");
        const id = await syncClass(settings, primary);
        const [parent, list] = await Promise.all([
          loadMonthly(id, month),
          listWeeklyPlans(id, month),
        ]);
        if (!alive) return;
        setClassId(id);
        setClassName(primary.className);
        setMonthly(parent);
        setSummaries(list.items);
        // 달을 바꾸면 고른 주와 띄워 둔 계획안은 다른 달 것이다. 같이 비운다.
        setWeekId(
          entry?.month === month &&
            parent?.weeks.some((w) => w.week_id === entry.weekId && w.active)
            ? entry.weekId
            : "",
        );
        setPlan(null);
        setEditing(null);
      } catch (e) {
        if (alive) setProblem(describe(e, "주간계획안을 불러오지 못했어요."));
      }
    })();
    return () => {
      alive = false;
    };
  }, [loadMonthly, month, entry]);

  const weeks = useMemo(() => monthly?.weeks.filter((w) => w.active) ?? [], [monthly]);
  const summaryOf = (id: string) => summaries.find((p) => p.week_id === id);

  /** 주를 고르면 그 주 계획안을 불러온다. 없으면 null — 만들기 단추를 띄운다. */
  useEffect(() => {
    if (!weekId) return;
    // 보관함에서 연 계획안이면 그 id 를 고른다 (같은 주에 지운 뒤 다시 만든 판이 있을 수 있다).
    const found = summaries.find(
      (p) =>
        p.week_id === weekId &&
        (!entry || entry.classId !== classId || entry.weekId !== weekId || p.id === entry.id),
    );
    if (!found || plan?.id === found.id) return;
    let alive = true;
    getWeeklyPlan(found.id)
      .then((next) => alive && setPlan(next))
      .catch((e) => alive && setProblem(describe(e, "그 주를 불러오지 못했어요.")));
    return () => {
      alive = false;
    };
  }, [weekId, summaries, plan?.id, classId, entry]);

  /** 계획안이 바뀔 때마다 이력을 다시 읽어 「교사 수정」 칸을 고른다. */
  useEffect(() => {
    if (!plan) return;
    let alive = true;
    getWeeklyPlanAudit(plan.id)
      .then(({ items }) => {
        const last = new Map<string, string>();
        for (const e of items)
          if (e.item_id && (e.type === "TEACHER_EDITED" || e.type === "REGENERATED"))
            last.set(e.item_id, e.type);
        if (alive)
          setEdited(new Set([...last].filter(([, t]) => t === "TEACHER_EDITED").map(([id]) => id)));
      })
      .catch(() => alive && setEdited(new Set()));
    return () => {
      alive = false;
    };
  }, [plan]);

  const confirmed = plan?.status === "CONFIRMED";
  const cells = useMemo(() => {
    const map = new Map<string, WeeklyCell>();
    for (const section of plan?.sections ?? [])
      if (section.visible && section.cells[0]) map.set(section.section_key, section.cells[0]);
    return map;
  }, [plan]);
  const labels = useMemo(
    () =>
      new Map(
        (plan?.sections ?? []).map((x) => [x.section_key, sectionName(x.section_key, x.label)]),
      ),
    [plan],
  );
  const teacherKeys = [...cells].filter(([, c]) => c.teacher_input).map(([k]) => k);
  const grouped = new Set([...GROUPS.flatMap((g) => g.keys), ...teacherKeys]);
  const otherKeys = [...cells.keys()].filter((k) => !grouped.has(k));

  const theme = cells.get("theme");
  const blocked = theme && !theme.value.trim() ? "놀이 주제를 적어야 확정할 수 있어요." : "";

  async function run(key: string, job: () => Promise<WeeklyPlan | void>) {
    setBusy(key);
    setMessage("");
    setProblem("");
    try {
      const next = await job();
      if (next) {
        setPlan(next);
        setSummaries((list) => [...list.filter((p) => p.id !== next.id), next]);
      }
    } catch (e) {
      setProblem(describe(e, "처리하지 못했어요."));
    } finally {
      setBusy("");
    }
  }

  const handleCreate = () =>
    run("create", async () => {
      if (classId === null || !weekId) return;
      return createWeeklyPlan({ class_id: classId, week_id: weekId });
    });

  const handleDelete = () =>
    run("delete", async () => {
      if (!plan) return;
      await deleteWeeklyPlan(plan.id);
      setSummaries((list) => list.filter((p) => p.id !== plan.id));
      setPlan(null);
      setMessage("지웠어요. 다시 만들 수 있어요.");
    });

  const handleSave = () =>
    run("edit", async () => {
      if (!plan || !editing) return;
      const cell = [...cells.values()].find((c) => c.item_id === editing.itemId);
      const value = editing.draft;
      setEditing(null);
      if (!cell || value === cell.value) return;
      return editWeeklyCell(plan.id, cell.item_id, value, plan.revision);
    });

  const handleRegenerate = (cell: WeeklyCell) =>
    run(cell.item_id, async () => {
      if (!plan) return;
      return regenerateWeeklyCell(plan.id, cell.item_id, plan.revision);
    });

  const handleConfirm = () =>
    run("confirm", async () => {
      if (!plan) return;
      const next = await confirmWeeklyPlan(plan.id, plan.revision);
      setMessage("확정했어요. 계획안은 확정을 되돌릴 수 없어요.");
      return next;
    });

  function renderCard(sectionKey: string, wide = false) {
    const cell = cells.get(sectionKey);
    if (!cell) return null;
    const name = labels.get(sectionKey) ?? sectionKey;
    const origin = originOf(cell, edited);
    const source = cell.teacher_input ? "" : sourceOf(cell);
    const working = busy === cell.item_id;
    const empty = !cell.value.trim();

    if (editing?.itemId === cell.item_id)
      return (
        <article key={sectionKey} className={`${s.card} ${wide ? s.wide : ""}`}>
          <div className={s.cardName}>
            <h4>{name}</h4>
          </div>
          <textarea
            className={s.editor}
            aria-label={`${name} 내용`}
            value={editing.draft}
            autoFocus
            onChange={(e) => setEditing({ itemId: cell.item_id, draft: e.target.value })}
          />
          <div className={s.cardButtons}>
            <button type="button" className={s.btnSmall} disabled={!!busy} onClick={handleSave}>
              저장
            </button>
            <button type="button" className={s.btnSmall} onClick={() => setEditing(null)}>
              취소
            </button>
          </div>
        </article>
      );

    if (cell.teacher_input && empty)
      return (
        <article key={sectionKey} className={s.cardEmpty}>
          <div className={s.cardName}>
            <h4>{name}</h4>
          </div>
          <p className={s.soft} style={{ margin: 0 }}>
            아직 비어 있어요.
          </p>
          {!confirmed && (
            <button
              type="button"
              className={s.btnSmall}
              style={{ alignSelf: "flex-start" }}
              disabled={!!busy}
              onClick={() => setEditing({ itemId: cell.item_id, draft: "" })}
            >
              입력하기
            </button>
          )}
        </article>
      );

    return (
      <article key={sectionKey} className={`${s.card} ${wide ? s.wide : ""}`}>
        <div className={s.cardHead}>
          <div className={s.cardName}>
            <h4>{name}</h4>
            {origin && <span className={origin.tone}>{origin.label}</span>}
          </div>
          {!confirmed && (
            <div className={s.cardButtons}>
              <button
                type="button"
                className={s.btnSmall}
                disabled={!!busy}
                onClick={() => setEditing({ itemId: cell.item_id, draft: cell.value })}
              >
                고치기
              </button>
              {!cell.teacher_input && (
                <button
                  type="button"
                  className={s.btnSmall}
                  disabled={!!busy}
                  onClick={() => handleRegenerate(cell)}
                >
                  {working ? "만드는 중…" : "다시 만들기"}
                </button>
              )}
            </div>
          )}
        </div>
        {empty ? (
          <p className={s.soft} style={{ margin: 0 }}>
            {cell.state === "EMPTY_UNRESOLVED"
              ? "근거가 없어 비워 두었어요. 직접 적어주세요."
              : "비어 있어요."}
          </p>
        ) : (
          <p className={`${s.value} ${sectionKey === "theme" ? s.valueTheme : ""}`}>{cell.value}</p>
        )}
        {source && <div className={s.source}>{source}</div>}
      </article>
    );
  }

  const weekLabel = weeks.find((w) => w.week_id === weekId)?.label ?? weekId;
  const dayOnly = (iso: string) => shortDate(iso).replace(/\(.\)$/, "");

  return (
    <WorkspacePage
      title="주간계획안"
      description="확정한 월간계획안을 바탕으로 한 주 계획을 만들어요. 칸마다 누가 썼는지와 근거를 볼 수 있어요."
    >
      <Message error>{problem}</Message>
      <Message>{message}</Message>

      <div className={s.wrap}>
        {/* 주 고르기 — 월간이 정한 활성 주차만 (§3-1) */}
        <nav aria-label={`${month}월의 주`} className={s.picker}>
          <label className={s.month}>
            월
            <select value={month} onChange={(e) => setMonth(Number(e.target.value))}>
              {MONTHS.map((m) => (
                <option key={m} value={m}>
                  {m}월
                </option>
              ))}
            </select>
          </label>
          {weeks.map((w) => {
            const sum = summaryOf(w.week_id);
            const current = w.week_id === weekId;
            const state = sum
              ? sum.status === "CONFIRMED"
                ? "확정됨"
                : "초안"
              : "아직 없음 · 만들기";
            const tone = [
              s.week,
              sum ? "" : s.weekNone,
              current ? s.weekCurrent : "",
              sum?.status === "CONFIRMED" ? s.weekDone : "",
            ];
            return (
              <button
                key={w.week_id}
                type="button"
                aria-current={current ? "true" : undefined}
                className={tone.join(" ")}
                onClick={() => {
                  if (!current) setPlan(null); // 다른 주의 계획안을 띄워 두지 않는다
                  setWeekId(w.week_id);
                  setEditing(null);
                }}
              >
                <b>
                  {w.label} · {dayOnly(w.start_date)} – {dayOnly(w.end_date)}
                </b>
                <span>{current ? `${state} · 보는 중` : state}</span>
              </button>
            );
          })}
        </nav>

        {/* G3 — 월간이 확정돼야 주간을 만든다 (§4-1). */}
        {!monthly && (
          <Empty title={`${month}월 월간계획안을 먼저 확정해주세요`}>
            주간계획안은 확정한 월간계획안을 근거로 만들어요. 「월간계획안」에서 {month}월을 만들고
            확정해주세요.
          </Empty>
        )}
        {monthly && !weekId && <Empty title="어느 주를 만들까요">위에서 주를 골라주세요.</Empty>}
        {monthly && weekId && !plan && (
          <Empty title={`${weekLabel} 계획안이 아직 없어요`}>
            <button
              type="button"
              className={s.btnPrimary}
              disabled={!!busy || classId === null}
              onClick={handleCreate}
            >
              {busy === "create" ? "만드는 중… (20초쯤 걸려요)" : "이 주 계획안 만들기"}
            </button>
          </Empty>
        )}

        {plan && (
          <>
            <header className={s.head}>
              <div>
                <div className={s.eyebrow}>
                  주간계획안{className ? ` · ${className}` : ""} · {plan.school_year}학년도
                </div>
                <div className={s.titleRow}>
                  <h2>{weekLabel}</h2>
                  <span className={s.period}>
                    {shortDate(plan.week_period.start_date)} – {shortDate(plan.display_end_date)}
                  </span>
                  <span className={`${s.status} ${confirmed ? s.statusDone : ""}`}>
                    {confirmed ? "확정됨" : "초안"}
                  </span>
                </div>
              </div>
              <div className={s.actions}>
                {confirmed ? (
                  <button
                    type="button"
                    className={s.btnPrimary}
                    disabled={hwpx.exporting}
                    onClick={() => hwpx.download(() => downloadWeeklyHwpx(plan.id))}
                  >
                    {hwpx.exporting ? "파일 만드는 중…" : "한글 파일로 내려받기"}
                  </button>
                ) : (
                  <>
                    <button
                      type="button"
                      className={s.btn}
                      disabled={!!busy}
                      onClick={handleDelete}
                    >
                      초안 지우기
                    </button>
                    <button
                      type="button"
                      className={s.btnPrimary}
                      disabled={!!busy || !!blocked}
                      onClick={handleConfirm}
                    >
                      {busy === "confirm" ? "확정하는 중…" : "확정하기"}
                    </button>
                  </>
                )}
              </div>
            </header>
            {!confirmed && (
              <p className={s.soft} style={{ margin: "-16px 0 0" }}>
                {blocked || "확정하면 한글 파일(hwpx)로 내려받을 수 있어요."}
              </p>
            )}

            <div className={s.context}>
              <div>
                <span className={s.soft}>운영 요일</span>
                <span className={s.days}>
                  {ALL_DAYS.map((d) => (
                    <span key={d} className={plan.operating_days.includes(d) ? s.day : s.dayOff}>
                      {DAY_NAMES[d]}
                    </span>
                  ))}
                </span>
              </div>
              <div>
                <span className={s.soft}>이어받은 계획</span>
                <a href="/plans/monthly">
                  {month}월 월간계획안 (확정){plan.parent.theme ? ` · ${plan.parent.theme}` : ""}
                </a>
              </div>
            </div>

            {!confirmed && (
              <div role="note" className={s.note}>
                <svg
                  aria-hidden="true"
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <circle cx="12" cy="12" r="9" />
                  <path d="M12 8h.01" />
                  <path d="M11 12h1v5h1" />
                </svg>
                <div>
                  AI가 쓴 칸의 <b>날짜 · 시각 · 선생님 이름</b>은 입력한 내용과 대조했어요. 행사
                  이름처럼 그 밖의 사실은 확정 전에 한 번 더 확인해 주세요.
                </div>
              </div>
            )}

            {plan.verification.findings.length > 0 && (
              <ul className={s.findings}>
                {plan.verification.findings.map((f, i) => (
                  <li key={i}>{f.message}</li>
                ))}
              </ul>
            )}

            {GROUPS.map((g) => {
              const keys = g.keys.filter((k) => cells.has(k) && !teacherKeys.includes(k));
              if (!keys.length) return null;
              return (
                <section key={g.title} className={s.group}>
                  <div className={s.groupHead}>
                    <h3>{g.title}</h3>
                  </div>
                  <div className={s.grid2}>{keys.map((k) => renderCard(k, k === "theme"))}</div>
                </section>
              );
            })}

            {otherKeys.length > 0 && (
              <section className={s.group}>
                <div className={s.groupHead}>
                  <h3>그 밖의 칸</h3>
                </div>
                <div className={s.grid2}>{otherKeys.map((k) => renderCard(k))}</div>
              </section>
            )}

            {teacherKeys.length > 0 && (
              <section className={s.group}>
                <div className={s.groupHead}>
                  <h3>선생님이 직접 쓰는 칸</h3>
                  <span className={s.soft}>AI가 쓰지 않아요. 비워 두어도 확정할 수 있어요.</span>
                </div>
                <div className={s.grid3}>{teacherKeys.map((k) => renderCard(k))}</div>
              </section>
            )}
          </>
        )}
      </div>
    </WorkspacePage>
  );
}
