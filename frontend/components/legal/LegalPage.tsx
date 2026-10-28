import Link from "next/link";
import type { ReactNode } from "react";

/**
 * 약관·개인정보처리방침처럼 글만 있는 화면의 틀.
 *
 * 로그인 화면에서 바로 닿을 수 있어야 한다. 운영 주체가 누구이고 무엇을 저장하는지
 * 사이트 안에 적혀 있지 않으면, 브라우저는 이메일과 비밀번호를 받는 화면을
 * 피싱으로 의심한다 (Search Console 「사용자 로그인 시 의심되는 피싱」).
 */
export default function LegalPage({
  title,
  updated,
  children,
}: {
  title: string;
  updated: string;
  children: ReactNode;
}) {
  return (
    <div className="min-h-screen bg-cream px-5 py-6 text-ink sm:px-8">
      <header className="mx-auto flex max-w-[760px] items-center justify-between gap-3">
        <Link href="/welcome" aria-label="쌤플 소개로" className="flex items-baseline">
          <span className="text-[27px] font-bold tracking-[-0.04em] text-primary-deep">
            Ssample<span className="text-peach-strong">.</span>
          </span>
          <span className="ml-3 font-display text-xl text-ink">쌤플</span>
        </Link>
      </header>

      <main className="mx-auto mt-8 max-w-[760px] border border-line bg-paper p-6 shadow-pg-hard sm:p-10">
        <h1 className="font-display text-[30px] font-bold sm:text-[37px]">{title}</h1>
        <p className="mt-2 text-[11px] text-ink-soft">{updated} 기준</p>
        <div className="mt-8 space-y-7 text-sm leading-[1.9] text-ink">{children}</div>
      </main>

      <LegalFooter />
    </div>
  );
}

export function LegalSection({ heading, children }: { heading: string; children: ReactNode }) {
  return (
    <section>
      <h2 className="font-display text-[21px] font-bold">{heading}</h2>
      <div className="mt-3 space-y-3 text-ink-soft">{children}</div>
    </section>
  );
}

/** 운영 주체와 두 문서로 가는 길. 랜딩·로그인·약관 화면이 같이 쓴다. */
export function LegalFooter({ width = "max-w-[760px]" }: { width?: string }) {
  return (
    <footer
      className={`mx-auto mt-8 flex ${width} flex-wrap items-center justify-between gap-3 border-t border-line px-1 py-6 text-[11px] text-ink-soft`}
    >
      <span>Ssample · 쌤플 — 강원대 2팀 · 카카오테크캠퍼스 4기</span>
      <span className="flex items-center gap-4">
        <Link href="/privacy" className="hover:text-ink">
          개인정보처리방침
        </Link>
        <Link href="/terms" className="hover:text-ink">
          이용약관
        </Link>
        <a
          href="https://github.com/kakaotechcampus-4/ktc4-kangwon-2"
          target="_blank"
          rel="noreferrer"
          className="hover:text-ink"
        >
          문의
        </a>
      </span>
    </footer>
  );
}
