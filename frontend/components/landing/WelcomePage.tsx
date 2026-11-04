import Image from "next/image";
import Link from "next/link";
import { LegalFooter } from "@/components/legal/LegalPage";
import { Wordmark } from "@/components/app/Wordmark";
import { FigurePlates } from "./FigurePlates";
import { HeroDevices } from "./HeroDevices";
import s from "./Welcome.module.css";

/**
 * 로그인 전에 보는 소개 화면(`/welcome`). 서버를 부르지 않는다 — 정적으로 그려진다.
 *
 * 짜임은 「조용한 앱 소개」다. 큰 아이콘과 이름 → 실제 화면 두 대 → 약속 세 줄 →
 * 움직이는 그림 여섯 장 → 화면마다 한 판씩 → 작은 기능 → 어디서나 → 아이 정보 → 묻는 것.
 * 그림은 전부 운영 화면을 찍은 것이다(멘토용 테스트 계정, 가짜 아이 · 가짜 기록).
 *
 * 옛 소개 화면은 `/welcome/classic` 에 그대로 남겨 두었다.
 */

const PROMISES = [
  {
    title: "아이 이름은 AI에 보내지 않아요",
    text: "보낼 때 가명으로 바꾸고, 돌아온 초안에서만 되돌려요.",
  },
  {
    title: "선생님이 확정해야 문서가 돼요",
    text: "AI가 만든 건 초안이에요. 읽고 고친 뒤 확정해요.",
  },
  { title: "한글 파일로 내려받아요", text: "확정한 문서는 원에서 쓰던 그대로 제출해요." },
];

type Feature = {
  id: string;
  title: string;
  text: string;
  points: string[];
  image: { src: string; width: number; height: number; alt: string };
  tone: "sage" | "plum" | "note" | "peach" | "warm";
};

const FEATURES: Feature[] = [
  {
    id: "records",
    title: "아이 한 명, 본 대로 한 줄",
    text: "아이와 영역을 고르고 본 장면을 적어요. 상황 · 행동 · 반응 · 교사 지원 순서로 적으면 일지가 잘 나와요.",
    points: [
      "날짜별로 모이는 쌓인 기록",
      "아이마다 붙는 표식과 누리과정 영역 색",
      "아이별 기록 모아 보기",
    ],
    image: {
      src: "/landing/v2/records.webp",
      width: 1362,
      height: 1434,
      alt: "관찰 기록 화면. 날짜별로 아이 이름, 영역, 본 장면이 쌓여 있다.",
    },
    tone: "plum",
  },
  {
    id: "routines",
    title: "하루는 칠판에 쪽지로",
    text: "달력에서 날을 고르면 그날 일과가 칠판에 붙어요. 시간을 바꾸면 순서대로 다시 서고, 겹치면 알려 줘요.",
    points: [
      "매일 같은 하루는 한 번에 깔기",
      "일과마다 계획한 것과 실제 모습",
      "그 자리에서 「오늘 일지 만들기」",
    ],
    image: {
      src: "/landing/v2/routines.webp",
      width: 1323,
      height: 1486,
      alt: "일과 기록 화면. 칠판 위에 등원, 실내놀이, 간식 일과가 쪽지로 붙어 있다.",
    },
    tone: "sage",
  },
  {
    id: "journal",
    title: "적은 사실은 그대로, 문장은 초안으로",
    text: "보육일지의 사실 칸은 선생님이 적은 일과 그대로예요. 초안을 읽고 고친 뒤 확정하면 보관함에 날짜별로 쌓여요.",
    points: [
      "문장마다 어느 기록에서 왔는지 링크",
      "확정한 문서도 풀어서 다시 고치기",
      "한글 파일(hwpx)로 내려받기",
    ],
    image: {
      src: "/landing/v2/journal.webp",
      width: 1600,
      height: 1402,
      alt: "문서 보관함 화면. 한 주의 일일 보육일지가 확정 표시와 함께 놓여 있고, 오른쪽에 10월 29일 일지가 펼쳐져 있다.",
    },
    tone: "note",
  },
  {
    id: "weekly",
    title: "한 주를 펼쳐 놓고, 빈 날부터",
    text: "요일마다 일과와 관찰이 몇 건인지 보여 주고, 비어 있는 날은 비었다고 말해요. 주간 보육일지는 이 화면에서 바로 만들어요.",
    points: [
      "한 주 수첩과 그날의 칠판",
      "아직 확정 안 된 날은 「확정하러 가기」",
      "못 만들 때는 왜인지 알려 줌",
    ],
    image: {
      src: "/landing/v2/weekly.webp",
      width: 1600,
      height: 1025,
      alt: "주간 기록 화면. 왼쪽에 요일별 일과와 관찰 건수, 오른쪽 칠판에 그날 일과 쪽지가 붙어 있다.",
    },
    tone: "peach",
  },
  {
    id: "evaluation",
    title: "평가 때 낼 서류, 오늘 기준으로",
    text: "평가 지표에 맞춰 쌤플에서 만든 문서를 세고, 무엇을 더 쓰면 되는지 알려 줘요. 센 것이 내용까지 확인해 준 것은 아니라고 분명히 적어 둡니다.",
    points: [
      "지표 4-1 · 4-2 · 5-2 · 5-3 서류별 현황",
      "내 컴퓨터 폴더는 파일 이름만 읽기",
      "바로 쓰러 가는 단추",
    ],
    image: {
      src: "/landing/v2/evaluation.webp",
      width: 1600,
      height: 1031,
      alt: "평가 점검 화면. 왼쪽에 「오늘 평가를 받는다면」 요약, 오른쪽에 평가 때 낼 서류 목록이 있다.",
    },
    tone: "warm",
  },
];

