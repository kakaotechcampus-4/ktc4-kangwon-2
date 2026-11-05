import Image from "next/image";
import Link from "next/link";
import { LegalFooter } from "@/components/legal/LegalPage";
import { Icon, type IconName } from "@/components/app/icons";
import { Wordmark } from "@/components/app/Wordmark";

/**
 * 로그인 전에 보는 소개 화면(`/welcome`). 서버를 부르지 않는다 — 정적으로 그려진다.
 *
 * 순서는 교사가 묻는 순서다. 무엇을 해 주나(하는 일) → 내 하루 어디에 끼나(흐름) →
 * 글은 누가 쓰나(사실·해석·지원) → 아이 정보는 괜찮나(안심) → 실제로 어떻게 생겼나(화면).
 * 「안심하고 쓰기」를 머리 메뉴에 올려 둔 이유도 같다 — 보육 문서라 그 질문이 먼저 온다.
 */

const PRIMARY =
  "inline-flex min-h-12 items-center justify-center gap-2 rounded-md border border-primary-line " +
  "bg-primary px-5 text-[15px] font-bold text-white shadow-[3px_3px_0_var(--pg-primary-tint-line)] " +
  "transition-colors hover:bg-primary-hover";

/** 첫 화면에서 약속하는 세 가지. 기능이 아니라 **지키는 것**만 적는다. */
const PROMISES = [
  "아이 이름은 AI에 보내지 않아요",
  "선생님이 확정해야 문서가 돼요",
  "한글 파일로 내려받기",
];

const DOES: { icon: IconName; title: string; text: string; items: string[] }[] = [
  {
    icon: "edit",
    title: "기록을 일지 초안으로",
    text: "아이별 관찰 기록은 관찰일지로, 우리 반 일과 기록은 보육일지 초안으로 정리해요.",
    items: [
      "한 줄 기록 · 말로 적기",
      "관찰일지 · 일일 · 주간 보육일지",
      "고친 뒤 확정하고 한글 파일로",
    ],
  },
  {
    icon: "plan",
    title: "연간에서 주간까지 이어지는 계획",
    text: "반 정보와 놀이 주제로 연간계획안을 만들고, 확정한 계획을 바탕으로 월간 · 주간 계획안을 이어서 만들어요.",
    items: [
      "월별 주제형 · 놀이 프로젝트형",
      "칸마다 어디서 왔는지 근거 표시",
      "원에서 쓰던 양식 그대로",
    ],
  },
  {
    icon: "eval",
    title: "평가 준비, 필요한 자료를 한눈에",
    text: "기록과 문서를 지표별로 살펴보고, 추가로 준비할 자료를 확인해요.",
    items: ["지표별 자료 현황", "원에서 쓰던 서류도 등록", "자체점검 체크 보관"],
  },
];

const FLOW: { title: string; text: string; who: "선생님" | "쌤플" }[] = [
  {
    title: "관찰한 내용을 남기고",
    text: "아이의 말과 행동, 우리 반의 하루 일과를 기록해요.",
    who: "선생님",
  },
  {
    title: "초안을 받고",
    text: "작성한 기록으로 일지 초안을 만들어요. 계획안은 반 정보와 놀이 주제로 시작해요.",
    who: "쌤플",
  },
  {
    title: "확인하고 확정해요",
    text: "초안을 읽고 필요한 부분을 고친 뒤 확정해요. 한글 파일로 내려받을 수 있어요.",
    who: "선생님",
  },
];

