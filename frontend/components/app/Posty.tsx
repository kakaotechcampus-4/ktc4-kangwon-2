import type { CSSProperties } from "react";

/**
 * 포스티 — 쌤플의 얼굴.
 *
 * 쪽지가 몸이고, 가는 팔과 큰 손발이 쪽지에서 바로 나온다(팔다리 「다」 안으로 확정).
 * 상체와 얼굴은 어느 포즈에서나 같다. **팔다리 각도만 바뀐다** — 포즈마다 몸을 새로
 * 그리면 같은 아이로 안 읽힌다.
 *
 * **아이를 나타내는 그림이 아니다.** 아이 표식은 도형·색이고(`lib/workspace/child-mark.ts`),
 * 포스티는 서비스 쪽이 말을 거는 자리에만 선다.
 *
 * 색은 토큰만 쓴다. 빨강 셋은 되돌리기 어려운 일에만 쓴다 — 색이 진해질수록 돌이키기 어렵다.
 */

/** 쪽지 색. 색이 곧 상태다. */
export type PostyTone =
  "note" | "sage" | "shell" | "sun" | "lilac" | "plum" | "clay" | "caution" | "check" | "erase";

/** 팔다리 각도. 상체는 그대로다. */
export type PostyPose =
  "stand" | "up" | "hand" | "point" | "wave" | "cheer" | "run" | "think" | "sit" | "sitWave";

/** 표정. */
export type PostyFace = "base" | "done" | "empty" | "fix" | "oh" | "think";

const TONE: Record<PostyTone, { paper: string; line: string; fold: string }> = {
  note: { paper: "--pg-note", line: "--pg-note-line", fold: "--pg-note-fold" },
  sage: { paper: "--pg-sage", line: "--pg-sage-line", fold: "--pg-sage-fold" },
  shell: { paper: "--pg-shell", line: "--pg-shell-line", fold: "--pg-shell-fold" },
  sun: { paper: "--pg-sun-tint", line: "--pg-sun", fold: "--pg-paper-warm" },
  lilac: { paper: "--pg-primary-tint", line: "--pg-primary-tint-line", fold: "--pg-plum-fold" },
  plum: { paper: "--pg-plum", line: "--pg-plum-line", fold: "--pg-plum-fold" },
  clay: { paper: "--pg-clay", line: "--pg-clay-line", fold: "--pg-clay-fold" },
  /** 가벼운 주의 — 「이대로 두면 비어 있어요」 */
  caution: { paper: "--pg-alert-soft", line: "--pg-alert-soft-line", fold: "--pg-alert-soft-fold" },
  /** 확인 필요 — 「근거 없는 문장이 있어요」 */
  check: { paper: "--pg-alert", line: "--pg-alert-line", fold: "--pg-alert-fold" },
  /** 지우기 — 되돌릴 수 없는 일 */
  erase: {
    paper: "--pg-alert-strong",
    line: "--pg-alert-strong-line",
    fold: "--pg-alert-strong-fold",
  },
};

const INK = "var(--pg-ink)";

/**
 * 쪽지는 x 7~41 에 서지만 손은 그 밖으로 뻗는다 — `sit` 의 왼손 중심이 2.4,
 * 손 반지름이 4.2 라 폭 48 짜리 틀에서는 끝이 잘렸다. 좌우로 이만큼 넓혀 둔다.
 */
const PAD = 4;

/** 어깨·엉덩이는 쪽지에 붙어 있어 포즈가 달라도 자리가 같다. */
const SHOULDER = { left: 7, right: 41, y: 28 };
const HIP = { left: 18, right: 30, y: 43 };

type Pose = {
  /** 왼손 · 오른손 끝. 세 번째 값은 팔이 휘는 정도. */
  arms: [[number, number, number], [number, number, number]];
  feet: [[number, number], [number, number]];
  height: number;
};

