"use client";
import { ViewTransition, useState, type CSSProperties, type ReactNode } from "react";
import { LegalFooter } from "@/components/legal/LegalPage";
import { Wordmark } from "@/components/app/Wordmark";
import { SCENES } from "@/components/landing/day-scenes";
import LoginDay, { type DayScene } from "./LoginDay";
import s from "./AuthFrame.module.css";

/**
 * 로그인·가입 화면의 틀. 왼쪽은 소개 화면의 「하루」 장면이 시간 따라 넘어가고(LoginDay), 오른쪽은
 * 소개 화면 쪽지 판의 몸통(Ssample. · 구멍 셋) 안 흰 화면에 폼이 들어간다 — 「로그인 공책 시안」 5번.
 *
 * 넓은 화면에서는 지금 장면의 색이 화면 전체 바탕에 깔린다(저녁 장면은 어둡게, 쪽지 판은 밝은 채로).
 * 좁은 화면은 장면을 숨기고 나무 책상 위에 쪽지 판만 남는다. 장면의 h1 은 화면 읽기 프로그램에만 남긴다.
 *
 * 내용은 가운데 1240px 한 덩어리로 모은다 — 넓은 화면에서 좌우 끝에 붙어 가운데가 비지 않게.
 * 큰 모니터(1800px 넘게)에서는 통째로 1.15~1.25배 키운다 — 100% 배율에서 너무 작아 보였다.
 *
 * 로그인 ↔ 회원가입은 다른 주소라 틀이 새로 그려진다. 쪽지 판은 `ViewTransition` 으로 이어 붙여
 * 길이만 부드럽게 바뀌게 하고(globals.css `.auth-sheet`), 장면은 끊기지 않고 이어진다(LoginDay).
 */
export default function AuthFrame({ children }: { children: ReactNode }) {
  const [scene, setScene] = useState<DayScene>(SCENES[0]);
  return (
    <div
      className={`${s.desk} ${scene.night ? s.night : ""} flex min-h-[calc(100*var(--app-vh))] flex-col text-ink`}
      style={{ "--scene-bg": scene.bg } as CSSProperties}
    >
      <div
        className={`${s.scale} mx-auto grid w-full max-w-[1240px] gap-8 px-4 pb-4 pt-6 sm:px-12 lg:grid-cols-[minmax(0,1fr)_440px] lg:gap-20 lg:py-8`}
      >
        <section
          aria-label="쌤플이 하는 일"
          className="relative flex flex-col gap-10 max-lg:sr-only"
        >
          <Wordmark href="/welcome" label="쌤플 소개로" tone={scene.night ? "rail" : "ink"} />
          <h1 className="sr-only">관찰 한 줄을 적으면, 일지 초안이 나와요.</h1>
          <div className="max-lg:hidden">
            <LoginDay onScene={setScene} />
          </div>
        </section>

        <main className="flex flex-col items-center lg:justify-start lg:pt-[76px]">
          <div className="mb-8 w-full max-w-[440px] lg:hidden">
            <Wordmark href="/welcome" label="쌤플 소개로" />
          </div>
          <ViewTransition name="auth-sheet" share="auth-sheet" default="none">
            <div className={`${s.pad} w-full max-w-[440px]`}>
              <div aria-hidden="true" className={s.padTop}>
                <b>
                  Ssample<i>.</i>
                </b>
                <span className={s.holes}>
                  <span />
                  <span />
                  <span />
                </span>
              </div>
              <div className={`${s.screen} px-6 pb-4 pt-7 sm:px-[30px] sm:pb-[18px] sm:pt-[30px]`}>
                {children}
              </div>
            </div>
          </ViewTransition>
        </main>
      </div>
      <div className={`${s.scale} mt-auto`}>
        <LegalFooter width="max-w-[1144px]" />
      </div>
    </div>
  );
}

/**
 * 쪽지 판 화면 안의 분홍 상자 — 로그인 · 가입이 막혔을 때.
 * `alert` 면 화면 읽기 프로그램이 바로 읽는다(폼 오류). 이미 alert 안에 있으면 끈다.
 */
export function ErrorNote({ children, alert = true }: { children: ReactNode; alert?: boolean }) {
  return (
    <p
      role={alert ? "alert" : undefined}
      className="rounded-[10px] border border-alert-soft-line bg-alert-soft px-4 py-3 text-[13px] leading-relaxed text-alert-ink"
    >
      {children}
    </p>
  );
}
