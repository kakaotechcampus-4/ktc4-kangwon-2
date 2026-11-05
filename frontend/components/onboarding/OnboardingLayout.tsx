"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { Posty } from "@/components/app/Posty";
import { useTypewriter } from "./FlowParts";
import { fontClassName } from "@/lib/fonts";
import { readToken } from "@/lib/auth/token";
import { useClientState } from "@/lib/hooks/use-client-state";

/** 진행 글자. 원 정보 · 반 정보 · 아이 명단 세 단계와 마지막 확인. */
const LABELS = ["원 정보 1/3", "반 정보 2/3", "아이 명단 3/3", "마지막 확인"];

/** 오른쪽 칸 포스티의 말 — 굵은 한 줄과 풀어 쓴 한 줄. */
export type PostySay = { title: string; body: string };

/**
 * 시작 설정(온보딩)의 틀 — 시안 캔버스 「A · 오른쪽 포스티 칸」 그대로.
 *
 * 휴대폰: 흰 한 장. 맨 위 줄에 「←」 와 오른쪽 진행 글자, 그 아래 얇은 막대, 질문, 아래 넓은 주 버튼.
 * 데스크톱: 크림 바탕 위 「쌤플」 머리 줄과 가운데 칠판(.chalkPage). 칠판이라 폼 한 열(820px)보다 넓게 1100px 까지 편다.
 * 768px 부터는 칠판 오른쪽 280px(1024px 부터 320px) 칸에 손 흔드는 포스티 · 말풍선(`say`)을 두고, 넘어가는 버튼도 그 칸 아래로 간다.
 * 그보다 좁으면 입력 칸이 너무 좁아져 칸을 빼고 휴대폰과 같은 한 줄로 둔다.
 * 완료 화면처럼 진행이 없는 화면은 `stage` 를 비운다 — 진행 글자도 오른쪽 칸도 없다.
 */