/** 일지 한 줄이 어디서 왔는지. 1 은 교사가 적은 그대로이고, 2 · 3 만 초안이다. */
const LAYERS = [
  {
    n: "1",
    label: "사실",
    by: "선생님이 적은 그대로",
    text: "바깥놀이에서 아이 A가 도토리를 크기별로 줄 세웠다. 친구가 와서 같이 세웠다.",
    bar: "border-l-sun-ink",
    dot: "bg-sun-ink",
    hand: true,
  },
  {
    n: "2",
    label: "해석",
    by: "초안 · 사실만 근거로",
    text: "도토리를 크기별로 나열하며 사물의 크기를 비교하는 모습을 보였다.",
    bar: "border-l-primary",
    dot: "bg-primary",
    hand: false,
  },
  {
    n: "3",
    label: "지원",
    by: "초안 · 다음 놀이 제안",
    text: "길이나 무게를 기준으로도 비교해 볼 수 있도록 다양한 자연물을 준비한다.",
    bar: "border-l-success",
    dot: "bg-success",
    hand: false,
  },
];

const SAFE: { icon: IconName; title: string; text: string; example?: boolean }[] = [
  {
    icon: "lock",
    title: "이름은 가명으로 바꿔 보내요",
    text: "AI에 보낼 때 아이 이름을 가명으로 바꾸고, 받은 초안에는 원래 이름을 표시해요.",
    example: true,
  },
  {
    icon: "check",
    title: "확정은 선생님이",
    text: "AI가 만든 내용은 초안이에요. 선생님이 검토하고 확정해요.",
  },
  {
    icon: "doc",
    title: "제출은 직접 해요",
    text: "문서를 어디로도 자동으로 제출하거나 보내지 않아요.",
  },
  {
    icon: "record",
    title: "입력한 기록을 근거로",
    text: "관찰일지는 입력한 기록을 바탕으로 만들어요. 투약 · 사고 기록은 AI로 생성하지 않아요.",
  },
];

const FAQ = [
  {
    q: "같은 원 선생님과 함께 쓸 수 있나요?",
    a: "네. 같은 원의 선생님에게 초대 코드를 받아 참여할 수 있어요. 초대 코드는 설정 화면에서 만들 수 있어요.",
  },
  {
    q: "원에서 쓰던 계획안 양식을 쓸 수 있나요?",
    a: "지원하는 양식 파일을 올리면 칸 구조에 맞춰 계획안을 만들 수 있어요. 파일을 올린 뒤 칸이 제대로 인식됐는지 확인해 주세요.",
  },
  {
    q: "AI가 쓴 내용을 그대로 제출해도 되나요?",
    a: "먼저 실제 기록과 맞는지 확인해 주세요. 필요한 부분을 고친 뒤 확정하고 내려받을 수 있어요.",
  },
  {
    q: "아이 이름은 어디에 저장되나요?",
    a: "아이 이름은 쌤플 서버에 저장해요. 브라우저 저장소에는 보관하지 않고, AI에 보낼 때는 가명으로 바꿔요.",
  },
];

