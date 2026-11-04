import Link from "next/link";
import { Children, isValidElement, type ReactElement, type ReactNode } from "react";
import { Wordmark } from "@/components/app/Wordmark";
import { LegalToc } from "./LegalToc";
import s from "./Legal.module.css";

/**
 * 약관·개인정보처리방침처럼 글만 있는 화면의 틀.
 *
 * 로그인 화면에서 바로 닿을 수 있어야 한다. 운영 주체가 누구이고 무엇을 저장하는지
 * 사이트 안에 적혀 있지 않으면, 브라우저는 이메일과 비밀번호를 받는 화면을
 * 피싱으로 의심한다 (Search Console 「사용자 로그인 시 의심되는 피싱」).
 *
 * 읽는 화면이라 손글씨는 문서 제목에만 쓰고, 소제목 · 본문은 읽기 쉬운 글꼴로 둔다.
 * 왼쪽 목차는 `LegalSection` 의 제목에서 만든다 — 문서마다 따로 적지 않는다.
 */

const DOCS = [
  { kind: "privacy", href: "/privacy", label: "개인정보처리방침" },
  { kind: "terms", href: "/terms", label: "이용약관" },
] as const;

type SectionProps = { heading: string; children: ReactNode };

/** 「3. 왜 저장하나요」 → 「s-3」. 번호가 없으면 제목 그대로 쓴다. */
function sectionId(heading: string) {
  const n = heading.match(/^(\d+)\./)?.[1];
  return n ? `s-${n}` : `s-${heading.replace(/\s+/g, "-")}`;
}

export default function LegalPage({
  kind,
  title,
  updated,
  summary,
  children,
}: {
  kind: (typeof DOCS)[number]["kind"];
  title: string;
  updated: string;
  /** 제목 아래 「한눈에 보기」. 본문에 이미 있는 약속만 짧게 옮긴다. */
  summary: string[];
  children: ReactNode;
}) {
  const toc = Children.toArray(children)
    .filter(
      (el): el is ReactElement<SectionProps> => isValidElement(el) && el.type === LegalSection,
    )
    .map((el) => ({ id: sectionId(el.props.heading), heading: el.props.heading }));

  return (
    <div className={s.page}>
      <header className={s.top}>
        <div className={s.topInner}>
          <Wordmark href="/welcome" label="쌤플 소개로" size="sm" />
          <nav aria-label="문서 고르기" className={s.switch}>
            {DOCS.map((d) => (
              <Link
                key={d.kind}
                href={d.href}
                aria-current={d.kind === kind ? "page" : undefined}
                className={s.switchItem}
              >
                {d.label}
              </Link>
            ))}
          </nav>
        </div>
      </header>

      <div className={s.layout}>
        <LegalToc items={toc} />

        <main className={s.paper}>
          <div className={s.head}>
            <h1 className={s.title}>{title}</h1>
            <p className={s.updated}>{updated} 기준</p>
            <ul className={s.summary} aria-label="한눈에 보기">
              {summary.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </div>
          <div className={s.body}>{children}</div>
        </main>
      </div>

      <div className={s.footer}>
        <LegalFooter width="max-w-[1080px]" />
      </div>
    </div>
  );
}

export function LegalSection({ heading, children }: SectionProps) {
  const id = sectionId(heading);
  const [, num, rest] = heading.match(/^(\d+)\.\s*(.*)$/) ?? [null, null, heading];
  return (
    <section id={id} className={s.section} aria-labelledby={`${id}-h`}>
      <h2 id={`${id}-h`} className={s.heading}>
        {num && <span className={s.num}>{num}</span>}
        {rest}
      </h2>
      <div className={s.sectionBody}>{children}</div>
    </section>
  );
}

/** 운영 주체와 두 문서로 가는 길. 랜딩·로그인·약관 화면이 같이 쓴다. */
export function LegalFooter({ width = "max-w-[760px]" }: { width?: string }) {
  return (
    <footer
      className={`mx-auto mt-8 flex ${width} flex-wrap items-center justify-between gap-3 border-t border-line px-1 py-6 text-[12px] text-ink-soft`}
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
