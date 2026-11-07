"use client";
import { ViewTransition, useEffect, useState, type ReactNode } from "react";
import { Posty } from "@/components/app/Posty";
import { LegalFooter } from "@/components/legal/LegalPage";
import { Wordmark } from "@/components/app/Wordmark";
import s from "./AuthFrame.module.css";

/**
 * 로그인·가입 화면의 틀. 나무 책상 위에, 왼쪽은 쌤플이 하는 일 한 장면 · 오른쪽은 스프링 공책 한 장.
 *
 * 내용은 가운데 1240px 한 덩어리로 모은다 — 넓은 화면에서 좌우 끝에 붙어 가운데가 비지 않게.
 * 좁은 화면에서는 장면을 숨기고 공책만 남는다. 장면의 h1 은 화면 읽기 프로그램에는 남긴다.
 *
 * 로그인 ↔ 회원가입은 다른 주소라 틀이 새로 그려진다. 공책은 `ViewTransition` 으로 이어 붙여
 * 길이만 부드럽게 바뀌게 하고(globals.css `.auth-sheet`), 장면은 처음 한 번만 돌린다.
 */
let scenePlayed = false;

export default function AuthFrame({ children }: { children: ReactNode }) {
  return (
    <div className={`${s.desk} min-h-[calc(100*var(--app-vh))] text-ink`}>
      <div className="mx-auto grid max-w-[1240px] gap-8 px-4 pb-4 pt-6 sm:px-12 lg:min-h-[calc(100*var(--app-vh)-80px)] lg:grid-cols-[minmax(0,1fr)_440px] lg:gap-20 lg:py-8">
        <section
          aria-label="쌤플이 하는 일"
          className="relative flex flex-col gap-10 max-lg:sr-only"
        >
          <span aria-hidden="true" className={s.mug} />
          <Pencil />
          <Wordmark href="/welcome" label="쌤플 소개로" />
          <div className="mt-[72px] flex flex-col gap-10">
            <IntroCopy />
            <Scene />
          </div>
        </section>

        <main className="flex flex-col items-center lg:justify-start lg:pt-[76px]">
          <div className="mb-8 w-full max-w-[440px] lg:hidden">
            <Wordmark href="/welcome" label="쌤플 소개로" />
          </div>
          <ViewTransition name="auth-sheet" share="auth-sheet" default="none">
            <div
              className={`${s.sheet} w-full max-w-[440px] py-10 pl-14 pr-6 sm:pb-8 sm:pl-16 sm:pr-10 sm:pt-11`}
            >
              <span aria-hidden="true" className={s.ring} />
              {children}
            </div>
          </ViewTransition>
        </main>
      </div>
      <LegalFooter width="max-w-[1144px]" />
    </div>
  );
}

function IntroCopy() {
  return (
    <div>
      <h1 className="font-display text-[clamp(32px,3vw,40px)] font-bold leading-[1.22]">
        관찰 한 줄을 적으면,
        <br />
        일지 초안이 나와요.
      </h1>
      <p className="mt-4 max-w-[420px] text-[15px] leading-[1.75] text-ink-soft [word-break:keep-all]">
        적은 관찰은 그대로 두고, 해석과 지원만 쪽지로 붙여요. 일지에 넣을지는 선생님이 골라요.
      </p>
    </div>
  );
}

/** 선생님이 공책에 적은 한 줄 위로 해석 · 지원 쪽지가 붙는다. 그림이라 읽기 프로그램에는 숨긴다 */
function Scene() {
  // 같은 탭에서 두 번째로 그릴 때(로그인 ↔ 회원가입)는 끝난 모습으로 바로 둔다
  const [still] = useState(() => scenePlayed);
  useEffect(() => {
    scenePlayed = true;
  }, []);
  return (
    <div aria-hidden="true" className={`relative max-w-[560px] pb-3 ${still ? s.still : ""}`}>
      <span className={s.posty}>
        <Posty pose="point" tape size={56} label={null} className={s.postyBefore} />
        <Posty pose="cheer" face="done" tape size={56} label={null} className={s.postyAfter} />
      </span>
      <div className={s.book}>
        <span className={s.ring} />
        <p className="flex gap-3 text-xs text-ink-soft">
          <b className="font-bold text-ink">관찰 기록 예시</b>
          <span>9월 22일 바깥놀이</span>
          <span>자연탐구</span>
        </p>
        <p className={`${s.ruled} text-[15px]`}>
          <TypingObservation still={still} />
        </p>
      </div>
      <div className="-mt-3 ml-9 mr-3 grid grid-cols-2 gap-4">
        <Note title="해석" sub="근거 · 관찰 1건" tone="border-note-line bg-note">
          개미의 움직임에 관심을 보이며 한자리에서 오래 지켜보았다.
        </Note>
        <Note title="지원" sub="다음 바깥놀이 때" tone="border-plum-line bg-plum">
          화단 근처에 돋보기와 곤충 그림책을 두어 다른 곤충도 살펴볼 수 있게 돕는다.
        </Note>
      </div>
    </div>
  );
}

