"use client";
import { useEffect, useRef, useState } from "react";
import { getAnnualPlan } from "@/lib/api/plans";
import type { AnnualPlanResponse } from "@/lib/api/types";
import { loadAnnualContext, type AnnualContext } from "@/lib/plan-generator/context";
import { AnnualDone } from "./AnnualFrame";
import AnnualThemeSheet from "./AnnualThemeSheet";
import PlayProjectResult, { picksFromPlan } from "./PlayProjectResult";
import PlayProjectSheet from "./PlayProjectSheet";
import { playPageLabels } from "./playProjectPagination";
import ThemeAnnualResult from "./ThemeAnnualResult";
import { useCompactShell } from "@/components/app/compact-shell";
import { loadClassSettings } from "@/lib/onboarding/settings";
import { classServerId } from "@/lib/api/onboarding";

/** 반 설정(온보딩 · 설정에서 적은 반 이름)에서 이 계획안 반의 이름. 상단 띠와 같은 출처. 못 찾으면 빈 값. */
const settingsClassName = (classId: number) =>
  loadClassSettings()?.classes.find((c) => classServerId(c.id) === classId)?.className ?? "";
/** 한 번의 조회 결과 — 어떤 요청(key)에 대한 값인지 함께 들고 있어서 id/재시도가 바뀌면 자동으로 무효가 된다. */
interface Loaded {
  key: string;
  plan: AnnualPlanResponse | null;
  context?: AnnualContext;
  error: string;
  /** 다른 곳에서 바뀌어 다시 불러왔을 때의 안내와, 화면을 새로 그리게 하는 번호. */
  notice?: string;
  version?: number;
}
const STALE_NOTICE = "다른 곳에서 바뀌었어요. 최신 내용을 다시 불러왔어요.";

export default function AnnualResult({ id }: { id: number }) {
  const [retry, setRetry] = useState(0),
    [loaded, setLoaded] = useState<Loaded | null>(null);
  // 저장이 409 로 막히면 최신 계획안으로 바꾼다. 재시도 key 를 올리면 안내를 잃으니 같은 key 로 덮는다.
  // 요청이 겹치면 마지막 요청의 응답만 반영한다 — 늦게 온 옛 응답이 새 응답을 덮으면 과거 revision 으로 돌아간다.
  const lastReload = useRef(0);
  function reloadAfterConflict() {
    const mine = ++lastReload.current;
    const apply = (next: (cur: Loaded | null) => Loaded | null) => {
      if (mine === lastReload.current) setLoaded(next);
    };
    return getAnnualPlan(id).then(
      (fresh) =>
        apply((cur) => ({
          key,
          plan: fresh,
          context: cur?.context,
          error: "",
          notice: STALE_NOTICE,
          version: (cur?.version ?? 0) + 1,
        })),
      () =>
        apply((cur) =>
          cur ? { ...cur, notice: "최신 내용을 불러오지 못했어요. 새로고침해 주세요." } : cur,
        ),
    );
  }
  // 확정이 끝나면 응답 계획안으로 바꾸고 key 를 올려 ⑥ · ⑤ 로 다시 그린다(안내는 비운다).
  const replacePlan = (fresh: AnnualPlanResponse) => {
    ++lastReload.current; // 늦게 온 다시 불러오기 응답이 확정본을 덮지 못하게.
    setLoaded((cur) => ({
      key,
      plan: fresh,
      context: cur?.context,
      error: "",
      version: (cur?.version ?? 0) + 1,
    }));
  };
  const dismissNotice = () =>
    setLoaded((cur) => (cur?.notice ? { ...cur, notice: undefined } : cur));
  const valid = Number.isSafeInteger(id) && id > 0;
  const key = id + ":" + retry;
  const current = loaded?.key === key ? loaded : null;
  const plan = current?.plan ?? null,
    context = current?.context,
    error = valid ? (current?.error ?? "") : "올바른 계획안 주소가 아닙니다.";
  useEffect(() => {
    if (!valid) return;
    const controller = new AbortController();
    let live = true;
    getAnnualPlan(id, controller.signal)
      .then((plan) => {
        if (live)
          setLoaded({
            key,
            plan,
            context: plan.format === "MONTHLY_THEME" ? loadAnnualContext(id) : undefined,
            error: "",
          });
      })
      .catch((e) => {
        if (live && !controller.signal.aborted)
          setLoaded({
            key,
            plan: null,
            error: e instanceof Error ? e.message : "계획안을 불러오지 못했어요.",
          });
      });
    return () => {
      live = false;
      controller.abort();
    };
  }, [id, key, valid]);
  // 확정 전(놀이 고르기 · 다듬기)은 문서 폭을 위해 사이드바를 접는다. 불러오는 동안도 접어 두어
  // 생성 중 → 결과로 넘어올 때 한 번 펼쳤다 접히지 않게 한다. 확정본은 펼친다.
  useCompactShell(!error && plan?.status !== "CONFIRMED");
  const className = context?.className ?? "";
  if (error)
    return (
      <div className="px-4 pt-6 lg:px-10">
        <p role="alert">{error}</p>
        <button onClick={() => setRetry((v) => v + 1)}>다시 불러오기</button>
      </div>
    );
  if (!plan)
    return (
      <p role="status" className="px-4 pt-6 lg:px-10">
        계획안을 불러오고 있어요.
      </p>
    );
  const view = key + ":" + (current?.version ?? 0);
  // 놀이형 문서 제목 「- 햇살반」. 월별 주제형은 위 className(생성 때 남긴 문맥)을 그대로 쓴다.
  const playClassName = plan.format === "PLAY_PROJECT" ? settingsClassName(plan.class_id) : "";
  // 월별 주제형도 문맥이 없으면(보관함에서 열면) 반 설정 이름 — 한글 내려받기 제목은 늘 반 이름을 단다.
  const themeClassName = className || settingsClassName(plan.class_id);
  // ⑥ 확정 후. 놀이 중심형은 원래 문서처럼 두 구간씩 한 쪽(봄·여름 / 가을·겨울), 월별 주제형은 한 쪽이다.
  if (plan.status === "CONFIRMED")
    return (
      <AnnualDone
        key={view}
        plan={plan}
        pageLabels={plan.format === "PLAY_PROJECT" ? playPageLabels(plan.periods) : undefined}
        pages={
          plan.format === "PLAY_PROJECT"
            ? [0, 2].map((i) => (
                <PlayProjectSheet
                  key={i}
                  plan={plan}
                  className={playClassName}
                  picks={picksFromPlan(plan)}
                  periods={[i, i + 1].filter((n) => n < plan.periods.length)}
                  perPage={2}
                />
              ))
            : [
                <AnnualThemeSheet
                  key="annual"
                  title={`${themeClassName ? themeClassName + " " : ""}${plan.school_year}학년도 연간 보육계획안`}
                  months={plan.months}
                />,
              ]
        }
      />
    );
  return plan.format === "PLAY_PROJECT" ? (
    <PlayProjectResult
      key={view}
      plan={plan}
      className={playClassName}
      notice={current?.notice}
      onConflict={reloadAfterConflict}
      onDismissNotice={dismissNotice}
      onConfirmed={replacePlan}
    />
  ) : (
    <ThemeAnnualResult
      key={view}
      plan={plan}
      className={themeClassName}
      notice={current?.notice}
      onConflict={reloadAfterConflict}
      onConfirmed={replacePlan}
    />
  );
}