export default function OnboardingLayout({
  stage,
  say,
  live = false,
  progress,
  onBack,
  footer,
  children,
}: {
  /** 1~3 은 세 단계, 4 는 마지막 확인(셋 다 끝남). */
  stage?: 1 | 2 | 3 | 4;
  say?: PostySay;
  /** 말풍선이 바뀔 때마다 읽어 줄지(아이 명단에서 넣고 뺄 때). */
  live?: boolean;
  /** 0~1 */
  progress?: number;
  /** 있으면 「←」 를 보인다. 첫 질문에서는 앞 화면으로 가는 함수를 준다. */
  onBack?: () => void;
  footer?: ReactNode;
  children: ReactNode;
}) {
  // 로고가 가는 곳은 교사가 누구냐에 따라 다르다. 처음 가입한 사람에게는 아직 원이 없어
  // 메인으로 보내봐야 할 일이 없지만, 설정을 고치러 들어온 교사에게 소개 화면을 띄우면
  // 쓰던 자리에서 튕겨 나간다 (수린 점검).
  const [signedIn] = useClientState(() => !!readToken(), false);
  const home = signedIn ? "/" : "/welcome";
  const percent =
    progress === undefined ? null : Math.round(Math.min(1, Math.max(0, progress)) * 100);
  const label = stage && LABELS[stage - 1];
  return (
    <div
      // 데스크톱은 **흰 카드만** 화면 세로 가운데에 둔다. 머리 줄은 카드 바로 위에 띄워 두고 가운데 계산에서 뺀다.
      // 위아래 여백을 머리 줄 높이보다 크게 같게 두어, 창이 낮아도 머리 줄이 화면 밖으로 밀려나지 않는다.
      className={`${fontClassName} flex min-h-screen flex-col items-center bg-[var(--pg-board)] font-body text-ink sm:justify-center sm:bg-cream sm:px-6 sm:py-[88px]`}
    >
      <div className="relative flex w-full max-w-[1100px] flex-1 flex-col sm:flex-none">
        <header className="absolute inset-x-0 bottom-full hidden h-[72px] items-center justify-between sm:flex">
          <Link
            href={home}
            aria-label={signedIn ? "쌤플 메인으로" : "쌤플 소개로"}
            className="font-display text-[30px] font-bold text-primary-deep"
          >
            쌤플
          </Link>
          {/* 첫 설정에서 빠져나갈 길. 전에는 주소창에 /logout 을 쳐야 했다 (#291) */}
          {signedIn ? (
            <Link href="/logout" className="flex min-h-11 items-center text-[14px] text-ink-soft">
              로그아웃
            </Link>
          ) : (
            <span className="text-[14px] text-ink-soft">시작 설정</span>
          )}
        </header>

        {/* 768px 부터 오른쪽 칸이 있는 화면은 두 칸 격자다 — 왼쪽은 질문이 위아래를 다 쓰고,
            오른쪽은 위에 포스티 · 말풍선, 아래에 넘어가는 버튼. 버튼은 한 벌만 그려 자리만 옮긴다. */}
        <div
          className={`chalkboard chalkPage flex flex-1 flex-col bg-paper sm:min-h-[760px] sm:flex-none ${stage ? "md:grid md:grid-cols-[minmax(0,1fr)_280px] md:grid-rows-[minmax(0,1fr)_auto] lg:grid-cols-[minmax(0,1fr)_320px]" : ""}`}
        >
          <div className="flex min-w-0 flex-1 flex-col md:row-span-2">
            <div className="flex h-14 flex-none items-center gap-2 px-3 sm:px-7">
              {onBack && (
                <button
                  type="button"
                  onClick={onBack}
                  aria-label="이전"
                  className="inline-flex h-11 w-11 items-center justify-center squircle [--r:12px] text-ink hover:bg-primary-tint focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
                >
                  <svg
                    width="24"
                    height="24"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M15 5l-7 7 7 7" />
                  </svg>
                </button>
              )}
              <div className="flex-1" />
              {label && <span className="pr-3 text-[13px] font-medium text-ink-soft">{label}</span>}
            </div>
            {percent !== null && (
              <div
                role="progressbar"
                aria-label="진행 정도"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={percent}
                className="mx-6 h-1 flex-none overflow-hidden rounded-sm bg-shell sm:mx-10"
              >
                <div
                  className="h-1 rounded-sm bg-primary transition-[width] duration-300"
                  style={{ width: `${percent}%` }}
                />
              </div>
            )}

            <main className="flex flex-1 flex-col px-6 pb-6 pt-7 sm:px-10">{children}</main>
          </div>

          {stage && <PostyPanel say={say} live={live} />}

          {/* 분필 결 — 밑줄(ChalkLine)과 지역 고르개의 네모(ChalkBox)가 같이 쓴다. 선을 살짝 비틀고(displacement),
              가루처럼 군데군데 비운다(noise 를 알파로). 영역은 두 쪽 viewBox(100×4 · 100×40)를 다 덮게 잡는다. */}
          <svg aria-hidden="true" width="0" height="0" className="absolute">
            <filter id="chalk" filterUnits="userSpaceOnUse" x="-5" y="-5" width="110" height="50">
              <feTurbulence
                type="fractalNoise"
                baseFrequency="0.9"
                numOctaves={2}
                seed={3}
                result="n"
              />
              <feDisplacementMap
                in="SourceGraphic"
                in2="n"
                scale={1.6}
                xChannelSelector="R"
                yChannelSelector="G"
                result="d"
              />
              <feTurbulence
                type="fractalNoise"
                baseFrequency="1.4"
                numOctaves={1}
                seed={8}
                result="g"
              />
              <feColorMatrix
                in="g"
                type="matrix"
                values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 -2.2 1.75"
                result="mask"
              />
              <feComposite in="d" in2="mask" operator="in" />
            </filter>
            {/* 글자용 분필 결 — 선보다 덜 비틀고 덜 비운다. 더 세게 하면 이름이 안 읽힌다(시험 의견: 가독성).
                글자 상자에 맞춰(objectBoundingBox) 잡으니 글자 길이가 달라도 된다. */}
            {/* 분필로 그린 포스티(.chalkPosty) — 쪽지 몸은 노란 분필을 비스듬히 문질러 칠한 빗금으로 채운다.
                굵기가 다른 획 셋을 한 무늬에 넣어 고르지 않게 하고, 획 사이로 칠판이 조금 비친다. */}
            <pattern
              id="chalk-hatch"
              patternUnits="userSpaceOnUse"
              width="7"
              height="7"
              patternTransform="rotate(-28)"
            >
              <rect width="7" height="7" fill="var(--pg-primary)" fillOpacity={0.4} />
              <rect x="0" width="2.1" height="7" fill="var(--pg-primary)" />
              <rect x="2.7" width="1.4" height="7" fill="var(--pg-primary)" fillOpacity={0.85} />
              <rect x="4.6" width="1.9" height="7" fill="var(--pg-primary)" />
            </pattern>
            <pattern
              id="chalk-hatch-fold"
              patternUnits="userSpaceOnUse"
              width="3"
              height="3"
              patternTransform="rotate(-35)"
            >
              <rect width="3" height="3" fill="var(--pg-primary)" fillOpacity={0.55} />
              <rect width="2.2" height="3" fill="var(--pg-primary)" />
            </pattern>
            {/* 포스티 선 결 — 살짝 출렁이고(낮은 주파수) 가장자리를 조금 거칠게 비튼 뒤, 결 따라 군데군데 비우고 살짝 번지게 한다.
                점처럼 고르게 비우면 모자이크처럼 보여서, 비우는 무늬를 한쪽으로 길게(0.35 · 0.6) 둔다. */}
            <filter id="chalk-posty" x="-10%" y="-10%" width="120%" height="120%">
              <feTurbulence
                type="fractalNoise"
                baseFrequency="0.03"
                numOctaves={2}
                seed={4}
                result="w"
              />
              <feDisplacementMap
                in="SourceGraphic"
                in2="w"
                scale={3.5}
                xChannelSelector="R"
                yChannelSelector="G"
                result="wob"
              />
              <feTurbulence
                type="fractalNoise"
                baseFrequency="0.9"
                numOctaves={2}
                seed={5}
                result="r"
              />
              <feDisplacementMap
                in="wob"
                in2="r"
                scale={1.4}
                xChannelSelector="R"
                yChannelSelector="G"
                result="rough"
              />
              <feTurbulence
                type="fractalNoise"
                baseFrequency="0.35 0.6"
                numOctaves={3}
                seed={11}
                result="g"
              />
              <feColorMatrix
                in="g"
                type="matrix"
                values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 -1.5 1.5"
                result="gm"
              />
              <feComposite in="rough" in2="gm" operator="in" result="grainy" />
              <feGaussianBlur in="grainy" stdDeviation={0.45} result="soft" />
              {/* 둘레에 분필 가루가 뿌옇게 번진 듯 — 크게 흐린 사본을 옅게(45%) 깔고 그 위에 그림을 얹는다. */}
              <feGaussianBlur in="soft" stdDeviation={3} result="halo" />
              <feColorMatrix
                in="halo"
                type="matrix"
                values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 0.45 0"
                result="dust"
              />
              <feMerge>
                <feMergeNode in="dust" />
                <feMergeNode in="soft" />
              </feMerge>
            </filter>
            <filter id="chalk-text" x="-5%" y="-15%" width="110%" height="130%">
              <feTurbulence
                type="fractalNoise"
                baseFrequency="0.9"
                numOctaves={2}
                seed={3}
                result="n"
              />
              <feDisplacementMap
                in="SourceGraphic"
                in2="n"
                scale={1.1}
                xChannelSelector="R"
                yChannelSelector="G"
                result="d"
              />
              <feTurbulence
                type="fractalNoise"
                baseFrequency="1.2"
                numOctaves={2}
                seed={8}
                result="g"
              />
              <feColorMatrix
                in="g"
                type="matrix"
                values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 -2.1 1.75"
                result="mask"
              />
              <feComposite in="d" in2="mask" operator="in" />
            </filter>
          </svg>

          {footer && (
            <div
              className={`sticky bottom-0 flex flex-none flex-col-reverse items-stretch gap-2 bg-paper px-6 pb-5 pt-3 sm:flex-row sm:items-center sm:justify-end sm:px-10 ${stage ? "md:static md:col-start-2 md:row-start-2 md:flex-col-reverse md:items-stretch md:justify-start md:border-l md:border-shell md:bg-ivory md:px-7 md:pb-8" : ""}`}
            >
              {footer}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * 카드 오른쪽 칸 위쪽 — 말풍선과 그 아래 손 흔드는 포스티를 칸 세로 가운데에 둔다. 아래쪽 버튼 자리는 OnboardingLayout 의 footer 다.
 * 말풍선은 친 글자만큼만 자란다 — 가로는 글 길이에 맞춰 가운데에서 양옆으로(칸 너비까지), 세로는 위로.
 * 포스티가 따라 움직이지 않도록 말풍선 자리(`h-[124px]`, 가장 긴 문구인 4줄 높이)를 따로 잡고
 * 그 아래쪽에 붙인다. 꼬리는 말풍선 가운데라 늘 포스티 위에 있다.
 */
function PostyPanel({ say, live }: { say?: PostySay; live: boolean }) {
  return (
    <aside
      aria-label="진행 안내"
      className="hidden flex-col items-center justify-center gap-[18px] border-l border-shell bg-ivory px-7 py-8 md:col-start-2 md:row-start-1 md:flex"
    >
      <div className="flex h-[124px] w-full flex-none flex-col items-center justify-end">
        {say && (
          <div
            className="paper relative max-w-full squircle [--r:16px] border border-line bg-paper px-4 py-3.5 text-left"
            style={{ wordBreak: "keep-all" }}
          >
            <span
              aria-hidden="true"
              className="absolute -bottom-[7px] left-1/2 -ml-1.5 h-3 w-3 rotate-45 border-b border-r border-line bg-paper"
            />
            {/* 한 글자씩 치는 글은 화면 읽기 프로그램이 글자마다 읽지 않도록 숨기고, 다 된 글을 따로 둔다. */}
            <span className="sr-only" aria-live={live ? "polite" : undefined}>
              {say.title} {say.body}
            </span>
            <SayLines key={say.title + say.body} say={say} />
          </div>
        )}
      </div>
      <Posty
        pose="wave"
        tone="note"
        face="base"
        size={152}
        tape
        label="포스티가 손을 흔들어요"
        // 칠판에 분필로 그린 포스티(globals.css 의 .chalkPosty)
        className="chalkPosty"
      />
    </aside>
  );
}

/**
 * 말풍선 글 — 앞 문구와 뒷 문구를 굵기 · 크기 · 글자색이 모두 같은 한 문단으로 잇는다
 * (포스티가 한 번에 말하는 것처럼). 앞 문구는 늘 응원 한마디라 굵게 하면 덜 중요한 쪽이 눈에 띈다.
 * 글이 바뀌면 `key` 로 처음부터 다시 친다. 아직 안 친 글자는 자리를 잡지 않는다(말풍선이 글과 함께
 * 자란다). 가운데 맞춤이면 글자마다 줄이 흔들려서 왼쪽 맞춤이다.
 */
function SayLines({ say }: { say: PostySay }) {
  const text = `${say.title} ${say.body}`;
  const shown = useTypewriter(text.length);
  return (
    <span aria-hidden="true" className="block text-[15px] leading-[1.6] text-ink">
      {text.slice(0, shown)}
    </span>
  );
}

/** 각 단계 상단의 제목/설명 블록 */
export function StepHeading({
  title,
  description,
  eyebrow,
}: {
  title: string;
  description: string;
  eyebrow?: ReactNode;
}) {
  return (
    <div>
      {eyebrow}
      {/* balance 는 휴대폰에서 「우리 반 아동 / 명단을…」처럼 말 중간을 끊는다. 어절 단위로만 줄을 바꾼다 */}
      <h1
        className={`font-display text-[24px] font-bold text-ink sm:text-[26px] lg:text-[32px] ${eyebrow ? "mt-3" : ""}`}
        style={{ wordBreak: "keep-all" }}
      >
        {title}
      </h1>
      <p className="mt-2 text-[14.5px] leading-relaxed text-ink-soft">{description}</p>
    </div>
  );
}

/** 하단 [이전] [다음] 영역 — 모바일에서는 다음 버튼이 넓게 늘어난다 */
export function StepFooter({
  left,
  right,
  note,
}: {
  left?: ReactNode;
  right: ReactNode;
  note?: ReactNode;
}) {
  return (
    <div className="mt-1 flex flex-wrap items-center gap-3 border-t border-line pt-[22px]">
      {left}
      <span className="flex-1" />
      {note && <span className="hidden text-[12.5px] text-ink-soft lg:inline">{note}</span>}
      {right}
    </div>
  );
}
