import Link from "next/link";
import type { ReactNode } from "react";
import { Icon } from "@/components/app/icons";

/**
 * 로그인·가입 화면의 틀. 왼쪽은 소개, 오른쪽이 입력 칸이다.
 *
 * 여기만 초록을 쓴다. 디자인 파일이 로그인·가입 화면을 초록으로 그렸다 —
 * 작업실(보라)에 들어가기 전이라는 신호로 읽힌다.
 */
export default function AuthFrame({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-cream px-5 py-6 text-ink sm:px-8">
      <header className="mx-auto flex max-w-[1140px] items-center justify-between gap-3">
        <Link href="/welcome" aria-label="쌤플 소개로" className="flex items-baseline">
          <span className="text-[28px] font-bold tracking-[-0.04em] text-success">
            Ssample<span className="text-peach-strong">.</span>
          </span>
          <span className="ml-3 font-display text-xl text-ink">쌤플</span>
        </Link>
        <Link
          href="/welcome"
          className="flex min-h-11 items-center gap-2 text-xs text-ink-soft hover:text-ink"
        >
          쌤플 소개
          <Icon name="arrow" className="h-4 w-4" />
        </Link>
      </header>

      <main className="mx-auto grid max-w-[1050px] items-center gap-10 py-10 sm:py-16 lg:grid-cols-[1fr_450px] lg:gap-20">
        <section className="hidden lg:block">
          <span className="flex items-center gap-2 text-xs font-medium text-success">
            <Icon name="nature" className="h-4 w-4" />
            선생님의 계획과 기록을 위한 작업실
          </span>
          <h1 className="mt-5 font-display text-[43px] font-bold leading-[1.2] sm:text-[54px]">
            선생님의 하루에,
            <br />
            여유 한 뼘을.
          </h1>
          <p className="mt-5 text-sm leading-[1.9] text-ink-soft">
            아이들과 마주하는 순간에 더 집중할 수 있도록.
            <br />
            계획부터 기록까지, 쌤플이 함께할게요.
          </p>

          <div className="relative mt-9 -rotate-1 border border-note-line bg-note p-6 shadow-pg-hard">
            <span
              aria-hidden="true"
              className="pointer-events-none absolute -top-3 right-10 h-6 w-20 rotate-3 border border-white/60 bg-tape"
            />
            <h2 className="flex items-center gap-2 font-display text-[27px] font-bold text-sun-ink">
              <Icon name="plan" className="h-6 w-6" />
              작은 기록이 모여 큰 성장이 돼요
            </h2>
            <p className="mt-3 text-xs leading-[1.9] text-sun-ink">
              우리 반에 맞는 계획안, 놓치고 싶지 않은 관찰 기록.
              <br />
              차곡차곡 정리되는 문서를 한곳에서 만나보세요.
            </p>
          </div>
        </section>

        <section className="border border-line bg-paper p-6 shadow-pg-hard sm:p-8">
          {children}
        </section>
      </main>
    </div>
  );
}