const OBSERVATION_EXAMPLE = "화단 앞에 앉아 개미가 줄지어 가는 것을 3분 동안 바라보았다.";

/** 실제 표시한 글자 뒤에 커서를 둔다. clip-path는 숨긴 글자의 자리까지 차지한다. */
function TypingObservation({ still }: { still: boolean }) {
  const [length, setLength] = useState(() => (still ? OBSERVATION_EXAMPLE.length : 0));
  useEffect(() => {
    if (still || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let next = 0;
    let timer: ReturnType<typeof setTimeout>;
    const type = () => {
      next += 1;
      setLength(next);
      if (next < OBSERVATION_EXAMPLE.length) {
        timer = setTimeout(type, 2400 / OBSERVATION_EXAMPLE.length);
      }
    };
    timer = setTimeout(type, 400);
    return () => clearTimeout(timer);
  }, [still]);
  return (
    <>
      <span className={s.typed}>
        {OBSERVATION_EXAMPLE.slice(0, length)}
        <span className={s.caret} />
      </span>
      <span className={s.typedStatic}>{OBSERVATION_EXAMPLE}</span>
    </>
  );
}

function Note({
  title,
  sub,
  tone,
  children,
}: {
  title: string;
  sub: string;
  tone: string;
  children: ReactNode;
}) {
  return (
    <div className={`${s.note} border px-4 pb-3.5 pt-5 ${tone}`}>
      <span className="absolute -top-2.5 left-1/2 -ml-7 h-[18px] w-14 -rotate-2 border-x border-white/60 bg-tape" />
      <h3 className="font-display text-[20px] font-bold leading-[1.1]">{title}</h3>
      <small className="mt-0.5 block text-xs text-ink-soft">{sub}</small>
      <p className="mt-1.5 text-[13px] leading-[1.6]">{children}</p>
      <span
        className={`${s.stamp} absolute right-3 top-3.5 rounded-md border-[2.5px] border-alert-strong px-2 py-1 font-display text-[16px] font-bold leading-none text-alert-strong`}
      >
        초안
      </span>
    </div>
  );
}

/**
 * 공책에 붙이는 노란 쪽지 — 로그인 · 가입이 막혔을 때. 종이라 모서리를 둥글리지 않는다.
 * `alert` 면 화면 읽기 프로그램이 바로 읽는다(폼 오류). 이미 alert 안에 있으면 끈다.
 */
export function ErrorNote({ children, alert = true }: { children: ReactNode; alert?: boolean }) {
  return (
    <p
      role={alert ? "alert" : undefined}
      className="relative -rotate-[0.6deg] border border-note-line bg-note px-4 pb-3 pt-3.5 text-[13px] leading-relaxed text-sun-ink shadow-pg-card"
    >
      <span
        aria-hidden="true"
        className="absolute -top-2 left-1/2 -ml-6 h-4 w-12 rotate-2 border-x border-white/60 bg-tape"
      />
      {children}
    </p>
  );
}

function Pencil() {
  return (
    <svg aria-hidden="true" className={s.pencil} width="190" height="18" viewBox="0 0 190 18">
      <path d="M0 9 18 2v14z" fill="#f2d3a8" />
      <path d="M0 9l6-2.3v4.6z" fill="var(--pg-ink)" />
      <rect x="18" y="2" width="146" height="14" fill="#f5c96a" />
      <rect x="18" y="2" width="146" height="5" fill="#f9d98a" />
      <rect x="164" y="2" width="12" height="14" fill="#b9b2a6" />
      <rect x="176" y="2" width="14" height="14" rx="3" fill="var(--pg-alert)" />
    </svg>
  );
}