const SMALL_THINGS = [
  ["말로 적기", "손이 바쁠 땐 마이크로 한 줄."],
  ["기본 하루 깔기", "매일 같은 일과는 한 번에."],
  ["겹친 시간 알림", "저장하기 전에 먼저 알려 줘요."],
  ["근거 링크", "초안 문장이 어느 기록에서 왔는지."],
  ["확정 취소", "확정한 문서도 다시 열어 고쳐요."],
  ["연간 → 월간 → 주간", "확정한 계획이 다음 계획의 재료로."],
  ["같은 원 선생님", "초대 코드로 함께 써요."],
  ["다른 반 문서", "그 반 담임이 승인하면 보기만."],
];

const SAFETY = [
  [
    "이름은 가명으로",
    "AI에 보낼 때 아이 이름을 가명으로 바꾸고, 받은 초안에는 원래 이름을 표시해요.",
  ],
  ["초안까지만", "AI가 만든 내용은 초안이에요. 선생님이 검토하고 확정해요."],
  ["자동 제출 없음", "문서를 어디로도 자동으로 제출하거나 보내지 않아요."],
  ["입력한 기록을 근거로", "투약 · 사고 기록은 AI로 만들지 않아요."],
];

const FAQ = [
  [
    "같은 원 선생님과 함께 쓸 수 있나요?",
    "네. 같은 원 선생님에게 초대 코드를 받아 참여해요. 다른 반 문서는 그 반 담임이 승인해야 볼 수 있어요.",
  ],
  [
    "원에서 쓰던 계획안 양식을 쓸 수 있나요?",
    "지원하는 양식 파일을 올리면 칸 구조에 맞춰 계획안을 만들어요. 올린 뒤 칸이 제대로 읽혔는지 확인해 주세요.",
  ],
  [
    "AI가 쓴 내용을 그대로 제출해도 되나요?",
    "먼저 실제 기록과 맞는지 확인해 주세요. 고친 뒤 확정하고 내려받을 수 있어요.",
  ],
  [
    "아이 이름은 어디에 저장되나요?",
    "쌤플 서버에 저장해요. 브라우저 저장소에는 두지 않고, AI에 보낼 때는 가명으로 바꿔요.",
  ],
];

const PHONES = [
  ["phone-records", "휴대폰의 관찰 기록 화면"],
  ["phone-routines", "휴대폰의 일과 기록 화면"],
  ["phone-weekly", "휴대폰의 주간 기록 화면"],
];

