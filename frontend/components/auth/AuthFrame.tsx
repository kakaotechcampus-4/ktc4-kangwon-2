"use client";
import Link from "next/link";
import type { ReactNode } from "react";
import { Icon } from "@/components/app/icons";
import { Posty } from "@/components/app/Posty";
import { LegalFooter } from "@/components/legal/LegalPage";
import { Wordmark } from "@/components/app/Wordmark";
import { useHydrated } from "@/lib/hooks/use-client-state";
import s from "./AuthFrame.module.css";

/**
 * 로그인·가입 화면의 틀. 나무 틀 칠판 하나에, 왼쪽은 분필 인사 · 오른쪽은 공책 종이 한 장.
 *
 * 칠판 왼쪽(`greeting` · `todo`)은 화면에 들어올 때 한 덩어리로 떠오른다. 종이 위 입력은
 * 작업실과 같은 보라 단추 · 흰 칸이다 — 로그인 뒤 화면과 결이 이어지게.
 */
export default function AuthFrame({
  greeting,
  todo,
  aside,
  children,
}: {
  /** 칠판에 분필로 쓴 인사. 화면의 h1 이다. */
  greeting: ReactNode;
  /** 칠판 아래쪽 할 일 목록 (회원가입만) */
  todo?: ReactNode;
  /** 종이 가장자리에 붙는 쪽지 — 로그인 ↔ 회원가입 */
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="min-h-[calc(100*var(--app-vh))] bg-cream px-4 py-6 text-ink sm:px-8">
      <header className="mx-auto flex max-w-[1180px] items-center justify-between gap-3">
        <Wordmark href="/welcome" label="쌤플 소개로" />
        <Link
          href="/welcome"
          className="flex min-h-11 items-center gap-2 text-xs text-ink-soft hover:text-ink"
        >
          쌤플 소개
          <Icon name="arrow" className="h-4 w-4" />
        </Link>
      </header>

      <main className="mx-auto max-w-[1180px] pb-6 pt-6 sm:pt-10">
        <div className={s.frame}>
          <div
            className={`${s.board} grid gap-6 px-3 pb-24 pt-6 sm:px-8 lg:grid-cols-[1fr_420px] lg:items-center lg:gap-12 lg:px-14 lg:pb-16 lg:pt-12`}
          >
            <section className={`${s.fadeIn} px-2 sm:px-0`}>
              <Today />
              <h1
                className="mt-3 font-display text-[30px] font-bold leading-[1.25] lg:mt-4 lg:text-[48px]"
                style={{ wordBreak: "keep-all", wordSpacing: "-0.15em" }}
              >
                {greeting}
              </h1>
              <p className="mt-3 hidden max-w-[380px] text-sm leading-[1.8] text-board-ink-soft lg:block">
                아이들과 마주하는 순간에 더 집중할 수 있도록. 계획부터 기록까지, 쌤플이 함께할게요.
              </p>
              {todo && <div className="hidden lg:block">{todo}</div>}
            </section>

            <div className="relative">
              <div className="relative">
                <div aria-hidden="true" className={s.under} />
                <div aria-hidden="true" className={s.under} />
                <section className={`${s.sheet} py-7 pl-11 pr-5 sm:py-10 sm:pl-[60px] sm:pr-9`}>
                  <span aria-hidden="true" className={s.tape} />
                  <span aria-hidden="true" className={s.tape} />
                  <div className="text-ink">{children}</div>
                </section>
              </div>
              {aside}
            </div>
          </div>
          <Posty
            pose="wave"
            wave
            tape
            size={78}
            label="포스티가 인사해요"
            className={`${s.posty} absolute bottom-1 right-6 z-[3] h-auto w-[58px] lg:left-16 lg:right-auto lg:w-[78px]`}
          />
          <div aria-hidden="true" className={s.tray}>
            <b className="left-5 lg:left-44" />
            <i className="left-20 lg:left-60" />
            <i className="left-[110px] lg:left-[272px]" />
          </div>
        </div>
      </main>

      <LegalFooter width="max-w-[1180px]" />
    </div>
  );
}

/**
 * 칠판 맨 위 날짜. 보는 사람의 시계로 쓴다 — 서버 렌더에서 그리면 서버 시간대 날짜가 나와
 * hydration 이 어긋나므로 브라우저에 닿은 뒤에 쓴다.
 */
function Today() {
  const hydrated = useHydrated();
  if (!hydrated) return <p className="h-7" aria-hidden="true" />;
  const d = new Date();
  return (
    <p className="flex h-7 items-center gap-2.5 font-display text-[19px] font-bold text-board-ink-soft lg:text-[24px]">
      {d.getMonth() + 1}월 {d.getDate()}일
      <span className="rounded-[50%] border-2 border-alert px-2.5">
        {"일월화수목금토"[d.getDay()]}요일
      </span>
    </p>
  );
}