const POSE: Record<PostyPose, Pose> = {
  stand: {
    arms: [
      [2.8, 41, 0],
      [45.2, 41, 0],
    ],
    feet: [
      [17, 53],
      [31, 53],
    ],
    height: 60,
  },
  up: {
    arms: [
      [3.4, 11, 0],
      [44.6, 11, 0],
    ],
    feet: [
      [17, 53],
      [31, 53],
    ],
    height: 60,
  },
  hand: {
    arms: [
      [2.6, 9, 0],
      [45.2, 41, 0],
    ],
    feet: [
      [17, 53],
      [31, 53],
    ],
    height: 60,
  },
  point: {
    arms: [
      [2.8, 41, 0],
      [46.4, 16, 0],
    ],
    feet: [
      [17, 53],
      [31, 53],
    ],
    height: 60,
  },
  wave: {
    arms: [
      [2.8, 41, 0],
      [45.6, 12, 4],
    ],
    feet: [
      [17, 53],
      [31, 53],
    ],
    height: 60,
  },
  cheer: {
    arms: [
      [1.6, 18, -3],
      [46.4, 18, 3],
    ],
    feet: [
      [14.2, 52],
      [33.8, 52],
    ],
    height: 60,
  },
  run: {
    arms: [
      [1.8, 22, -3],
      [46.2, 36, 3],
    ],
    feet: [
      [11.6, 50],
      [35.4, 54],
    ],
    height: 60,
  },
  think: {
    arms: [
      [2.8, 41, 0],
      [34.5, 20, 6],
    ],
    feet: [
      [17, 53],
      [31, 53],
    ],
    height: 60,
  },
  sit: {
    arms: [
      [2.4, 38, 0],
      [45.6, 38, 0],
    ],
    feet: [
      [11.5, 49],
      [36.5, 49],
    ],
    height: 56,
  },
  sitWave: {
    arms: [
      [2.4, 38, 0],
      [45.6, 12, 4],
    ],
    feet: [
      [11.5, 49],
      [36.5, 49],
    ],
    height: 56,
  },
};

/** 읽어 줄 이름. 장식으로 쓸 때는 `label={null}`. */
const SPOKEN: Record<PostyFace, string> = {
  base: "포스티",
  done: "다 했어요",
  empty: "아직 비었어요",
  fix: "확인이 필요해요",
  oh: "잠깐요",
  think: "생각 중이에요",
};

function arm(
  startX: number,
  [x, y, curve]: [number, number, number],
  w: number,
  hand: number,
  swing?: string,
) {
  const d = curve
    ? `M${startX} ${SHOULDER.y}Q${(startX + x) / 2 + curve} ${(SHOULDER.y + y) / 2} ${x} ${y}`
    : `M${startX} ${SHOULDER.y}L${x} ${y}`;
  return (
    <g
      className={swing}
      style={swing ? { transformOrigin: `${startX}px ${SHOULDER.y}px` } : undefined}
    >
      <path d={d} fill="none" stroke={INK} strokeWidth={w} strokeLinecap="round" />
      <circle cx={x} cy={y} r={hand} fill={INK} />
    </g>
  );
}

function leg(
  hipX: number,
  [x, y]: [number, number],
  right: boolean,
  w: number,
  foot: number,
  swing?: string,
) {
  return (
    <g className={swing} style={swing ? { transformOrigin: `${hipX}px ${HIP.y}px` } : undefined}>
      <path
        d={`M${hipX} ${HIP.y}L${x} ${y}`}
        fill="none"
        stroke={INK}
        strokeWidth={w}
        strokeLinecap="round"
      />
      <ellipse
        cx={x + (right ? foot * 0.78 : -foot * 0.78)}
        cy={y + 1}
        rx={foot}
        ry={foot * 0.59}
        fill={INK}
      />
    </g>
  );
}

/** 표정 — 쪽지 한가운데 앉는다. */
function Face({ kind }: { kind: PostyFace }) {
  const line = { stroke: INK, strokeWidth: 1.8, strokeLinecap: "round" as const, fill: "none" };
  const eyes = (cy: number) => (
    <>
      <circle cx={18.6} cy={cy} r={2.2} fill={INK} />
      <circle cx={29.4} cy={cy} r={2.2} fill={INK} />
    </>
  );
  if (kind === "done")
    return (
      <g {...line}>
        <path d="M16.6 19.6q2 -2.6 4 0" />
        <path d="M27.4 19.6q2 -2.6 4 0" />
        <path d="M18 24q6 4.6 12 0" />
      </g>
    );
  if (kind === "think")
    return (
      <g {...line}>
        <path d="M16.4 19.4q2.2 2 4.4 0" />
        <path d="M27.2 19.4q2.2 2 4.4 0" />
        <path d="M20.8 25.4h6.4" />
      </g>
    );
  if (kind === "fix")
    return (
      <>
        <g {...line}>
          <path d="M15.6 14.6 20.6 16.4" />
          <path d="M32.4 14.6 27.4 16.4" />
          <path d="M20 26.4h8" />
        </g>
        {eyes(20.2)}
      </>
    );
  if (kind === "oh")
    return (
      <>
        <g {...line}>
          <path d="M15.4 14.2q2.6 -1.8 5.2 -0.4" />
          <path d="M32.6 14.2q-2.6 -1.8 -5.2 -0.4" />
        </g>
        {eyes(19.4)}
        <ellipse cx={24} cy={27} rx={2.8} ry={3.4} {...line} />
      </>
    );
  if (kind === "empty")
    return (
      <>
        {eyes(19)}
        <ellipse cx={24} cy={26} rx={2.4} ry={2.8} {...line} />
      </>
    );
  return (
    <>
      {eyes(19)}
      <path d="M18.4 25q5.6 3.4 11.2 0" {...line} />
    </>
  );
}

