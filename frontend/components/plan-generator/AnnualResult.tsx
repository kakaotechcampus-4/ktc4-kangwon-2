"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import AppHeader from "@/components/app/AppHeader";
import { getAnnualPlan } from "@/lib/api/plans";
import type { AnnualPlanResponse } from "@/lib/api/types";
import { loadAnnualContext, type AnnualContext } from "@/lib/plan-generator/context";
import GenerationFlow from "./GenerationFlow";
import PlayProjectResult from "./PlayProjectResult";
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
  const router = useRouter(),
    [retry, setRetry] = useState(0),
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
  const request = context?.request || {
    age: "mixed" as const,
    ageLabel: "연령 정보 없음",
    selectedTypes: ["annual" as const],
    period: {
      annual: { year: plan?.school_year || new Date().getFullYear() },
      monthly: { month: 3 },
      weekly: { month: 3, week: 1 },
      daily: { date: "" },
    },
    memo: "",
  };
  return (
    <>
      <AppHeader
        title={plan?.format === "PLAY_PROJECT" ? "연간계획안 · 놀이 프로젝트형" : "연간계획안"}
        description={
          plan?.format === "PLAY_PROJECT"
            ? "생성된 놀이 후보를 구간별로 확인해주세요."
            : "생성된 계획안을 확인하고 수정·확정해주세요."
        }
        divider={false}
      />
      {error ? (
        <div className="px-4 lg:px-10">
          <p role="alert">{error}</p>
          <button onClick={() => setRetry((v) => v + 1)}>다시 불러오기</button>
        </div>
      ) : !plan ? (
        <p role="status" className="px-4 lg:px-10">
          계획안을 불러오고 있어요.
        </p>
      ) : plan.format === "PLAY_PROJECT" ? (
        <PlayProjectResult
          key={key + ":" + (current?.version ?? 0)}
          plan={plan}
          notice={current?.notice}
          onConflict={reloadAfterConflict}
          onDismissNotice={dismissNotice}
        />
      ) : (
        <GenerationFlow
          key={id + ":" + retry}
          phase="done"
          stepIndex={4}
          initialConfirmed={plan.status === "CONFIRMED"}
          request={request}
          contents={{
            ...context?.companions,
            annual: {
              annualPlanId: plan.id,
              // 서버가 `source_type` 을 보내지 않아 이 자리는 늘 "template" 이었다.
              // **"ai" 로 바꾸지 않는다.** LLM_MODE 기본이 mock 이라, 그때는 참고자료
              // 라벨을 그대로 베끼고 LLM 이 한 글자도 안 쓴다(`plans/llm.py:114`).
              // 지금 응답에는 `generation` 이 없어서 프런트가 둘을 가를 방법이 없다 —
              // 모르는 것을 단정하지 않고, 쌓여 있는 문서와 같은 값을 그대로 쓴다.
              // #146 이 `generation` 을 실어 오면 그때 method 로 가른다(월간 화면과 같이).
              origin: "template",
              notes: [],
              rows: plan.months.map((m) => ({
                label: m.month + "월",
                title: m.theme,
                detail: m.sub_themes.join("\n"),
              })),
            },
          }}
          classId={context?.classId || ""}
          className={context?.className || ""}
          onBack={() => router.push("/plans/annual/new")}
          onRetry={() => router.push("/plans/annual/new")}
        />
      )}
    </>
  );
}
