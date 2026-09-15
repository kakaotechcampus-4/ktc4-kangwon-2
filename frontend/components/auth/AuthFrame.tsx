import Link from "next/link";
import type { ReactNode } from "react";

export default function AuthFrame({ children }: { children: ReactNode }) {
  return <main className="min-h-screen bg-cream flex flex-col">
    <header className="px-6 py-4 lg:px-12"><Link href="/login" className="inline-flex items-center gap-2.5 font-display text-xl"><span className="flex h-9 w-9 items-center justify-center rounded-xl bg-sage-tint" aria-hidden="true">🌱</span>쓱싹요정</Link></header>
    <div className="flex-1 flex items-center justify-center px-5 py-6 lg:px-[4vw] lg:py-8">
      <div className="w-full max-w-[1600px] grid lg:grid-cols-2 gap-8 lg:gap-[clamp(32px,5vw,100px)] items-center">
        <section className="hidden lg:block">
          <span className="font-mono text-xs tracking-[.18em] text-sage-ink">A LITTLE GROWTH, EVERY DAY</span>
          <h1 className="font-display text-[clamp(32px,3.3vw,56px)] leading-[1.4] mt-5">선생님의 하루에,<br/>여유 한 뼘을.</h1>
          <p className="text-ink-soft leading-8 xl:text-lg xl:leading-9 mt-5">아이들과 마주하는 순간에 더 집중할 수 있도록.<br/>계획부터 기록까지, 쓱싹요정이 함께할게요.</p>
          <div className="mt-10 rounded-[28px] border border-line bg-sage-tint p-8 xl:p-10">
            <div className="flex items-center gap-3"><span className="text-3xl" aria-hidden="true">🌿</span><span className="font-display text-xl xl:text-2xl">작은 기록이 모여 큰 성장이 돼요</span></div>
            <p className="mt-4 text-sm xl:text-base leading-7 xl:leading-8 text-ink-soft">우리 반에 맞는 계획안, 놓치고 싶지 않은 관찰 기록,<br/>차곡차곡 정리되는 문서를 한곳에서 만나보세요.</p>
          </div>
        </section>
        <section className="w-full max-w-[600px] min-w-0 mx-auto rounded-[28px] border border-line bg-paper p-6 sm:p-8 xl:p-10 shadow-sm">{children}</section>
      </div>
    </div>
    <footer className="text-center text-xs text-ink-soft px-5 pb-4">쓱싹요정 · 선생님의 하루를 잇다</footer>
  </main>;
}
