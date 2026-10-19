"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import AppHeader from "@/components/app/AppHeader";
import { getAnnualPlan } from "@/lib/api/plans";
import type { AnnualPlan } from "@/lib/api/types";
import { loadAnnualContext, type AnnualContext } from "@/lib/plan-generator/context";
import GenerationFlow from "./GenerationFlow";
/** 한 번의 조회 결과 — 어떤 요청(key)에 대한 값인지 함께 들고 있어서 id/재시도가 바뀌면 자동으로 무효가 된다. */
interface Loaded {
  key: string;
  plan: AnnualPlan | null;
  context?: AnnualContext;
  error: string;
}

export default function AnnualResult({ id }: { id: number }) {
  const router = useRouter(),
    [retry, setRetry] = useState(0),
    [loaded, setLoaded] = useState<Loaded | null>(null);
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
        if (live) setLoaded({ key, plan, context: loadAnnualContext(id), error: "" });
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
        title="연간계획안"
        description="생성된 계획안을 확인하고 수정·확정해주세요."
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
