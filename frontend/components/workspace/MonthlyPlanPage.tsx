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

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
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
import { sectionName } from "@/lib/monthly/section-labels";
import { chosenClassFor, loadClassSettings } from "@/lib/onboarding/settings";
import { useClientState } from "@/lib/hooks/use-client-state";
import { WorkspacePage, Empty, Message, useClasses, ws } from "./WorkspaceUI";

function describe(e: unknown, fallback: string): string {
  if (e instanceof ApiError) return e.message;
  return e instanceof Error ? e.message : fallback;
}

const MONTHS = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2];
const REGENERATABLE = new Set(["focus", "outdoor_play", "basic_habit", "goals"]);
const FINDINGS: Record<string, string> = {
  ACTIVITY_REFERENCE_NOT_VERIFIED:
    "수정한 내용과 기존 참고 활동의 연결을 자동으로 확인하지 못했어요. 교사가 내용을 확인해주세요.",
  ACTIVITY_FREE_TEXT_AGE_NOT_VERIFIED:
    "직접 작성한 바깥놀이 문장의 연령 적합성은 자동으로 확인하지 못했어요. 교사가 내용을 확인해주세요.",
  ACTIVITY_AGE_UNSUPPORTED:
    "우리 반 연령을 모두 지원하지 않는 참고 활동이 있어요. 활동 내용과 대상 연령을 확인해주세요.",
};

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
  const classes = useClasses(setProblem);
  const [initialClass] = useClientState(() => chosenClassFor(loadClassSettings())?.id ?? "", "");
  const [pickedClass, setPickedClass] = useState<string | null>(null);
  const localClassId = pickedClass ?? (initialClass || classes[0]?.id || "");
  const scope = `${localClassId}|${month}`;
  const [loadedScope, setLoadedScope] = useState("");
  const [profileSource, setProfileSource] = useState("");
  const [reload, setReload] = useState(0);
  const running = useRef(false);
  const loading = loadedScope !== scope;

  /** 그 달 계획안을 불러온다. 없으면 null 로 둔다 — 화면이 만들기 버튼을 띄운다. */
  const load = useCallback(async (id: number, target: number) => {
    const { items } = await listMonthlyPlans(id);
    const found = items.find((p) => p.month === target);
    return found ? await getMonthlyPlan(found.id) : null;
  }, []);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const settings = loadClassSettings();
        const classroom = classes.find((c) => c.id === localClassId);
        if (!settings || !classroom) return;
        const id = await syncClass(settings, classroom);
        const [resolution, next] = await Promise.all([
          getClassTemplateProfile(id),
          load(id, month),
        ]);
        if (!alive) return;
        setClassId(id);
        setProfile(resolution.profile_ref);
        setProfileSource(
          resolution.source === "CLASSROOM_OVERRIDE" ? "반 지정 양식" : "원 기본 양식",
        );
        setPlan(next);
        setLoadedScope(scope);
        setProblem("");
      } catch (e) {
        if (alive) {
          setProblem(describe(e, "월간계획안을 불러오지 못했어요."));
          setLoadedScope(scope);
          setProfile(null);
          setPlan(null);
        }
      }
    })();
    return () => {
      alive = false;
    };
  }, [load, month, localClassId, classes, scope, reload]);

  const confirmed = plan?.status === "CONFIRMED";
  const weeks = useMemo(() => plan?.weeks.filter((w) => w.active) ?? [], [plan]);
  const sections = useMemo(
    () =>
      (plan?.sections ?? [])
        .filter((s) => s.visible && s.role === "CONTENT")
        .sort((a, b) => a.order - b.order),
    [plan],
  );

  async function run(key: string, job: () => Promise<MonthlyPlan | void>) {
    if (running.current || loading) return;
    running.current = true;
    setBusy(key);
    setMessage("");
    setProblem("");
    try {
      const next = await job();
      if (next) {
        setPlan(next);
      }
    } catch (e) {
      setProblem(describe(e, "처리하지 못했어요."));
    } finally {
      running.current = false;
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
      setPlan(await load(classId, month));
      setDrafts({});
      setMessage("지웠어요. 다시 만들 수 있어요.");
    });

  const changed =
    plan?.sections
      .flatMap((s) => s.cells)
      .filter(
        (cell) => drafts[cell.item_id] !== undefined && drafts[cell.item_id] !== cell.value,
      ) ?? [];

  /** Carry forward each returned revision; never discard other unsaved cells. */
  async function saveDrafts(current: MonthlyPlan): Promise<MonthlyPlan> {
    let next = current;
    for (const cell of changed) {
      next = await editMonthlyCell(next.id, cell.item_id, drafts[cell.item_id], next.revision);
      setPlan(next);
      setDrafts((before) => {
        const remaining = { ...before };
        delete remaining[cell.item_id];
        return remaining;
      });
    }
    return next;
  }

  const handleSave = () =>
    run("save", async () => {
      if (!plan) return;
      const next = await saveDrafts(plan);
      setMessage("수정한 내용을 저장했어요.");
      return next;
    });

  const handleRegenerate = (cell: MonthlyCell) =>
    run(cell.item_id, async () => {
      if (!plan) return;
      if (!window.confirm("이 칸을 다시 만들면 현재 내용이 바뀌어요. 계속할까요?")) return;
      const next = await saveDrafts(plan);
      return regenerateMonthlyCell(next.id, cell.item_id, next.revision);
    });

  const handleConfirm = () =>
    run("confirm", async () => {
      if (!plan) return;
      const saved = await saveDrafts(plan);
      const next = await confirmMonthlyPlan(saved.id, saved.revision);
      setMessage("확정했어요. 이제 고칠 수 없어요.");
      return next;
    });

  /** 칸 하나. 한 달짜리 Section 은 주와 상관없이 칸이 하나다. */
  function renderCell(cell: MonthlyCell, sectionKey: string) {
    const value = drafts[cell.item_id] ?? cell.value;
    const working = busy === cell.item_id;
    return (
      <div className={ws.stack}>
        <textarea
          className={ws.input}
          rows={3}
          value={value}
          readOnly={confirmed}
          disabled={!!busy}
          aria-label="칸 내용"
          onChange={(e) => setDrafts((before) => ({ ...before, [cell.item_id]: e.target.value }))}
        />
        {cell.state === "EMPTY_UNRESOLVED" && (
          <span className={ws.hint}>근거가 없어 비워 두었어요. 직접 적어주세요.</span>
        )}
        {cell.evidence.length > 0 && (
          <span className={ws.muted}>
            근거 · {cell.evidence.map((e) => e.display_name || e.source_type).join(" · ")}
          </span>
        )}
        {!confirmed &&
          REGENERATABLE.has(sectionKey) &&
          (plan?.generation_mode !== "RULE_ONLY" || sectionKey === "outdoor_play") && (
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
      {problem && (
        <div className={ws.actions}>
          <button
            type="button"
            className={ws.secondary}
            disabled={!!busy}
            onClick={() => setReload((n) => n + 1)}
          >
            다시 불러오기
          </button>
          <Link href="/plans" className={ws.link}>
            연간계획안 확인하기
          </Link>
        </div>
      )}

      <div className={ws.row} style={{ marginBottom: 20 }}>
        <label className={ws.field}>
          담당 반
          <select
            value={localClassId}
            disabled={!!busy}
            onChange={(e) => {
              if (
                changed.length &&
                !window.confirm("저장하지 않은 수정 내용이 있어요. 반을 바꿀까요?")
              )
                return;
              setDrafts({});
              setPickedClass(e.target.value);
            }}
          >
            {classes.map((c) => (
              <option key={c.id} value={c.id}>
                {c.className}
              </option>
            ))}
          </select>
        </label>
        <label className={ws.field}>
          월
          <select
            value={month}
            disabled={!!busy}
            onChange={(e) => {
              if (
                changed.length &&
                !window.confirm("저장하지 않은 수정 내용이 있어요. 월을 바꿀까요?")
              )
                return;
              setDrafts({});
              setMonth(Number(e.target.value));
            }}
          >
            {MONTHS.map((m) => (
              <option key={m} value={m}>
                {m}월
              </option>
            ))}
          </select>
        </label>
      </div>

      {loading && <p role="status">월간계획안을 불러오는 중…</p>}
      {!loading && profile && (
        <p className={ws.hint}>
          {profileSource} · {profile.profile_id} / {profile.profile_version}
        </p>
      )}
      {!loading && !profile && (
        <Empty title="월간계획안 양식을 먼저 정해주세요">
          어떤 칸을 둘지 정해야 만들 수 있어요. 「월간계획안 양식」에서 정해주세요.
          <Link href="/plans/template" className={ws.link}>
            월간 양식 설정으로 가기
          </Link>
        </Empty>
      )}

      {!loading && profile && !plan && (
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

      {!loading && plan && (
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
                    disabled={!!busy || !changed.length}
                    onClick={handleSave}
                  >
                    {busy === "save" ? "저장하는 중…" : "수정 내용 저장"}
                  </button>
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
          {!confirmed && changed.length > 0 && (
            <p className={ws.hint}>
              저장하지 않은 수정 {changed.length}칸 · 확정할 때도 먼저 저장해요.
            </p>
          )}

          {plan.verification.findings.length > 0 && (
            <ul className={ws.list} style={{ marginBottom: 16 }}>
              {[
                ...new Map(
                  plan.verification.findings.map((finding) => [
                    `${finding.code}|${finding.section_key}`,
                    finding,
                  ]),
                ).values(),
              ].map((f, i) => (
                <li key={i} className={ws.hint}>
                  {FINDINGS[f.code] ?? f.message}
                </li>
              ))}
            </ul>
          )}

          <div className={ws.scroll}>
            <table className={ws.monthlyTable}>
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
                      <th scope="row">{sectionName(section.section_key, section.label)}</th>
                      {whole ? (
                        <td colSpan={Math.max(weeks.length, 1)}>
                          {section.cells[0] && renderCell(section.cells[0], section.section_key)}
                        </td>
                      ) : (
                        weeks.map((w) => {
                          const cell = byWeek.get(w.week_id);
                          return (
                            <td key={w.week_id}>
                              {cell ? renderCell(cell, section.section_key) : null}
                            </td>
                          );
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
