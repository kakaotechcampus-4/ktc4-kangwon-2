"use client";

/**
 * 주간계획안 화면 (FR-304 · docs/weekly-plan-contract.md).
 *
 * **월간 화면과 모양이 다르다.** 월간은 주차가 열이라 표를 그리지만, 주간은 모든 Section 이
 * `repeat_by = NONE` 이라 Section 마다 칸이 하나다 (WQ-02). 그래서 표가 아니라 목록이다 —
 * 요일별 값은 칸 하나 안에 교사가 목록으로 쓴다.
 *
 * **월간을 확정해야 들어온다** (§4-1 G3). 주는 주간이 다시 세지 않고 부모 월간이 준
 * `week_id` 만 쓴다 (§3-1). 그래서 주 고르기가 「그 달 월간의 활성 주차」에서 나온다.
 *
 * **교사 입력 칸 셋은 만들지 않는다** — 가정 연계 · 행사 · 특별활동 (§6-2). 연간에 없는
 * 기관 운영 정보라 AI 가 지으면 없는 사실이 된다. 그 칸에는 다시 만들기 단추를 안 띄운다.
 *
 * **확정 취소가 없다** (ADR-030 PM-03). 확정 전에 지우고 다시 만드는 길만 둔다.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError } from "@/lib/api/client";
import { getMonthlyPlan, listMonthlyPlans } from "@/lib/api/monthly";
import { syncClass } from "@/lib/api/onboarding";
import type { MonthlyPlan, WeeklyCell, WeeklyPlan } from "@/lib/api/types";
import {
  confirmWeeklyPlan,
  createWeeklyPlan,
  deleteWeeklyPlan,
  editWeeklyCell,
  getWeeklyPlan,
  listWeeklyPlans,
  regenerateWeeklyCell,
} from "@/lib/api/weekly";
import { loadClassSettings, primaryClassFor } from "@/lib/onboarding/settings";
import { DAY_NAMES, sectionName } from "@/lib/weekly/section-labels";
import { WorkspacePage, Empty, Message, ws } from "./WorkspaceUI";

/**
 * 주간 서버 경로가 아직 없다 (계약 §14 W5, 하민님).
 *
 * 우리가 낸 404 는 공통 봉투(`{error: {...}}`)를 달고 오고, 아예 없는 경로는 FastAPI 기본
 * `{"detail": "Not Found"}` 다. 그 차이로 가른다. 안 가르면 화면이 「잠시 후 다시
 * 시도해주세요」를 띄우는데, 다시 시도해도 영원히 안 된다 — 교사는 고장으로 읽는다.
 */
const NOT_BUILT_YET = "주간계획안은 아직 서버 준비 중이에요. 월간계획안까지는 지금 쓰실 수 있어요.";
const notBuiltYet = (e: unknown) =>
  e instanceof ApiError &&
  e.status === 404 &&
  !(typeof e.body === "object" && e.body !== null && "error" in e.body);

function describe(e: unknown, fallback: string): string {
  if (notBuiltYet(e)) return NOT_BUILT_YET;
  if (e instanceof ApiError) return e.message;
  return e instanceof Error ? e.message : fallback;
}

const MONTHS = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2];

/**
 * 표시 기간. **서버가 준 `display_end_date` 를 쓴다** — 화면이 토요일을 더하지 않는다 (§3-2).
 * `week_period.end_date` 는 늘 금요일이다. 그걸 그리면 토요일을 켠 원이 하루 모자라게 본다.
 */
function periodText(plan: WeeklyPlan): string {
  const days = plan.operating_days.map((d) => DAY_NAMES[d] ?? d).join(" · ");
  return `${plan.week_period.start_date} ~ ${plan.display_end_date} (${days})`;
}

/**
 * 교사가 적는 칸인가 (가정 연계 · 행사 · 특별활동, §6-2).
 *
 * **응답에 `selection` 이 없어서 칸의 `generation` 으로 가른다.** 만든 적이 없으면 null 이고
 * (§10-2), 교사가 처음 쓰면 `MANUAL` 이 된다. 생성한 칸은 교사가 고쳐도 처음 만든 방식을
 * 그대로 들고 있으므로(`TEACHER_EDITED` 는 이력에만 남는다, §5-3) 둘이 섞이지 않는다.
 *
 * Template 에는 `selection: "INSTITUTION_INPUT"` 로 적혀 있다 — 응답에 그 값이 실리면
 * 이 추론을 지우고 그걸 쓰는 쪽이 낫다 (하민님께 요청해 둔다).
 */
const isTeacherInput = (cell: WeeklyCell) =>
  cell.generation === null || cell.generation.method === "MANUAL";

