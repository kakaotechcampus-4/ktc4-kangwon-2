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
import { deleteMonthlyPlan, getMonthlyPlan, listMonthlyPlans } from "@/lib/api/monthly";
import { listAnnualPlans } from "@/lib/api/plans";
import { classServerId, syncClass } from "@/lib/api/onboarding";
import { getClassTemplateProfile } from "@/lib/api/templateProfiles";
import type { MonthlyPlan, ProfileRef } from "@/lib/api/types";
import { isPlayAnnual } from "@/lib/monthly/play-entry";
import { loadClassSettings } from "@/lib/onboarding/settings";
import { useClientState } from "@/lib/hooks/use-client-state";
import { archivePlanEntry } from "@/lib/workspace/document-archive";
import MonthlyPlanEditor from "./MonthlyPlanEditor";
import MonthlyNew from "./MonthlyNew";
import { WorkspacePage, Message, useClasses, ws } from "./WorkspaceUI";

function describe(e: unknown, fallback: string): string {
  if (e instanceof ApiError) return e.message;
  return e instanceof Error ? e.message : fallback;
}

function readArchiveEntry() {
  return archivePlanEntry(typeof window === "undefined" ? "" : window.location.search);
}
type Entry = NonNullable<ReturnType<typeof archivePlanEntry>>;

/**
 * 주소에 고른 계획안(`plan_id` · `class_id` · `month`)이 있으면 편집, 없으면 만들기(Ⓜ1).
 * 화면을 바꿀 때 주소도 바꿔 둔다 — 새로고침해도 같은 화면이다. 놀이형 초안은 자기 주소로 간다.
 */
export default function MonthlyPlanPage() {
  const [entry, setEntry] = useClientState<Entry | null>(readArchiveEntry, null);
  const go = (next: Entry | null) => {
    window.history.replaceState(
      null,
      "",
      next
        ? `/plans/monthly?plan_id=${next.id}&class_id=${next.classId}&month=${next.month}`
        : "/plans/monthly",
    );
    setEntry(next);
  };
  if (!entry) return <MonthlyNew onOpen={(p) => go({ ...p, weekId: "" })} />;
  return <MonthlyEdit key={entry.id} entry={entry} onBack={() => go(null)} />;
}

function MonthlyEdit({ entry, onBack }: { entry: Entry; onBack: () => void }) {
  const [profile, setProfile] = useState<ProfileRef | null>(null);
  const month = entry.month;
  const [plan, setPlan] = useState<MonthlyPlan | null>(null);
  const [busy, setBusy] = useState<string>("");
  const [message, setMessage] = useState("");
  const [problem, setProblem] = useState("");
  const classes = useClasses(setProblem);
  // 고른 계획안의 반. 문서 보관함 · 만들기 화면 모두 주소로 반을 준다.
  const localClassId = classes.find((c) => classServerId(c.id) === entry.classId)?.id ?? "";
  const scope = `${localClassId}|${month}`;
  const [loadedScope, setLoadedScope] = useState("");
  const [profileSource, setProfileSource] = useState("");
  const [reload, setReload] = useState(0);
  const [isPlay, setIsPlay] = useState(false);
  // 409 로 다시 불러올 때마다 올려 편집 화면을 새로 연다.
  const [version, setVersion] = useState(0);
  const running = useRef(false);
  // 편집 화면의 「열린 입력 저장하고 기다리기」. 못 저장한 칸이 있으면 반 · 월을 옮기지 않는다.
  const flush = useRef<(() => Promise<boolean>) | null>(null);
  // 이동을 기다리는 동안 반 · 월 선택도 잠근다(겹친 이동 방지).
  const [moving, setMoving] = useState(false);
  const leave = async (move: () => void) => {
    if (moving) return;
    setMoving(true);
    try {
      if (!flush.current || (await flush.current())) move();
    } finally {
      setMoving(false);
    }
  };
  const loading = loadedScope !== scope;

  /** 그 달 계획안을 불러온다. 없으면 null 로 둔다 — 화면이 만들기 버튼을 띄운다. */
  const load = useCallback(
    async (id: number, target: number) => {
      const { items } = await listMonthlyPlans(id);
      const found = items.find(
        (p) =>
          p.month === target &&
          (entry.classId !== id || entry.month !== target || p.id === entry.id),
      );
      return found ? await getMonthlyPlan(found.id) : null;
    },
    [entry],
  );

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

  // 지우면 만들기 화면으로 돌아가 그 달을 다시 만든다.
  const handleDelete = () =>
    run("delete", async () => {
      if (!plan) return;
      await deleteMonthlyPlan(plan.id);
      onBack();
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

      <div className={ws.actions} style={{ marginBottom: 16 }}>
        <button
          type="button"
          className={ws.secondary}
          disabled={!!busy || moving}
          onClick={() => void leave(onBack)}
        >
          ← 월간계획안 만들기
        </button>
      </div>

      {loading && <p role="status">월간계획안을 불러오는 중…</p>}
      {!loading && (isPlay || !plan) && (
        <p className={ws.hint}>이 계획안을 찾지 못했어요. 만들기 화면에서 달을 다시 골라 주세요.</p>
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
          flushRef={flush}
          note={
            profile ? `${profileSource} · ${profile.profile_id} / ${profile.profile_version}` : ""
          }
        />
      )}
    </WorkspacePage>
  );
}
