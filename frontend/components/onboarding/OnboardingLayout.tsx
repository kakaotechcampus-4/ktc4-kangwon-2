"use client";

import type { ReactNode } from "react";
import { fontClassName } from "@/lib/fonts";
import OnboardingStepIndicator from "./OnboardingStepIndicator";
import type { OnboardingStep } from "@/lib/onboarding/types";

/**
 * Header(계획안 페이지와 동일) + 진행 표시 + 중앙 온보딩 카드.
 * 페이지 배경은 Main을 아주 옅게 탄 --pg-cream(#F4F8F5), 카드는 흰색.
 */
export default function OnboardingLayout({
  step,
  orgLabel = "🌼 햇살어린이집 · 김민지 선생님", // 가입 시 저장된 값 — 이 화면에서 다시 입력받지 않음
  children,
}: {
  step: OnboardingStep;
  orgLabel?: string;
  children: ReactNode;
}) {
  return (
    <div className={`${fontClassName} min-h-screen font-body bg-cream text-ink`}>
      <header className="flex items-center justify-between px-4 py-3.5 lg:px-8 lg:py-5 border-b border-line">
        <div className="flex items-center gap-2.5 min-w-0">
          <svg width="30" height="30" viewBox="0 0 30 30" aria-hidden="true" className="shrink-0">
            <circle cx="12" cy="15" r="9" className="fill-sage" />
            <circle cx="20" cy="10" r="6" className="fill-sage-ink" />
          </svg>
          <span className="font-display text-xl">새싹플랜</span>
          <span className="hidden lg:inline text-sm ml-1 text-ink-soft">· 시작 설정</span>
        </div>
        <span className="text-sm px-3 py-1.5 rounded-full border border-line bg-paper text-ink-soft max-w-[52vw] lg:max-w-none truncate">{orgLabel}</span>
      </header>

      <main className="max-w-[820px] mx-auto px-4 pt-5 pb-10 lg:px-8 lg:pt-9 lg:pb-16 flex flex-col gap-4 lg:gap-[22px]">
        <OnboardingStepIndicator current={step} />
        <section className="rounded-[20px] lg:rounded-[24px] border border-line bg-paper shadow-pg px-[18px] py-[22px] lg:px-10 lg:py-9 flex flex-col gap-6 lg:gap-7">
          {children}
        </section>
      </main>
    </div>
  );
}

/** 각 단계 상단의 제목/설명 블록 */
export function StepHeading({ title, description, eyebrow }: { title: string; description: string; eyebrow?: ReactNode }) {
  return (
    <div>
      {eyebrow}
      <h1 className={`font-display text-[21px] lg:text-2xl text-ink ${eyebrow ? "mt-3" : ""}`} style={{ textWrap: "balance" }}>
        {title}
      </h1>
      <p className="mt-2 text-[14.5px] leading-relaxed text-ink-soft">{description}</p>
    </div>
  );
}

/** 하단 [이전] [다음] 영역 — 모바일에서는 다음 버튼이 넓게 늘어난다 */
export function StepFooter({ left, right, note }: { left?: ReactNode; right: ReactNode; note?: ReactNode }) {
  return (
    <div className="flex items-center gap-3 pt-[22px] mt-1 border-t border-line flex-wrap">
      {left}
      <span className="flex-1" />
      {note && <span className="hidden lg:inline text-[12.5px] text-ink-soft">{note}</span>}
      {right}
    </div>
  );
}
