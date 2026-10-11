"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { fontClassName } from "@/lib/fonts";
import OnboardingStepIndicator from "./OnboardingStepIndicator";
import type { OnboardingStep } from "@/lib/onboarding/types";

/**
 * 시작 설정(온보딩)의 틀. 브랜드 머리 + 진행 표시 + 종이 한 장.
 * 카드를 둥글리지 않고 각진 그림자를 둔다 — 책상에 올려 둔 종이처럼 보이게.
 */
export default function OnboardingLayout({
  step,
  children,
}: {
  step: OnboardingStep;
  children: ReactNode;
}) {
  return (
    <div className={`${fontClassName} min-h-screen bg-cream px-5 py-6 font-body text-ink sm:px-8`}>
      <header className="mx-auto flex max-w-[1000px] items-center justify-between gap-3">
        <Link href="/welcome" aria-label="쌤플 소개로" className="flex items-baseline">
          <span className="text-[27px] font-bold tracking-[-0.04em] text-primary-deep">
            Ssample<span className="text-peach-strong">.</span>
          </span>
          <span className="ml-3 font-display text-xl text-ink">쌤플</span>
        </Link>
        <span className="text-xs text-ink-soft">시작 설정</span>
      </header>

      <main className="mx-auto max-w-[820px] py-9 sm:py-12">
        <div className="mb-7">
          <OnboardingStepIndicator current={step} />
        </div>
        <section className="relative border border-line bg-paper p-6 shadow-pg-hard sm:p-9">
          <span
            aria-hidden="true"
            className="pointer-events-none absolute -top-3 right-10 h-6 w-20 rotate-3 border border-white/60 bg-tape"
          />
          <div className="flex flex-col gap-6 lg:gap-7">{children}</div>
        </section>
      </main>
    </div>
  );
}

/** 각 단계 상단의 제목/설명 블록 */
export function StepHeading({
  title,
  description,
  eyebrow,
}: {
  title: string;
  description: string;
  eyebrow?: ReactNode;
}) {
  return (
    <div>
      {eyebrow}
      <h1
        className={`font-display text-[26px] font-bold text-ink lg:text-[32px] ${eyebrow ? "mt-3" : ""}`}
        style={{ textWrap: "balance" }}
      >
        {title}
      </h1>
      <p className="mt-2 text-[14.5px] leading-relaxed text-ink-soft">{description}</p>
    </div>
  );
}

/** 하단 [이전] [다음] 영역 — 모바일에서는 다음 버튼이 넓게 늘어난다 */
export function StepFooter({
  left,
  right,
  note,
}: {
  left?: ReactNode;
  right: ReactNode;
  note?: ReactNode;
}) {
  return (
    <div className="mt-1 flex flex-wrap items-center gap-3 border-t border-line pt-[22px]">
      {left}
      <span className="flex-1" />
      {note && <span className="hidden text-[12.5px] text-ink-soft lg:inline">{note}</span>}
      {right}
    </div>
  );
}