export function Posty({
  pose = "stand",
  tone = "note",
  face = "base",
  size = 96,
  tape = false,
  walk = false,
  wave = false,
  label,
  className,
  style,
}: {
  pose?: PostyPose;
  tone?: PostyTone;
  face?: PostyFace;
  /** 가로 길이(px). 키는 포즈가 정한다. */
  size?: number;
  /** 머리에 붙이는 종이테이프. 첫 인사에만 쓴다. */
  tape?: boolean;
  /**
   * 걷는 모습. 팔다리가 번갈아 흔들리고 몸이 한 번씩 뜬다.
   * 흔드는 각도가 커서 **서 있기 포즈에만** 쓴다 — 든 팔을 흔들면 춤이 된다.
   * 「동작 줄이기」를 켠 교사에게는 멈춘 채로 선다.
   */
  walk?: boolean;
  /**
   * 든 오른팔을 흔든다 — 「여기요」 하고 부르는 손짓. 두 번 흔들고 잠깐 쉰다.
   * 오른팔을 든 포즈(`wave` · `sitWave`)에만 쓴다. 「동작 줄이기」면 멈춰 있다.
   */
  wave?: boolean;
  label?: string | null;
  className?: string;
  style?: CSSProperties;
}) {
  const { arms, feet, height } = POSE[pose];
  const skin = TONE[tone];
  const spoken = label === undefined ? SPOKEN[face] : label;
  // 작게 쓸수록 선을 굵게 해야 같은 굵기로 보인다. 34px 에서 1.9 는 1px 밑으로 내려가 사라진다.
  const thin = size < 56;
  const w = thin ? 2.8 : 1.9;
  const hand = thin ? 5 : 4.2;
  const foot = thin ? 6 : 5.4;
  const swinging = walk && pose === "stand";
  const waving = wave && (pose === "wave" || pose === "sitWave");
  return (
    <svg
      viewBox={`${-PAD} 0 ${48 + PAD * 2} ${height}`}
      width={size}
      height={Math.round((size * height) / (48 + PAD * 2))}
      className={[swinging ? "postyWalk" : "", className].filter(Boolean).join(" ") || undefined}
      style={style}
      role={spoken ? "img" : undefined}
      aria-label={spoken ?? undefined}
      aria-hidden={spoken ? undefined : true}
    >
      {arm(SHOULDER.left, arms[0], w, hand, swinging ? "postySwingBack" : undefined)}
      {arm(
        SHOULDER.right,
        arms[1],
        w,
        hand,
        swinging ? "postySwingFront" : waving ? "postyWave" : undefined,
      )}
      {leg(HIP.left, feet[0], false, w, foot, swinging ? "postySwingFront" : undefined)}
      {leg(HIP.right, feet[1], true, w, foot, swinging ? "postySwingBack" : undefined)}
      <path
        d="M7 5H41V34L31 43H7Z"
        fill={`var(${skin.paper})`}
        stroke={`var(${skin.line})`}
        strokeWidth={1.8}
        strokeLinejoin="round"
      />
      <path
        d="M41 34H31V43Z"
        fill={`var(${skin.fold})`}
        stroke={`var(${skin.line})`}
        strokeWidth={1.8}
        strokeLinejoin="round"
      />
      {tape && (
        <rect
          x={17}
          y={0.8}
          width={14}
          height={5.4}
          rx={1}
          fill="var(--pg-tape)"
          stroke="var(--pg-paper-warm-line)"
          strokeWidth={1.2}
        />
      )}
      <Face kind={face} />
    </svg>
  );
}
