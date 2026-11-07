"use client";

import type { CSSProperties } from "react";
import Link from "next/link";
import { Posty, type PostyTone } from "@/components/app/Posty";
import OnboardingLayout from "./OnboardingLayout";
import { ctaClass } from "./FlowParts";
import styles from "./DoneScreen.module.css";

/** 작은 포스티 한 줄 — 바닥에서 높이(y) · 크기 · 앞에 서는지(뒷줄은 가운데 포스티 뒤로 가려진다). */
const ROWS: { y: number; size: number; front: boolean; xs: number[] }[] = [
  // 뒷줄 — 가운데 포스티 어깨 뒤로 머리만 보인다
  { y: 58, size: 24, front: false, xs: [-98, -72, 72, 98] },
  // 가운데 줄 — 어깨를 붙이고 선다
  { y: 28, size: 28, front: false, xs: [-142, -114, -86, 86, 114, 142] },
  // 앞줄 — 가운데 줄 발치를 가린다
  { y: 0, size: 32, front: true, xs: [-150, -116, 116, 150] },
];
const TONES: PostyTone[] = ["lilac", "clay", "plum", "sun", "note", "shell", "sage"];

/**
 * 뒤에 모인 작은 포스티. x 는 가운데에서 떨어진 거리, d 는 던지는 박자(2.2초 한 바퀴 안).
 * 이웃끼리 박자가 겹치지 않게 7번째마다 돌려 가며 나눈다 — 한꺼번에 뛰면 무리가 아니라 한 덩어리로 보인다.
 */
const THROWERS = ROWS.flatMap((row, r) => row.xs.map((x) => ({ ...row, x, r }))).map((t, i) => ({
  ...t,
  key: `${t.r}:${t.x}`,
  tone: TONES[i % TONES.length],
  d: ((i * 7) % 14) * (2.2 / 14),
}));

const PETAL_COLORS = ["--pg-primary", "--pg-sun", "--pg-clay", "--pg-plum", "--pg-sage-line"];
const PETAL_SHAPES = ["", styles.dot, styles.strip];

/**
 * 꽃가루 — 작은 포스티마다 양손에서 한 장씩. 두 팔을 든 포즈(up)의 손끝에서 시작한다.
 * 손끝은 몸 가운데에서 폭의 0.37배 옆, 바닥에서 폭의 0.88배 위다(Posty 의 up 포즈 좌표).
 * 던지는 거리는 몸 크기에 맞춘다 — 작은 포스티가 멀리 던지면 어색하다.
 */
const PETALS = THROWERS.flatMap((t, i) =>
  [-1, 1].map((side, j) => {
    const k = i * 2 + j;
    const reach = t.size / 32;
    return {
      key: `${t.key}:${j}`,
      sx: t.x + side * t.size * 0.37,
      sy: t.y + t.size * 0.88,
      dx: Math.round(side * (12 + ((k * 7) % 18)) * reach),
      up: -Math.round((30 + ((k * 11) % 24)) * reach),
      fall: Math.round((26 + ((k * 13) % 20)) * reach),
      r: side * (200 + ((k * 37) % 160)),
      delay: t.d + j * 0.12,
      color: PETAL_COLORS[k % PETAL_COLORS.length],
      shape: PETAL_SHAPES[k % PETAL_SHAPES.length],
    };
  }),
);

/** 설정을 마친 화면. 요약 세 줄과 메인으로 가는 버튼. */
export default function DoneScreen({
  orgName,
  classCount,
  childCount,
}: {
  orgName: string;
  classCount: number;
  childCount: number;
}) {
  const rows = [
    ["어린이집", orgName || "-"],
    ["등록 반", `${classCount}개`],
    ["등록 아동", `${childCount}명`],
  ];
  return (
    <OnboardingLayout
      footer={
        <Link href="/" className={ctaClass}>
          메인으로 가기
        </Link>
      }
    >
      <div className="flex flex-col items-center gap-[18px] pt-9 text-center">
        <div className={styles.stage}>
          {THROWERS.map((t) => (
            <div
              key={t.key}
              aria-hidden="true"
              className={styles.thrower}
              style={
                {
                  "--bx": `${t.x}px`,
                  "--by": `${t.y}px`,
                  "--delay": `${t.d}s`,
                  zIndex: t.front ? 1 : 0,
                } as CSSProperties
              }
            >
              <div className={styles.throwerBody}>
                <Posty pose="up" tone={t.tone} face="done" size={t.size} label={null} />
              </div>
            </div>
          ))}
          {PETALS.map((p) => (
            <span
              key={p.key}
              aria-hidden="true"
              className={`${styles.petal} ${p.shape}`}
              style={
                {
                  background: `var(${p.color})`,
                  "--sx": `${p.sx}px`,
                  "--sy": `${p.sy}px`,
                  "--dx": `${p.dx}px`,
                  "--up": `${p.up}px`,
                  "--fall": `${p.fall}px`,
                  "--r": `${p.r}deg`,
                  "--delay": `${p.delay}s`,
                } as CSSProperties
              }
            />
          ))}
          <span className={styles.shadow} aria-hidden="true" />
          <div className={styles.hop}>
            <Posty
              pose="cheer"
              tone="sage"
              face="done"
              size={120}
              label="포스티가 다 했다고 두 팔을 들어요"
            />
          </div>
        </div>

        <h1 className="font-display text-[32px] font-bold leading-[1.35] text-ink sm:text-[40px]">
          준비 끝났어요!
        </h1>
        <p className="text-[16px] leading-[1.6] text-ink-soft">
          이제 메인 화면에서 쌤플을 시작할 수 있어요.
        </p>

        <dl className="mt-2 grid w-full grid-cols-3 gap-2">
          {rows.map(([k, v]) => (
            <div key={k} className="squircle [--r:14px] bg-cream px-2 py-3.5">
              <dt className="text-[13px] font-medium leading-tight text-ink-soft">{k}</dt>
              <dd className="mt-1 text-[15px] font-bold text-ink" style={{ wordBreak: "keep-all" }}>
                {v}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </OnboardingLayout>
  );
}
