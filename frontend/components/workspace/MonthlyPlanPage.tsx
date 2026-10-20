"use client";

/**
 * 월간계획안 화면 (FR-303 · docs/api-spec.md §9-1 ~ §9-3).
 *
 * **칸 수를 정하지 않는다.** 주 · Section · 칸은 서버가 준 만큼 그린다. 원마다 양식이
 * 달라서(TemplateProfile) 행도 열도 고정할 수 없다.
 *
 * **revision 을 들고 다닌다.** 편집 · 재생성 · 확정은 읽을 때 받은 `revision` 을
 * `expected_revision` 으로 보낸다. 그 사이 다른 화면에서 바뀌었으면 409 `STALE_WRITE` 다 —
 * 덮어쓰지 않고 다시 불러오라고 말한다.
 *
 * **비어 있어도 확정할 수 있다.** 안전교육처럼 근거가 없어 비는 칸이 있다(§9-1 M4).
 * 규칙도 LLM 도 거기를 지어내지 않는다. 확정 전에 비어 있다는 것만 보여준다.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError } from "@/lib/api/client";
import {
  confirmMonthlyPlan,
  createMonthlyPlan,
  deleteMonthlyPlan,
  editMonthlyCell,
  getMonthlyPlan,
  listMonthlyPlans,
  regenerateMonthlyCell,
} from "@/lib/api/monthly";
import { syncClass } from "@/lib/api/onboarding";
import { getClassTemplateProfile } from "@/lib/api/templateProfiles";
import type { MonthlyCell, MonthlyPlan, ProfileRef } from "@/lib/api/types";
import { loadClassSettings, primaryClassFor } from "@/lib/onboarding/settings";
import { WorkspacePage, Empty, Message, ws } from "./WorkspaceUI";

function describe(e: unknown, fallback: string): string {
  if (e instanceof ApiError) return e.message;
  return e instanceof Error ? e.message : fallback;
}

const MONTHS = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2];

/** 그 달의 「지금」. 3월 시작 학년도라 1 · 2월은 다음 해다. */
function defaultMonth(): number {
  return new Date().getMonth() + 1;
}