export default function WeeklyPlanPage() {
  const [classId, setClassId] = useState<number | null>(null);
  const [month, setMonth] = useState(() => new Date().getMonth() + 1);
  /** 그 달 월간계획안. 확정본이어야 주간을 만들 수 있다 (G3). */
  const [monthly, setMonthly] = useState<MonthlyPlan | null>(null);
  const [weekId, setWeekId] = useState("");
  const [plan, setPlan] = useState<WeeklyPlan | null>(null);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [problem, setProblem] = useState("");
  const [drafts, setDrafts] = useState<Record<string, string>>({});

  /** 그 달 월간을 불러온다. 없거나 확정 전이면 null 로 둔다 — 화면이 이유를 말한다. */
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
        const primary = settings && primaryClassFor(settings);
        if (!settings || !primary) throw new Error("반 정보를 먼저 저장해주세요.");
        const id = await syncClass(settings, primary);
        const parent = await loadMonthly(id, month);
        if (!alive) return;
        setClassId(id);
        setMonthly(parent);
        // 달을 바꾸면 고른 주와 띄워 둔 계획안은 다른 달 것이다. 같이 비운다.
        setWeekId("");
        setPlan(null);
        setDrafts({});
      } catch (e) {
        if (alive) setProblem(describe(e, "주간계획안을 불러오지 못했어요."));
      }
    })();
    return () => {
      alive = false;
    };
  }, [loadMonthly, month]);

  /** 고를 수 있는 주. 월간이 정한 활성 주차만이다 — 주간이 주를 다시 세지 않는다 (§3-1). */
  const weeks = useMemo(() => monthly?.weeks.filter((w) => w.active) ?? [], [monthly]);

  /** 주를 고르면 그 주 계획안을 불러온다. 없으면 null — 만들기 단추를 띄운다. */
  useEffect(() => {
    if (classId === null || !weekId || !monthly) return;
    let alive = true;
    (async () => {
      try {
        const { items } = await listWeeklyPlans(classId, month);
        const found = items.find((p) => p.week_id === weekId);
        const next = found ? await getWeeklyPlan(found.id) : null;
        if (!alive) return;
        setPlan(next);
        setDrafts({});
      } catch (e) {
        if (alive) setProblem(describe(e, "그 주를 불러오지 못했어요."));
      }
    })();
    return () => {
      alive = false;
    };
  }, [classId, weekId, monthly, month]);

  const confirmed = plan?.status === "CONFIRMED";
  const sections = useMemo(
    () => (plan?.sections ?? []).filter((s) => s.visible).sort((a, b) => a.order - b.order),
    [plan],
  );

  /**
   * 확정을 막는 이유. 버튼 옆에서 말한다 — 눌러도 서버가 거절할 버튼을 멀쩡히 보여 주면
   * 교사는 고장으로 읽는다.
   */
  const blocked = useMemo(() => {
    if (!plan) return "";
    const theme = sections.find((s) => s.section_key === "theme")?.cells[0];
    if (theme && !theme.value.trim()) return "놀이 주제를 적어야 확정할 수 있어요.";
    return "";
  }, [plan, sections]);

  async function run(key: string, job: () => Promise<WeeklyPlan | void>) {
    setBusy(key);
    setMessage("");
    setProblem("");
    try {
      const next = await job();
      if (next) {
        setPlan(next);
        setDrafts({});
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
      setPlan(null);
      setMessage("지웠어요. 다시 만들 수 있어요.");
    });

  const handleSave = (cell: WeeklyCell) =>
    run(cell.item_id, async () => {
      if (!plan) return;
      const value = drafts[cell.item_id];
      if (value === undefined || value === cell.value) return;
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

  /** 칸 하나. 주간은 Section 마다 칸이 하나라 주차를 따지지 않는다. */
  function Cell({ cell, teacherInput }: { cell: WeeklyCell; teacherInput: boolean }) {
    const value = drafts[cell.item_id] ?? cell.value;
    const working = busy === cell.item_id;
    return (
      <div className={ws.stack}>
        <textarea
          className={ws.input}
          rows={3}
          value={value}
          readOnly={confirmed}
          aria-label="칸 내용"
          onChange={(e) => setDrafts({ ...drafts, [cell.item_id]: e.target.value })}
          onBlur={() => !confirmed && handleSave(cell)}
        />
        {teacherInput ? (
          <span className={ws.hint}>
            교사가 적는 칸이에요. 연간 · 월간에 없는 내용이라 AI 가 만들지 않아요.
          </span>
        ) : (
          cell.state === "EMPTY_UNRESOLVED" && (
            <span className={ws.hint}>근거가 없어 비워 두었어요. 직접 적어주세요.</span>
          )
        )}
        {cell.evidence.length > 0 && (
          <span className={ws.muted}>
            근거 · {cell.evidence.map((e) => e.display_name || e.source_type).join(" · ")}
          </span>
        )}
        {cell.parent_snapshots.length > 0 && (
          <span className={ws.muted}>
            월간에는 · {cell.parent_snapshots.map((s) => s.snapshot_value).join(" · ")}
          </span>
        )}
        {!confirmed && !teacherInput && (
          <button
            type="button"
            className={ws.link}
            disabled={!!busy}
            onClick={() => handleRegenerate(cell)}
          >
            {working ? "…" : "↻ 이 칸만 다시 만들기"}
          </button>
        )}
      </div>
    );
  }

  return (
    <WorkspacePage
      title="주간계획안"
      description="확정한 월간계획안을 바탕으로 한 주 계획을 만들어요. 칸마다 근거를 볼 수 있어요."
    >
      <Message error>{problem}</Message>
      <Message>{message}</Message>

      <div className={ws.row} style={{ marginBottom: 20 }}>
        <label className={ws.field}>
          월
          <select value={month} onChange={(e) => setMonth(Number(e.target.value))}>
            {MONTHS.map((m) => (
              <option key={m} value={m}>
                {m}월
              </option>
            ))}
          </select>
        </label>
        {weeks.length > 0 && (
          <label className={ws.field}>
            주
            <select value={weekId} onChange={(e) => setWeekId(e.target.value)}>
              <option value="">주를 골라주세요</option>
              {weeks.map((w) => (
                <option key={w.week_id} value={w.week_id}>
                  {w.label}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {/* G3 — 월간이 확정돼야 주간을 만든다. 연간은 직접 보지 않는다 (§4-1). */}
      {!monthly && (
        <Empty title={`${month}월 월간계획안을 먼저 확정해주세요`}>
          주간계획안은 확정한 월간계획안을 근거로 만들어요. 「월간계획안」에서 {month}월을 만들고
          확정해주세요.
        </Empty>
      )}

      {monthly && !weekId && (
        <Empty title="어느 주를 만들까요">
          위에서 주를 골라주세요. 주차는 {month}월 월간계획안이 정한 그대로예요.
        </Empty>
      )}

      {monthly && weekId && !plan && (
        <Empty
          title={`${weeks.find((w) => w.week_id === weekId)?.label ?? weekId} 계획안이 아직 없어요`}
        >
          <button
            type="button"
            className={ws.primary}
            disabled={!!busy || classId === null}
            onClick={handleCreate}
          >
            {busy === "create" ? "만드는 중…" : "이 주 계획안 만들기"}
          </button>
        </Empty>
      )}

      {plan && (
        <>
          <div className={ws.between} style={{ marginBottom: 16 }}>
            <div>
              <span className={ws.eyebrow}>{plan.week_id}</span>
              <p className={ws.muted}>{periodText(plan)}</p>
              {plan.parent.theme && <p className={ws.muted}>월간 주제 · {plan.parent.theme}</p>}
            </div>
            <div className={ws.actions}>
              {confirmed ? (
                <span className={ws.badge}>확정됨</span>
              ) : (
                <>
                  <button
                    type="button"
                    className={ws.secondary}
                    disabled={!!busy}
                    onClick={handleDelete}
                  >
                    지우고 다시 만들기
                  </button>
                  <button
                    type="button"
                    className={ws.primary}
                    disabled={!!busy || !!blocked}
                    onClick={handleConfirm}
                  >
                    {busy === "confirm" ? "확정하는 중…" : "확정하기"}
                  </button>
                </>
              )}
            </div>
          </div>
          {!confirmed && blocked && <p className={ws.hint}>{blocked}</p>}

          {plan.verification.findings.length > 0 && (
            <ul className={ws.list} style={{ marginBottom: 16 }}>
              {plan.verification.findings.map((f, i) => (
                <li key={i} className={ws.hint}>
                  {f.message}
                </li>
              ))}
            </ul>
          )}

          <div className={ws.scroll}>
            <table className={ws.grid}>
              <tbody>
                {sections.map((section) => (
                  <tr key={section.section_key}>
                    <th scope="row">{sectionName(section.section_key, section.label)}</th>
                    <td>
                      {section.cells[0] && (
                        <Cell
                          cell={section.cells[0]}
                          teacherInput={isTeacherInput(section.cells[0])}
                        />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </WorkspacePage>
  );
}