export default function WelcomePage() {
  return (
    <div className={s.page}>
      <header className={s.nav}>
        <div className={s.navInner}>
          <Wordmark href="/welcome" label="쌤플 소개로" size="sm" />
          <nav aria-label="바로 가기" className={s.navLinks}>
            <a href="#figures" className={s.navOptional}>
              그림으로 보기
            </a>
            <a href="#features" className={s.navOptional}>
              화면
            </a>
            <a href="#safe" className={s.navOptional}>
              아이 정보
            </a>
            <Link href="/login">로그인</Link>
            <Link href="/signup" className={s.navCta}>
              시작하기
            </Link>
          </nav>
        </div>
      </header>

      <main>
        <section className={s.hero} aria-labelledby="hero-title">
          <AppIcon />
          <h1 id="hero-title" className={s.heroTitle}>
            쌤플
          </h1>
          <p className={s.heroTag}>선생님 곁의 조용한 기록장</p>
          <p className={s.heroLead}>
            오늘 본 장면을 한 줄씩 남기면, 일지 초안과 다음 계획이 그 위에 쌓여요.
          </p>
          <div className={s.heroCta}>
            <Link href="/signup" className={s.btn}>
              우리 반으로 시작하기
            </Link>
            <a href="#figures" className={s.textLink}>
              어떻게 움직이는지 보기
            </a>
          </div>
          <HeroDevices />
        </section>

        <section className={s.promises} aria-label="쌤플의 약속">
          <ul>
            {PROMISES.map((p) => (
              <li key={p.title}>
                <strong>{p.title}</strong>
                <span>{p.text}</span>
              </li>
            ))}
          </ul>
        </section>

        <section id="figures" className={s.figures} aria-labelledby="figures-title">
          <div className={s.wrap}>
            <h2 id="figures-title" className={s.h2}>
              한 줄이 문서가 되기까지
            </h2>
            <p className={s.sub}>
              쌤플이 기록을 다루는 방식을 여섯 장의 그림에 담았어요. 그림을 가리키거나 눌러 보세요.
            </p>
            <FigurePlates />
          </div>
        </section>

        <section id="features" className={s.features} aria-label="화면 둘러보기">
          {FEATURES.map((f, i) => (
            <FeatureRow key={f.id} feature={f} flip={i % 2 === 1} />
          ))}
        </section>

        <section className={s.small} aria-labelledby="small-title">
          <div className={s.wrap}>
            <h2 id="small-title" className={s.h2}>
              작은 것까지 챙겼어요
            </h2>
            <dl className={s.smallList}>
              {SMALL_THINGS.map(([t, d]) => (
                <div key={t}>
                  <dt>{t}</dt>
                  <dd>{d}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        <section className={s.where} aria-labelledby="where-title">
          <div className={s.wrap}>
            <h2 id="where-title" className={s.h2}>
              교실에서는 휴대폰, 하원 뒤엔 컴퓨터
            </h2>
            <p className={s.sub}>
              설치 없이 브라우저에서 열어요. 같은 반 기록이 어느 기기에서나 그대로 이어져요.
            </p>
            <div className={s.phones}>
              {PHONES.map(([name, alt]) => (
                <figure key={name} className={s.phoneFrame}>
                  <Image
                    src={`/landing/v2/${name}.webp`}
                    alt={alt}
                    width={780}
                    height={1688}
                    sizes="240px"
                  />
                </figure>
              ))}
            </div>
          </div>
        </section>

        <section id="safe" className={s.safe} aria-labelledby="safe-title">
          <div className={s.wrap}>
            <h2 id="safe-title" className={s.h2}>
              아이 정보는 조심스럽게
            </h2>
            <dl className={s.safeList}>
              {SAFETY.map(([t, d]) => (
                <div key={t}>
                  <dt>{t}</dt>
                  <dd>{d}</dd>
                </div>
              ))}
            </dl>
            <div className={s.faq}>
              <h3 className={s.h3}>자주 묻는 것</h3>
              {FAQ.map(([q, a]) => (
                <details key={q}>
                  <summary>{q}</summary>
                  <p>{a}</p>
                </details>
              ))}
            </div>
          </div>
        </section>

        <section className={s.end} aria-labelledby="end-title">
          <AppIcon />
          <h2 id="end-title" className={s.endTitle}>
            오늘 본 장면 하나부터
          </h2>
          <p className={s.sub}>반 하나 만들고, 아이 이름 몇 개면 바로 써요.</p>
          <div className={s.heroCta}>
            <Link href="/signup" className={s.btn}>
              우리 반으로 시작하기
            </Link>
            <Link href="/login" className={s.textLink}>
              로그인
            </Link>
          </div>
        </section>
      </main>

      <LegalFooter width="max-w-[1080px]" />
    </div>
  );
}

function FeatureRow({ feature: f, flip }: { feature: Feature; flip: boolean }) {
  return (
    <article className={`${s.feature} ${flip ? s.flip : ""}`} aria-labelledby={`f-${f.id}`}>
      <div className={s.featureText}>
        <h3 id={`f-${f.id}`} className={s.featureTitle}>
          {f.title}
        </h3>
        <p>{f.text}</p>
        <ul>
          {f.points.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      </div>
      <div
        className={`${s.panel} ${s[f.tone]} ${f.image.width > f.image.height * 1.2 ? s.wide : ""}`}
      >
        <Image
          className={s.shot}
          src={f.image.src}
          alt={f.image.alt}
          width={f.image.width}
          height={f.image.height}
          sizes="(max-width: 860px) 92vw, 560px"
        />
      </div>
    </article>
  );
}

/** 큰 앱 아이콘. `app/icon.svg` 와 같은 「S.」 를 종이 타일 위에 올렸다. */
function AppIcon() {
  return (
    <span className={s.icon} aria-hidden="true">
      <span className={s.iconS}>
        S<span className={s.iconDot}>.</span>
      </span>
    </span>
  );
}