export default function MonthlyPlanPage() {
  const [classId, setClassId] = useState<number | null>(null);
  const [profile, setProfile] = useState<ProfileRef | null>(null);
  const [month, setMonth] = useState(defaultMonth);
  const [plan, setPlan] = useState<MonthlyPlan | null>(null);
  const [busy, setBusy] = useState<string>("");
  const [message, setMessage] = useState("");
  const [problem, setProblem] = useState("");
  const [drafts, setDrafts] = useState<Record<string, string>>({});

  /** 그 달 계획안을 불러온다. 없으면 null 로 둔다 — 화면이 만들기 버튼을 띄운다. */
  const load = useCallback(async (id: number, target: number) => {
    const { items } = await listMonthlyPlans(id);
    const found = items.find((p) => p.month === target);
    setPlan(found ? await getMonthlyPlan(found.id) : null);
    setDrafts({});
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const settings = loadClassSettings();
        const primary = settings && primaryClassFor(settings);
        if (!settings || !primary) throw new Error("반 정보를 먼저 저장해주세요.");
        const id = await syncClass(settings, primary);
        const resolution = await getClassTemplateProfile(id);
        await load(id, month);
        if (!alive) return;
        setClassId(id);
        setProfile(resolution.profile_ref);
      } catch (e) {
        if (alive) setProblem(describe(e, "월간계획안을 불러오지 못했어요."));
      }
    })();
    return () => {
      alive = false;
    };
  }, [load, month]);

  const confirmed = plan?.status === "CONFIRMED";
  const weeks = useMemo(() => plan?.weeks.filter((w) => w.active) ?? [], [plan]);
  const sections = useMemo(
    () => (plan?.sections ?? []).filter((s) => s.visible).sort((a, b) => a.order - b.order),
    [plan],
  );

  async function run(key: string, job: () => Promise<MonthlyPlan | void>) {
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
      if (classId === null || !profile) return;
      return createMonthlyPlan({
        class_id: classId,
        month,
        profile_ref: profile,
      });
    });

  const handleDelete = () =>
    run("delete", async () => {
      if (!plan || classId === null) return;
      await deleteMonthlyPlan(plan.id);
      await load(classId, month);
      setMessage("지웠어요. 다시 만들 수 있어요.");
    });

  const handleSave = (cell: MonthlyCell) =>
    run(cell.item_id, async () => {
      if (!plan) return;
      const value = drafts[cell.item_id];
      if (value === undefined || value === cell.value) return;
      return editMonthlyCell(plan.id, cell.item_id, value, plan.revision);
    });

  const handleRegenerate = (cell: MonthlyCell) =>
    run(cell.item_id, async () => {
      if (!plan) return;
      return regenerateMonthlyCell(plan.id, cell.item_id, plan.revision);
    });

  const handleConfirm = () =>
    run("confirm", async () => {
      if (!plan) return;
      const next = await confirmMonthlyPlan(plan.id, plan.revision);
      setMessage("확정했어요. 이제 고칠 수 없어요.");
      return next;
    });

  /** 칸 하나. 한 달짜리 Section 은 주와 상관없이 칸이 하나다. */
  function Cell({ cell }: { cell: MonthlyCell }) {
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
        {cell.state === "EMPTY_UNRESOLVED" && (
          <span className={ws.hint}>근거가 없어 비워 두었어요. 직접 적어주세요.</span>
        )}
        {cell.evidence.length > 0 && (
          <span className={ws.muted}>
            근거 · {cell.evidence.map((e) => e.display_name || e.source_type).join(" · ")}
          </span>
        )}
        {!confirmed && (
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
      title="월간계획안"
      description="확정한 연간계획안을 바탕으로 한 달 계획을 만들어요. 칸마다 근거를 볼 수 있어요."
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
      </div>

      {!profile && (
        <Empty title="월간계획안 양식을 먼저 정해주세요">
          어떤 칸을 둘지 정해야 만들 수 있어요. 「월간계획안 양식」에서 정해주세요.
        </Empty>
      )}

      {profile && !plan && (
        <Empty title={`${month}월 계획안이 아직 없어요`}>
          <button
            type="button"
            className={ws.primary}
            disabled={!!busy || classId === null}
            onClick={handleCreate}
          >
            {busy === "create" ? "만드는 중…" : `${month}월 계획안 만들기`}
          </button>
        </Empty>
      )}

      {plan && (
        <>
          <div className={ws.between} style={{ marginBottom: 16 }}>
            <div>
              <span className={ws.eyebrow}>{plan.target_month}</span>
              {plan.parent.theme && <p className={ws.muted}>연간 주제 · {plan.parent.theme}</p>}
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
                    disabled={!!busy}
                    onClick={handleConfirm}
                  >
                    {busy === "confirm" ? "확정하는 중…" : "확정하기"}
                  </button>
                </>
              )}
            </div>
          </div>

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
              <thead>
                <tr>
                  <th scope="col">구분</th>
                  {weeks.map((w) => (
                    <th key={w.week_id} scope="col">
                      {w.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sections.map((section) => {
                  const byWeek = new Map(section.cells.map((c) => [c.week_id, c]));
                  const whole = section.repeat_by !== "WEEK";
                  return (
                    <tr key={section.section_key}>
                      <th scope="row">{section.label || section.section_key}</th>
                      {whole ? (
                        <td colSpan={Math.max(weeks.length, 1)}>
                          {section.cells[0] && <Cell cell={section.cells[0]} />}
                        </td>
                      ) : (
                        weeks.map((w) => {
                          const cell = byWeek.get(w.week_id);
                          return <td key={w.week_id}>{cell ? <Cell cell={cell} /> : null}</td>;
                        })
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </WorkspacePage>
  );
}
