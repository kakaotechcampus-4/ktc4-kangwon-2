"use client";

/**
 * 월간계획안 화면 (FR-303 · docs/api-spec.md §9-1 ~ §9-3).
 *
 * **칸 수를 정하지 않는다.** 주 · Section · 칸은 서버가 준 만큼 그린다. 원마다 양식이
 * 달라서(TemplateProfile) 행도 열도 고정할 수 없다.
 *
 * **revision 을 들고 다닌다.** 편집 · 재생성 · 확정은 읽을 때 받은 `revision` 을
 * `expected_revision` 으로 보낸다. 그 사이 다른 화면에서 바뀌었으면 409 `STALE_WRITE` 다 —
 * 덮어쓰지 않고 최신 계획안을 다시 불러온다. 편집 화면은 놀이 월간과 같다(MonthlyPlanEditor).
 *
 * **비어 있어도 확정할 수 있다.** 안전교육처럼 근거가 없어 비는 칸이 있다(§9-1 M4).
 * 규칙도 LLM 도 거기를 지어내지 않는다. 확정 전에 비어 있다는 것만 보여준다.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ApiError } from "@/lib/api/client";
import {
  createMonthlyPlan,
  deleteMonthlyPlan,
  getMonthlyPlan,
  listMonthlyPlans,
} from "@/lib/api/monthly";
import { listAnnualPlans } from "@/lib/api/plans";
import { syncClass } from "@/lib/api/onboarding";
import { getClassTemplateProfile } from "@/lib/api/templateProfiles";
import type { MonthlyPlan, ProfileRef } from "@/lib/api/types";
import { isPlayAnnual } from "@/lib/monthly/play-entry";
import { chosenClassFor, loadClassSettings } from "@/lib/onboarding/settings";
import { useClientState } from "@/lib/hooks/use-client-state";
import MonthlyPlanEditor from "./MonthlyPlanEditor";
import PlayMonthlyEntry from "./PlayMonthlyEntry";
import { WorkspacePage, Empty, Message, useClasses, ws } from "./WorkspaceUI";

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
  const classes = useClasses(setProblem);
  const [initialClass] = useClientState(() => chosenClassFor(loadClassSettings())?.id ?? "", "");
  const [pickedClass, setPickedClass] = useState<string | null>(null);
  const localClassId = pickedClass ?? (initialClass || classes[0]?.id || "");
  const scope = `${localClassId}|${month}`;
  const [loadedScope, setLoadedScope] = useState("");
  const [profileSource, setProfileSource] = useState("");
  const [reload, setReload] = useState(0);
  const [isPlay, setIsPlay] = useState(false);
  // 409 로 다시 불러올 때마다 올려 편집 화면을 새로 연다.
  const [version, setVersion] = useState(0);
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
        // 놀이형 분기. 연간 목록을 못 읽으면 기존 화면으로 둔다.
        const annual = await listAnnualPlans(id).catch(() => null);
        if (isPlayAnnual(annual)) {
          if (!alive) return;
          setIsPlay(true);
          setClassId(id);
          setLoadedScope(scope);
          setProblem("");
          return;
        }
        const [resolution, next] = await Promise.all([
          getClassTemplateProfile(id),
          load(id, month),
        ]);
        if (!alive) return;
        setIsPlay(false);
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
          setIsPlay(false);
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

  const legacy = !loading && !isPlay;

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
      setMessage("지웠어요. 다시 만들 수 있어요.");
    });

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
      {!loading && isPlay && classId !== null && (
        <PlayMonthlyEntry key={`${classId}|${month}`} classId={classId} month={month} />
      )}
      {legacy && !profile && (
        <Empty title="월간계획안 양식을 먼저 정해주세요">
          어떤 칸을 둘지 정해야 만들 수 있어요. 「월간계획안 양식」에서 정해주세요.
          <Link href="/plans/template" className={ws.link}>
            월간 양식 설정으로 가기
          </Link>
        </Empty>
      )}

      {legacy && profile && !plan && (
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

      {legacy && plan && (
        <MonthlyPlanEditor
          key={plan.id + ":" + version}
          plan={plan}
          onPlan={setPlan}
          onConflict={() => {
            setVersion((v) => v + 1);
            setReload((n) => n + 1);
            setMessage("다른 곳에서 바뀌었어요. 최신 내용을 다시 불러왔어요.");
          }}
          onDelete={handleDelete}
          note={
            profile ? `${profileSource} · ${profile.profile_id} / ${profile.profile_version}` : ""
          }
        />
      )}
    </WorkspacePage>
  );
}
