import Link from "next/link";
import { Icon, type IconName } from "@/components/app/icons";

const PRIMARY =
  "inline-flex min-h-12 items-center justify-center gap-2 rounded-md border border-primary-line " +
  "bg-primary px-5 text-sm font-semibold text-white shadow-pg-hard transition-colors hover:bg-primary-hover";

const STEPS: { number: string; icon: IconName; title: string; text: string }[] = [
  {
    number: "01",
    icon: "edit",
    title: "본 순간을 남기고",
    text: "아이의 말과 행동을 우리 반 화면에서 바로 한 줄로 적어요.",
  },
  {
    number: "02",
    icon: "plan",
    title: "우리 반 계획을 만들고",
    text: "반 정보와 놀이 주제로 시작해 연간 계획을 만들고 다듬어요.",
  },
  {
    number: "03",
    icon: "doc",
    title: "확인한 문서를 모아요",
    text: "근거 기록을 확인하고, 검토를 마친 계획안을 보관해요.",
  },
];

/** 로그인 전에 보는 소개 화면. 서버를 부르지 않는다 — 정적으로 그려진다. */
export default function LandingPage() {
  return (
    <div className="min-h-screen bg-cream text-ink">
      <header className="mx-auto flex max-w-[1180px] items-center justify-between gap-3 border-b border-line px-5 py-5 sm:px-8">
        <Brand />
        <div className="flex items-center gap-4">
          <Link href="/login" className="flex min-h-11 items-center text-xs font-semibold text-ink">
            로그인
          </Link>
          <Link
            href="/signup"
            className="flex min-h-11 items-center gap-2 text-xs font-medium text-primary"
          >
            시작하기
            <Icon name="arrow" className="h-4 w-4" />
          </Link>
        </div>
      </header>

      <main>
        <section className="mx-auto grid max-w-[1180px] items-center gap-12 px-5 py-14 sm:px-8 sm:py-20 lg:grid-cols-[0.95fr_1.05fr]">
          <div>
            <span className="inline-flex items-center gap-2 rounded-full border border-note-line bg-note-soft px-3 py-2 text-[11px] font-medium text-sun-ink">
              <Icon name="plan" className="h-4 w-4" />
              선생님의 계획과 기록을 위한 작업실
            </span>
            <h1 className="mt-6 font-display text-[46px] font-bold leading-[1.18] sm:text-[62px]">
              쌤의 계획이
              <br />
              쉬워지는 순간,
              <br />
              <span className="text-primary">쌤플.</span>
            </h1>
            <p className="mt-6 max-w-sm text-sm leading-[1.9] text-ink-soft">
              연간 계획부터 우리 반에 맞게.
              <br />
              오늘 본 아이의 말과 행동은 한 줄로 남기고,
              <br />
              모인 기록으로 일지를 준비하세요.
            </p>
            <div className="mt-7 flex flex-wrap items-center gap-5">
              <Link href="/signup" className={PRIMARY}>
                우리 반으로 시작하기
                <Icon name="arrow" className="h-4 w-4" />
              </Link>
              <a
                href="#how-it-works"
                className="min-h-11 py-3 text-xs font-medium text-ink-soft underline underline-offset-4"
              >
                어떻게 쓰나요?
              </a>
            </div>
          </div>

          <div className="relative min-w-0 pb-7 sm:pr-6">
            <PlanPreview />
            <QuickRecordNote />
          </div>
        </section>

        <section id="how-it-works" className="border-y border-line bg-paper">
          <div className="mx-auto max-w-[1180px] px-5 py-12 sm:px-8">
            <div className="mb-8 flex flex-wrap items-end justify-between gap-3">
              <h2 className="font-display text-[30px] font-bold sm:text-[38px]">
                하루의 흐름에 맞춰, 가볍게.
              </h2>
              <span className="text-xs text-ink-soft">쌤이 쓰고, 쌤이 확인하는 문서</span>
            </div>
            <div className="grid gap-8 md:grid-cols-3">
              {STEPS.map((step) => (
                <article key={step.number} className="border-t border-line pt-5">
                  <div className="flex items-center justify-between">
                    <Icon name={step.icon} className="h-8 w-8 text-primary" />
                    <span className="font-display text-2xl text-ink-soft">{step.number}</span>
                  </div>
                  <h3 className="mt-4 text-base font-semibold">{step.title}</h3>
                  <p className="mt-3 text-sm leading-[1.9] text-ink-soft">{step.text}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="mx-auto flex max-w-[1180px] flex-wrap items-center justify-between gap-5 px-5 py-12 sm:px-8">
          <div>
            <h2 className="font-display text-[30px] font-bold sm:text-[37px]">
              우리 반에 맞는 계획, 쌤플.
            </h2>
            <p className="mt-2 text-xs text-ink-soft">반 정보부터 천천히 시작해 보세요.</p>
          </div>
          <Link href="/signup" className={PRIMARY}>
            시작하기
            <Icon name="arrow" className="h-4 w-4" />
          </Link>
        </section>
      </main>

      <footer className="mx-auto flex max-w-[1180px] flex-wrap items-center justify-between gap-3 border-t border-line px-5 py-6 text-[11px] text-ink-soft sm:px-8">
        <span>Ssample · 쌤플</span>
        <span>강원대 2팀 · 카카오테크캠퍼스 4기</span>
      </footer>
    </div>
  );
}

function Brand() {
  return (
    <Link href="/welcome" aria-label="쌤플 소개로" className="flex items-baseline">
      <span className="text-[27px] font-bold tracking-[-0.04em] text-primary-deep">
        Ssample<span className="text-peach-strong">.</span>
      </span>
      <span className="ml-3 font-display text-xl text-ink">쌤플</span>
    </Link>
  );
}

/** 계획 노트가 어떻게 생겼는지 보여주는 예시. 실제 생성 결과가 아니라 소개용 그림이다. */
const PREVIEW_ROWS = [
  { label: "주제", first: "가을이 찾아왔어요", second: "알록달록 가을빛" },
  { label: "자유 놀이", first: "나뭇잎 가게 놀이", second: "자연물로 꾸미기" },
  { label: "바깥 놀이", first: "산책하며 가을 찾기", second: "낙엽 길을 걸어요" },
];

function PlanPreview() {
  return (
    <div className="overflow-hidden rounded-sm border border-line bg-paper shadow-[6px_7px_0_var(--pg-line)]">
      <div className="flex items-center justify-between border-b border-line bg-primary-tint px-5 py-3">
        <span className="text-xs font-semibold text-primary-ink">햇살반의 계획 노트</span>
        <Icon name="plan" className="h-4 w-4 text-primary" />
      </div>
      <div className="p-5 sm:p-6">
        <div className="mb-5 flex items-end justify-between gap-3">
          <h2 className="font-display text-[26px] font-bold sm:text-[31px]">우리 반의 가을</h2>
          <span className="shrink-0 text-[10px] text-ink-soft">10월 · 월간계획안</span>
        </div>
        <table className="w-full text-left text-[11px]">
          <thead>
            <tr className="bg-note-soft">
              <th className="border-b border-line p-3 font-semibold">주차</th>
              <th className="border-b border-line p-3 font-normal">1주</th>
              <th className="border-b border-line p-3 font-normal">2주</th>
            </tr>
          </thead>
          <tbody>
            {PREVIEW_ROWS.map((row) => (
              <tr key={row.label}>
                <th className="border-b border-line py-4 pr-1 text-left font-medium text-ink-soft">
                  {row.label}
                </th>
                <td className="border-b border-line p-3 leading-[1.8]">{row.first}</td>
                <td className="border-b border-line p-3 leading-[1.8]">{row.second}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function QuickRecordNote() {
  return (
    <div className="relative ml-8 mt-[-6px] max-w-[320px] -rotate-2 border border-note-line bg-note p-5 shadow-pg-hard sm:ml-16">
      <span
        aria-hidden="true"
        className="pointer-events-none absolute -top-3 left-1/2 h-6 w-16 -translate-x-1/2 rotate-3 border border-white/60 bg-tape"
      />
      <span className="flex items-center gap-2 text-[11px] font-semibold text-sun-ink">
        <Icon name="edit" className="h-4 w-4" />
        지금, 한 줄 기록
      </span>
      <p className="mt-3 font-display text-[23px] font-bold leading-relaxed text-ink">
        “도토리를 나란히 놓고
        <br />큰 것과 작은 것을 비교했다.”
      </p>
      <span className="mt-3 inline-block rounded bg-paper px-2 py-1 text-[10px] text-sun-ink">
        아이 A · 자연탐구
      </span>
    </div>
  );
}