export default function LandingPage() {
  return (
    <div className="min-h-[calc(100*var(--app-vh))] bg-cream text-ink">
      <header className="border-b border-line">
        <div className="mx-auto flex min-h-[76px] max-w-[1120px] items-center justify-between gap-4 px-5 sm:px-8">
          <Wordmark href="/welcome" label="쌤플 소개로" />
          <nav aria-label="바로 가기" className="flex items-center gap-3 text-sm sm:gap-5">
            <a href="#does" className="hidden min-h-11 items-center sm:inline-flex">
              하는 일
            </a>
            <a href="#safe" className="hidden min-h-11 items-center sm:inline-flex">
              안심하고 쓰기
            </a>
            <Link href="/login" className="inline-flex min-h-11 items-center whitespace-nowrap">
              로그인
            </Link>
            <Link
              href="/signup"
              className="inline-flex min-h-11 items-center gap-1 whitespace-nowrap font-bold text-primary-ink"
            >
              시작하기
              <Icon name="arrow" className="h-4 w-4" />
            </Link>
          </nav>
        </div>
      </header>

      <main>
        {/* [2] 첫 화면 — 왼쪽은 약속, 오른쪽은 책상 위 종이 두 장 */}
        <section
          aria-labelledby="hero-title"
          className="mx-auto grid max-w-[1120px] items-center gap-12 px-5 pb-16 pt-12 sm:px-8 lg:grid-cols-[1.05fr_1fr] lg:pb-[88px] lg:pt-[72px]"
        >
          <div className="min-w-0">
            <span className="inline-flex items-center gap-2 rounded-full border border-note-line bg-note-soft px-3.5 py-1.5 text-[13px] font-medium">
              만 3~5세 유아반 선생님의 기록과 계획을 위한 작업실
            </span>
            <h1
              id="hero-title"
              className="mt-5 font-display text-[44px] font-bold leading-[1.15] sm:text-[58px] lg:text-[68px]"
            >
              쌤의 계획이
              <br />
              쉬워지는 순간,
              <br />
              <span className="text-primary">쌤플.</span>
            </h1>
            <p className="mt-5 text-base leading-[1.9] text-ink-soft">
              아이의 관찰 기록과 우리 반 일과 기록으로 일지 초안을 만들어요.
              <br className="hidden sm:block" />
              연간부터 월간 · 주간까지, 계획안도 우리 반에 맞게.
            </p>
            <div className="mt-7 flex flex-wrap items-center gap-x-6 gap-y-4">
              <Link href="/signup" className={PRIMARY}>
                우리 반으로 시작하기
                <Icon name="arrow" className="h-4 w-4" />
              </Link>
              <a
                href="#flow"
                className="inline-flex min-h-11 items-center px-1 text-[15px] font-medium underline underline-offset-[5px]"
              >
                어떻게 쓰나요?
              </a>
            </div>
            <ul
              aria-label="쌤플의 약속"
              className="mt-6 flex flex-wrap gap-x-5 gap-y-2 text-[13px] text-ink-soft"
            >
              {PROMISES.map((line) => (
                <li key={line} className="inline-flex items-center gap-1.5">
                  <Icon name="check" className="h-4 w-4 shrink-0 text-success" />
                  {line}
                </li>
              ))}
            </ul>
          </div>

          <div aria-hidden="true" className="relative min-w-0 lg:pb-[190px]">
            <PlanPreview />
            <QuickRecordNote />
          </div>
        </section>

        {/* [3] 하는 일 셋 */}
        <section aria-labelledby="does-title" id="does" className="bg-white py-16 sm:py-[88px]">
          <div className="mx-auto max-w-[1120px] px-5 sm:px-8">
            <SectionHead
              id="does-title"
              title="기록부터 계획, 평가 준비까지"
              note="쌤이 쓰고, 쌤이 확인하는 문서"
            />
            <div className="grid gap-5 md:grid-cols-3">
              {DOES.map((card) => (
                <article
                  key={card.title}
                  className="flex flex-col gap-2.5 border border-line bg-paper p-6 shadow-pg-hard"
                >
                  <span className="grid h-11 w-11 place-items-center rounded-[10px] bg-primary-tint text-primary">
                    <Icon name={card.icon} className="h-[22px] w-[22px]" />
                  </span>
                  <h3 className="text-lg font-semibold leading-[1.5]">{card.title}</h3>
                  <p className="text-sm leading-[1.8] text-ink-soft">{card.text}</p>
                  <ul className="mt-1.5 flex flex-col gap-1.5 border-t border-dashed border-line pt-3 text-[13.5px]">
                    {card.items.map((line) => (
                      <li key={line} className="flex gap-2">
                        <span aria-hidden="true" className="font-bold text-primary">
                          ·
                        </span>
                        {line}
                      </li>
                    ))}
                  </ul>
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* [4] 하루 흐름 — 누가 하는 일인지 칸마다 적는다 */}
        <section aria-labelledby="flow-title" id="flow" className="py-16 sm:py-[88px]">
          <div className="mx-auto max-w-[1120px] px-5 sm:px-8">
            <SectionHead
              id="flow-title"
              title="하루의 흐름에 맞춰, 가볍게."
              note="AI는 초안까지. 마지막 확인은 선생님이 해요."
            />
            <ol className="grid gap-7 md:grid-cols-3 md:gap-0">
              {FLOW.map((step, i) => (
                <li key={step.title} className="relative border-t-2 border-ink pr-7 pt-6">
                  <span
                    aria-hidden="true"
                    className="absolute -top-[18px] left-0 bg-cream pr-2.5 font-display text-[26px] font-bold text-primary"
                  >
                    {`0${i + 1}`}
                  </span>
                  <h3 className="mt-1.5 text-lg font-semibold leading-[1.5]">{step.title}</h3>
                  <p className="mt-2 text-sm leading-[1.8] text-ink-soft">{step.text}</p>
                  <span
                    className={`mt-3 inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                      step.who === "선생님"
                        ? "bg-sun-tint text-sun-ink"
                        : "bg-primary-tint text-primary-ink"
                    }`}
                  >
                    {step.who}
                  </span>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* [5] 사실 · 해석 · 지원 */}
        <section aria-labelledby="journal-title" className="bg-white py-16 sm:py-[88px]">
          <div className="mx-auto grid max-w-[1120px] items-start gap-12 px-5 sm:px-8 lg:grid-cols-[0.9fr_1.1fr]">
            <div className="min-w-0">
              <h2
                id="journal-title"
                className="font-display text-[30px] font-bold leading-[1.2] sm:text-[40px]"
              >
                선생님의 기록을 바탕으로 써요
              </h2>
              <p className="mt-4 text-[15px] leading-[1.85] text-ink-soft">
                관찰한 사실을 바탕으로 해석과 지원 방법을 제안해요. 아래 예시처럼 사실 · 해석 ·
                지원을 구분해 살펴보세요.
              </p>
              <p className="mt-4 border border-peach-strong/40 bg-sun-tint px-4 py-3.5 text-sm leading-[1.8]">
                초안이 실제 기록과 맞는지, 제안한 지원이 우리 반에 적절한지 확인해 주세요.
              </p>
            </div>
            <div aria-label="관찰일지 작성 예시" className="flex min-w-0 flex-col gap-3.5">
              {LAYERS.map((layer) => (
                <div
                  key={layer.n}
                  className={`border border-l-4 border-line bg-paper px-5 pb-4 pt-[18px] ${layer.bar}`}
                >
                  <div className="flex flex-wrap items-center gap-2.5 text-[13px] font-bold">
                    <span
                      className={`grid h-[26px] w-[26px] place-items-center rounded-full text-xs text-white ${layer.dot}`}
                    >
                      {layer.n}
                    </span>
                    {layer.label}
                    <span className="ml-auto text-xs font-medium text-ink-soft">{layer.by}</span>
                  </div>
                  <p
                    className={
                      layer.hand
                        ? "mt-2 font-display text-[19px] leading-[1.45]"
                        : "mt-2 text-[14.5px] leading-[1.8]"
                    }
                  >
                    {layer.text}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* [6] 안심하고 쓰도록 */}
        <section aria-labelledby="safe-title" id="safe" className="py-16 sm:py-[88px]">
          <div className="mx-auto max-w-[1120px] px-5 sm:px-8">
            <SectionHead
              id="safe-title"
              title="아이 정보는 조심스럽게"
              note="보육 문서라서 더 지켜야 하는 것들"
            />
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {SAFE.map((item) => (
                <div key={item.title} className="border border-line bg-paper px-5 py-[22px]">
                  <Icon name={item.icon} className="h-[26px] w-[26px] text-success" />
                  <h3 className="mt-3 text-base font-semibold leading-[1.5]">{item.title}</h3>
                  <p className="mt-1.5 text-[13.5px] leading-[1.8] text-ink-soft">{item.text}</p>
                  {item.example && (
                    <span
                      aria-label="예: 김하늘은 가명 민준으로"
                      className="mt-2.5 inline-flex flex-wrap items-center gap-1.5 text-[12.5px]"
                    >
                      <s className="text-ink-soft">김하늘</s>→
                      <b className="rounded bg-primary-tint px-2 py-0.5 text-primary-ink">민준</b>
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* [7] 실제 화면 — 앱에서 바로 찍은 그림이다. 화면이 바뀌면 같은 이름으로 덮어쓴다. */}
        <section aria-labelledby="screens-title" className="bg-white py-16 sm:py-[88px]">
          <div className="mx-auto max-w-[1120px] px-5 sm:px-8">
            <SectionHead
              id="screens-title"
              title="컴퓨터에서도, 휴대폰에서도"
              note="컴퓨터와 휴대폰에서 같은 반의 기록을 확인해요."
            />
            <div className="grid items-end gap-7 lg:grid-cols-[minmax(0,1fr)_260px]">
              <figure className="m-0 min-w-0">
                <div className="overflow-hidden rounded-[10px] border border-line bg-cream shadow-[0_24px_48px_-28px_rgba(61,52,42,.4)]">
                  <div
                    aria-hidden="true"
                    className="flex gap-1.5 border-b border-line bg-shell px-3 py-2.5"
                  >
                    <i className="h-2.5 w-2.5 rounded-full bg-shell-line" />
                    <i className="h-2.5 w-2.5 rounded-full bg-shell-line" />
                    <i className="h-2.5 w-2.5 rounded-full bg-shell-line" />
                  </div>
                  <Image
                    src="/landing/home-pc.png"
                    alt="쌤플 우리 반 화면 — 왼쪽 메뉴와 한 줄 기록 칸"
                    width={1440}
                    height={900}
                    className="h-auto w-full"
                  />
                </div>
                <figcaption className="mt-3 text-[13px] text-ink-soft">
                  우리 반 — 한 줄 기록과 오늘 적은 내용
                </figcaption>
              </figure>
              <figure className="m-0 mx-auto w-full min-w-0 max-w-[260px]">
                <div className="rounded-[30px] bg-rail p-2 shadow-[6px_6px_0_var(--pg-shell-fold)]">
                  <Image
                    src="/landing/home-phone.png"
                    alt="휴대폰에서 본 쌤플 우리 반 화면"
                    width={390}
                    height={844}
                    className="h-auto w-full rounded-[23px]"
                  />
                </div>
                <figcaption className="mt-3 text-[13px] text-ink-soft">
                  휴대폰 — 같은 기록, 같은 반
                </figcaption>
              </figure>
            </div>
          </div>
        </section>

        {/* [8] 자주 묻는 것 */}
        <section aria-labelledby="faq-title" className="py-16 sm:py-[88px]">
          <div className="mx-auto max-w-[1120px] px-5 sm:px-8">
            <SectionHead id="faq-title" title="자주 묻는 질문" />
            <div className="max-w-[760px]">
              {FAQ.map((row) => (
                <details key={row.q} className="group border-b border-line">
                  <summary className="flex min-h-[60px] cursor-pointer list-none items-center justify-between gap-4 py-3 text-base font-semibold leading-[1.6] [&::-webkit-details-marker]:hidden">
                    {row.q}
                    <span
                      aria-hidden="true"
                      className="shrink-0 font-display text-[26px] text-primary"
                    >
                      <span className="group-open:hidden">+</span>
                      <span className="hidden group-open:inline">–</span>
                    </span>
                  </summary>
                  <p className="mb-5 text-[14.5px] leading-[1.85] text-ink-soft">{row.a}</p>
                </details>
              ))}
            </div>
          </div>
        </section>
      </main>

      {/* [9] 마무리 */}
      <section aria-labelledby="end-title" className="border-t border-line bg-paper">
        <div className="mx-auto flex max-w-[1120px] flex-wrap items-center justify-between gap-5 px-5 py-12 sm:px-8">
          <div>
            <h2 id="end-title" className="font-display text-[30px] font-bold sm:text-[37px]">
              우리 반에 맞는 계획, 쌤플.
            </h2>
            <p className="mt-2 text-sm text-ink-soft">반 정보부터 천천히 시작해 보세요.</p>
          </div>
          <Link href="/signup" className={PRIMARY}>
            시작하기
            <Icon name="arrow" className="h-4 w-4" />
          </Link>
        </div>
      </section>

      <LegalFooter width="max-w-[1120px]" />
    </div>
  );
}

function SectionHead({ id, title, note }: { id: string; title: string; note?: string }) {
  return (
    <div className="mb-10 flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
      <h2 id={id} className="font-display text-[30px] font-bold leading-[1.2] sm:text-[40px]">
        {title}
      </h2>
      {note && <p className="text-sm text-ink-soft">{note}</p>}
    </div>
  );
}

/** 계획안이 어떻게 생겼는지 보여주는 예시. 실제 생성 결과가 아니라 소개용 그림이다. */
const PREVIEW_ROWS = [
  { label: "주제", first: "가을이 찾아왔어요", second: "알록달록 가을빛" },
  { label: "자유 놀이", first: "나뭇잎 가게 놀이", second: "자연물로 꾸미기" },
  { label: "바깥 놀이", first: "산책하며 가을 찾기", second: "낙엽 길을 걸어요" },
];

function PlanPreview() {
  return (
    <div className="ml-auto w-full max-w-[520px] border border-line bg-paper shadow-[6px_6px_0_var(--pg-line)]">
      <div className="flex items-center justify-between bg-primary-tint px-[18px] py-3 text-[13px] font-bold text-primary-ink">
        <span>햇살반 계획안</span>
        <span>초안</span>
      </div>
      <div className="px-[22px] pb-[18px] pt-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <b className="font-display text-[28px] font-bold">우리 반의 가을</b>
          <small className="text-[12.5px] text-ink-soft">10월 · 월간계획안</small>
        </div>
        <table className="mt-3.5 w-full border-collapse text-left text-[13.5px]">
          <thead>
            <tr className="bg-sun-tint">
              <th className="border-b border-line px-2.5 py-2.5 font-bold">주차</th>
              <th className="border-b border-line px-2.5 py-2.5 font-bold">1주</th>
              <th className="border-b border-line px-2.5 py-2.5 font-bold">2주</th>
            </tr>
          </thead>
          <tbody>
            {PREVIEW_ROWS.map((row) => (
              <tr key={row.label}>
                <th className="w-[76px] border-b border-line px-2.5 py-2.5 font-medium text-ink-soft">
                  {row.label}
                </th>
                <td className="border-b border-line px-2.5 py-2.5">{row.first}</td>
                <td className="border-b border-line px-2.5 py-2.5">{row.second}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-2.5 flex flex-wrap gap-1.5 text-[11.5px]">
          <span className="rounded-full bg-success-tint px-2 py-0.5 text-success">
            근거 · 누리과정
          </span>
          <span className="rounded-full bg-success-tint px-2 py-0.5 text-success">
            근거 · 연간계획안 10월
          </span>
        </div>
      </div>
    </div>
  );
}

/** 계획안 종이 위에 겹쳐 둔 쪽지. 낮은 화면에서는 아래로 내려 겹치지 않게 한다. */
function QuickRecordNote() {
  return (
    <div className="relative mt-6 w-full max-w-[330px] -rotate-2 border border-note-line bg-note px-5 pb-4 pt-5 shadow-[4px_4px_0_var(--pg-note-line)] lg:absolute lg:bottom-0 lg:left-0 lg:mt-0 lg:w-[78%]">
      <span
        aria-hidden="true"
        className="pointer-events-none absolute -top-[11px] left-[42%] h-5 w-[74px] -rotate-3 border border-white/60 bg-tape"
      />
      <small className="flex items-center gap-1.5 text-[12.5px] font-semibold text-sun-ink">
        <Icon name="edit" className="h-4 w-4" />
        지금, 한 줄 기록
      </small>
      <p className="my-2 font-display text-[22px] font-bold leading-[1.4]">
        “도토리를 나란히 놓고
        <br />큰 것과 작은 것을 비교했다.”
      </p>
      <span className="inline-block border border-note-line bg-white px-2.5 py-0.5 text-xs">
        아이 A · 자연탐구
      </span>
    </div>
  );
}
