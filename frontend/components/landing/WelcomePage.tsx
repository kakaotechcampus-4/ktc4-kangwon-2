import Image from "next/image";
import Link from "next/link";
import { LegalFooter } from "@/components/legal/LegalPage";
import { Posty } from "@/components/app/Posty";
import { Wordmark } from "@/components/app/Wordmark";
import { FigurePlates } from "./FigurePlates";
import { HeroDevices } from "./HeroDevices";
import { PlanTabs } from "./PlanTabs";
import { TryOneLine } from "./TryOneLine";
import s from "./Welcome.module.css";

/**
 * 로그인 전에 보는 소개 화면(`/welcome`). 서버를 부르지 않는다 — 정적으로 그려진다.
 *
 * 순서: 첫 화면(연간 계획안 실제 화면) → 약속 셋 → 계획안 세 걸음 → 기록 한 줄 써 보기 →
 * 선 그림 여섯 장 → 기록 화면마다 한 판 → 작은 기능 → 어디서나 → 마감.
 * 그림은 전부 운영 화면을 찍은 것이다(멘토용 테스트 계정, 가짜 아이 · 가짜 기록, 아이 이름은 흐림).
 *
 * 옛 소개 화면은 `/welcome/classic` 에 그대로 남겨 두었다.
 */

const PROMISES = [
  {
    title: "아이 이름은 가명으로 보내요",
    text: "AI에 보낼 때만 가명으로 바꾸고, 초안에는 원래 이름이 보여요.",
  },
  {
    title: "확정은 선생님이 해요",
    text: "AI가 만든 건 초안이에요. 읽고 고친 뒤에야 문서가 돼요.",
  },
  {
    title: "한글 파일로 내려받아요",
    text: "원에서 쓰던 양식 그대로 제출할 수 있어요.",
  },
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
    title: "본 그대로, 한 줄이면 충분해요",
    text: "아이와 영역을 고르고 본 장면을 적어요. 상황 · 행동 · 반응 순서로 적으면 일지가 더 잘 나와요.",
    points: ["날짜별로 모이는 기록", "아이마다 다른 표식, 영역마다 다른 색", "아이별로 모아 보기"],
    image: {
      src: "/landing/v2/records.webp",
      width: 1362,
      height: 1434,
      alt: "관찰 기록 화면. 날짜별로 아이, 영역, 본 장면이 쌓여 있다. 아이 이름은 흐리게 가렸다.",
    },
    tone: "plum",
  },
  {
    id: "routines",
    title: "오늘 일과는 칠판에 붙여 두세요",
    text: "날짜를 고르면 그날 일과가 칠판에 쪽지로 붙어요. 시간을 바꾸면 순서대로 정리되고, 겹치는 시간은 알려 줘요.",
    points: [
      "매일 같은 일과는 한 번에 불러오기",
      "일과마다 계획과 실제 모습 기록",
      "그 화면에서 바로 보육일지 쓰기",
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
    title: "일지는 확정한 것만 보관함에",
    text: "보육일지의 사실 칸에는 선생님이 적은 일과가 그대로 들어가요. 초안을 읽고 고친 뒤 확정하면 날짜별로 보관함에 쌓여요.",
    points: [
      "초안 문장마다 근거 기록 연결",
      "확정한 뒤에도 다시 열어 고치기",
      "한글 파일로 내려받기",
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
    title: "한 주를 펼쳐 놓고, 빈 날부터 채워요",
    text: "요일마다 일과와 관찰이 몇 건인지 보여 주고, 기록이 없는 날은 바로 알려 줘요. 주간 보육일지도 이 화면에서 만들어요.",
    points: [
      "한 주 수첩과 그날의 칠판",
      "확정 안 된 일일 보육일지 바로 가기",
      "만들 수 없을 때는 이유 안내",
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
    title: "평가 준비, 지금 무엇이 모였는지",
    text: "평가 지표별로 쌤플에서 만든 문서를 세고, 더 준비할 서류를 알려 줘요. 개수를 센 것이지 내용을 확인한 것은 아니라는 점도 함께 보여 줘요.",
    points: [
      "지표 4-1 · 4-2 · 5-2 · 5-3 서류 현황",
      "내 컴퓨터 폴더는 파일 이름만 확인",
      "부족한 서류는 바로 쓰러 가기",
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
  ["말로 적기", "손이 바쁠 땐 목소리로 한 줄."],
  ["기본 일과 불러오기", "매일 같은 일과는 한 번에 깔아요."],
  ["시간 겹침 알림", "저장하기 전에 먼저 알려 줘요."],
  ["근거 연결", "초안 문장이 어느 기록에서 왔는지 바로 확인해요."],
  ["확정 취소", "확정한 문서도 다시 열어 고칠 수 있어요."],
  ["요청 사항", "계획안을 만들 때 바라는 점을 적어 둘 수 있어요."],
  ["안전교육 배치", "월간 계획안에 안전교육 후보를 주별로 놓아요."],
  ["다른 반 문서 보기", "그 반 담임이 승인하면 읽기만 할 수 있어요."],
];

/**
 * 파일럿 선생님 후기. **받은 문장만 넣는다** — 지어내지 않는다(PRODUCT.md 「Evidence on Hand」).
 * 비어 있으면 후기 칸은 그려지지 않는다.
 */
const VOICES: { quote: string; who: string }[] = [];

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
            <a href="#plans" className={s.navOptional}>
              계획안
            </a>
            <a href="#try" className={s.navOptional}>
              일지
            </a>
            <a href="#features" className={s.navOptional}>
              기록
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
          <h1 id="hero-title" className={s.heroTitle}>
            연간 계획안부터
            <br />
            오늘 보육일지까지
          </h1>
          <p className={s.heroLead}>
            반 정보와 기록을 바탕으로 초안을 먼저 채워 드려요. 선생님은 읽고 고친 뒤 확정만 하면
            돼요.
          </p>
          <div className={s.heroCta}>
            <Link href="/signup" className={s.btn}>
              우리 반으로 시작하기
            </Link>
            <a href="#plans" className={s.textLink}>
              계획안 먼저 보기
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

        <section id="plans" className={s.planSection} aria-labelledby="plans-title">
          <div className={s.wrap}>
            <h2 id="plans-title" className={s.h2}>
              계획안은 연간에서 월간으로 이어져요
            </h2>
            <p className={s.sub}>
              형식을 고르고 연간 계획안을 확정하면, 월간 계획안이 그 주제를 이어받아 만들어져요.
            </p>
            <PlanTabs />
          </div>
        </section>

        <section id="try" className={s.trySection} aria-labelledby="try-title">
          <div className={s.wrap}>
            <h2 id="try-title" className={s.h2}>
              기록 한 줄로 일지를 써 보세요
            </h2>
            <p className={s.sub}>
              적은 문장은 일지의 사실 칸에 그대로 들어가요. 아래 두 줄은 쌤플이 만들어 주는 초안의
              예시예요.
            </p>
            <TryOneLine />
          </div>
        </section>

        <section id="figures" className={s.figures} aria-labelledby="figures-title">
          <div className={s.wrap}>
            <h2 id="figures-title" className={s.h2}>
              쌤플이 기록을 다루는 방식
            </h2>
            <p className={s.sub}>그림 위에 마우스를 올리면 움직여요.</p>
            <FigurePlates />
          </div>
        </section>

        <section id="features" className={s.features} aria-label="기록 화면 둘러보기">
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
              설치하지 않아도 돼요. 브라우저로 열면 같은 반 기록이 그대로 이어져요.
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

        <Voices />

        <section className={s.end} aria-labelledby="end-title">
          <Posty pose="cheer" face="done" size={120} tape label={null} className={s.endPosty} />
          <h2 id="end-title" className={s.endTitle}>
            오늘 본 장면 하나부터 시작해요
          </h2>
          <p className={s.sub}>반을 만들고 아이 이름을 넣으면 바로 쓸 수 있어요.</p>
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

      <div className={s.footer}>
        <LegalFooter width="max-w-[1080px]" />
      </div>
    </div>
  );
}

function FeatureRow({ feature: f, flip }: { feature: Feature; flip: boolean }) {
  const wide = f.image.width > f.image.height * 1.2;
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
      <div className={`${s.panel} ${s[f.tone]} ${wide ? s.wide : ""}`}>
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

function Voices() {
  if (!VOICES.length) return null;
  return (
    <section className={s.voices} aria-label="먼저 써 본 선생님">
      <div className={s.wrap}>
        {VOICES.map((v) => (
          <figure key={v.quote}>
            <blockquote>{v.quote}</blockquote>
            <figcaption>{v.who}</figcaption>
          </figure>
        ))}
      </div>
    </section>
  );
}
