"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PageContainer } from "@/components/app/AppLayout";
import { Icon } from "@/components/app/icons";
import { listAnnualPlans } from "@/lib/api/plans";
import type { AnnualPlanSummary } from "@/lib/api/types";
import { loadClassSettings, primaryClassFor } from "@/lib/onboarding/settings";
import { AGE_LABEL, type AgeGroup } from "@/lib/plan-generator/types";
import { useClientState } from "@/lib/hooks/use-client-state";

const PRIMARY =
  "inline-flex min-h-11 items-center justify-center gap-2 rounded-md border border-primary-line " +
  "bg-primary px-4 text-xs font-semibold text-white shadow-pg-card transition-colors hover:bg-primary-hover";

/**
 * 계획 노트 — 만들어 둔 계획안을 모아 본다. 만드는 곳은 /plans/annual/new 다.
 *
 * 이 화면이 없으면 사이드바의 「계획 노트」가 곧바로 생성 양식으로 떨어져서,
 * 이미 만든 계획안을 다시 찾을 길이 없다.
 */
export default function PlanNotebookPage() {
  const [plans, setPlans] = useState<AnnualPlanSummary[] | null>(null);
  const [error, setError] = useState("");
  const [room] = useClientState(
    () => {
      const klass = primaryClassFor(loadClassSettings());
      return {
        className: klass?.className ?? "",
        age: klass?.ageGroup ? AGE_LABEL[klass.ageGroup as AgeGroup] : "",
      };
    },
    { className: "", age: "" },
  );

  useEffect(() => {
    const abort = new AbortController();
    listAnnualPlans(undefined, abort.signal)
      .then((data) => setPlans(data.items))
      .catch((e: unknown) => {
        if (abort.signal.aborted) return;
        setPlans([]);
        setError(e instanceof Error ? e.message : "계획안 목록을 불러오지 못했어요.");
      });
    return () => abort.abort();
  }, []);

  const subtitle = [room.className, room.age, "연간부터 주간까지"].filter(Boolean).join(" · ");

  return (
    <PageContainer>
      <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-[34px] font-bold text-ink lg:text-[44px]">계획 노트</h1>
          <p className="mt-1 text-xs text-ink-soft">{subtitle}</p>
        </div>
        {plans && plans.length > 0 && (
          <Link href="/plans/annual/new" className={PRIMARY}>
            <Icon name="plus" className="h-4 w-4" />새 계획안 만들기
          </Link>
        )}
      </div>

      {error && (
        <p role="alert" className="mb-4 rounded-md border border-line bg-paper px-4 py-3 text-xs">
          {error}
        </p>
      )}

      {/* 목록을 받기 전에는 빈 화면을 보여주지 않는다 — 있는 계획안을 없다고 말하게 된다. */}
      {plans === null ? (
        <section className="min-h-[390px] border border-line bg-paper shadow-pg-card" />
      ) : plans.length === 0 ? (
        <EmptyNotebook />
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {plans.map((plan) => (
            <li key={plan.id}>
              <PlanCard plan={plan} />
            </li>
          ))}
        </ul>
      )}
    </PageContainer>
  );
}

function EmptyNotebook() {
  return (
    <section className="flex min-h-[390px] flex-col items-center justify-center border border-line bg-paper px-5 py-12 text-center shadow-pg-hard">
      <span className="flex h-20 w-20 items-center justify-center rounded-[26px_20px_28px_18px] bg-primary-tint text-primary">
        <Icon name="plan" className="h-11 w-11" strokeWidth={1.4} />
      </span>
      <h2 className="mt-6 font-display text-[26px] font-bold text-ink lg:text-[34px]">
        우리 반의 첫 계획을 펼쳐볼까요?
      </h2>
      <p className="mt-3 max-w-md text-sm leading-relaxed text-ink-soft">
        반 정보와 주제를 정하면 초안을 만들 수 있어요.
        <br />
        쌤의 생각을 더하고, 검토한 뒤 보관하세요.
      </p>
      <Link href="/plans/annual/new" className={`${PRIMARY} mt-6`}>
        계획안 만들기
        <Icon name="arrow" className="h-4 w-4" />
      </Link>
    </section>
  );
}

function PlanCard({ plan }: { plan: AnnualPlanSummary }) {
  const confirmed = plan.status === "CONFIRMED";
  return (
    <Link
      href={`/plans/annual/${plan.id}`}
      className="flex h-full flex-col gap-3 rounded-md border border-line bg-paper p-5 shadow-pg-card transition-transform hover:-translate-y-0.5"
    >
      <div className="flex items-start justify-between gap-3">
        <span className="font-display text-[22px] font-bold text-ink">
          {plan.school_year}학년도 연간계획안
        </span>
        <span
          className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] ${
            confirmed ? "bg-sage-tint text-sage-ink" : "bg-sun-tint text-sun-ink"
          }`}
        >
          {confirmed ? "확정" : "초안"}
        </span>
      </div>
      <p className="text-xs text-ink-soft">
        {plan.created_at.slice(0, 10).replace(/-/g, ".")} 만듦
      </p>
      <span className="mt-auto inline-flex items-center gap-1.5 text-xs font-medium text-primary">
        펼쳐 보기
        <Icon name="arrow" className="h-3.5 w-3.5" />
      </span>
    </Link>
  );
}
