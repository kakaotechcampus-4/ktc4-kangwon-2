import type { CSSProperties } from "react";

/**
 * 쪽지 쌤플 — 서비스 얼굴.
 *
 * 사이드바에 붙인 노란 쪽지가 이미 쌤플의 얼굴이다(`plan-generator-tokens.css` 머리말).
 * 새 그림을 들여오는 대신 그 쪽지에 눈·입을 달았다. 접힌 귀와 종이테이프까지 같은 재료다.
 *
 * **아이를 나타내는 그림이 아니다.** 아이에게 캐릭터를 배정하면 「우리 애가 왜 저거예요」를
 * 설명할 방법이 없다. 아이 표식은 도형·색이고(`lib/workspace/child-mark.ts`),
 * 이 얼굴은 서비스 쪽이 말을 거는 자리에만 쓴다.
 *
 * 색은 토큰만 쓴다. 빨강이 없는 것은 일부러다 — 오류 표시도 흙색(`--pg-peach-ink`)이다.
 */

/** 화면이 지금 어떤 말을 하는 자리인지. */
export type SsampleMood = "base" | "done" | "empty";

const TONE: Record<SsampleMood, { paper: string; fold: string; line: string }> = {
  base: { paper: "var(--pg-note)", fold: "var(--pg-note-fold)", line: "var(--pg-note-line)" },
  done: { paper: "var(--pg-sage)", fold: "var(--pg-sage-fold)", line: "var(--pg-sage-line)" },
  empty: { paper: "var(--pg-shell)", fold: "var(--pg-shell-fold)", line: "var(--pg-shell-line)" },
};

/** 읽어 줄 이름. 장식으로 쓸 때는 `label={null}` 로 끈다. */
const SPOKEN: Record<SsampleMood, string> = {
  base: "쌤플",
  done: "다 했어요",
  empty: "아직 비었어요",
};

const INK = "var(--pg-ink)";

export function SsampleNote({
  mood = "base",
  size = 40,
  label,
  className,
}: {
  mood?: SsampleMood;
  /** 한 변 길이(px). 24px 아래로는 눈·입이 뭉개진다. */
  size?: number;
  /** 읽어 줄 이름을 바꾼다. `null` 이면 장식으로 숨긴다. */
  label?: string | null;
  className?: string;
}) {
  const tone = TONE[mood];
  const paper: CSSProperties = { fill: tone.paper, stroke: tone.line };
  const fold: CSSProperties = { fill: tone.fold, stroke: tone.line };
  const face: CSSProperties = { fill: "none", stroke: INK };
  const spoken = label === undefined ? SPOKEN[mood] : label;
  // 작을수록 선을 굵게 해야 같은 굵기로 보인다.
  const stroke = size <= 28 ? 2.6 : 1.7;

  return (
    <svg
      viewBox="0 0 48 48"
      width={size}
      height={size}
      className={className}
      role={spoken ? "img" : undefined}
      aria-label={spoken ?? undefined}
      aria-hidden={spoken ? undefined : true}
    >
      <g transform="rotate(-4 24 24)" strokeLinejoin="round" strokeWidth={stroke}>
        <path d="M8 10H40V32L31 40H8Z" style={paper} />
        <path d="M40 32H31V40Z" style={fold} />
        {mood === "base" && size > 28 && (
          <rect
            x="17"
            y="5.5"
            width="14"
            height="6"
            rx="1"
            style={{ fill: "var(--pg-tape)", stroke: "var(--pg-paper-warm-line)" }}
            strokeWidth="1.2"
          />
        )}
        <Face mood={mood} face={face} stroke={stroke} />
      </g>
    </svg>
  );
}

/** 표정. 눈과 입만 다르고 종이는 같다. */
function Face({ mood, face, stroke }: { mood: SsampleMood; face: CSSProperties; stroke: number }) {
  if (mood === "done") {
    // 웃는 눈. 점 두 개보다 「해냈다」가 분명하게 읽힌다.
    return (
      <g style={face} strokeWidth={stroke} strokeLinecap="round">
        <path d="M17.6 22.6q1.8-2.4 3.6 0" />
        <path d="M26.8 22.6q1.8-2.4 3.6 0" />
        <path d="M18.8 26.6q5.2 4.2 10.4 0" />
      </g>
    );
  }
  return (
    <>
      <circle cx="19.4" cy="22" r="2" style={{ fill: INK, stroke: "none" }} />
      <circle cx="28.6" cy="22" r="2" style={{ fill: INK, stroke: "none" }} />
      {mood === "empty" ? (
        // 비었다는 말을 입 모양으로. 슬픈 얼굴은 교사를 탓하는 것처럼 보인다.
        <circle cx="24" cy="28.2" r="2.3" style={face} strokeWidth={stroke} />
      ) : (
        <path d="M19.2 27.4q4.8 3 9.6 0" style={face} strokeWidth={stroke} strokeLinecap="round" />
      )}
    </>
  );
}
