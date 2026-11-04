"use client";

import Image from "next/image";
import { useState, type KeyboardEvent } from "react";
import s from "./Welcome.module.css";

/**
 * 계획안 세 걸음 — 형식 고르기 → 연간 → 월간. 탭을 누르면 그 단계의 실제 화면이 바뀐다.
 * 그림은 멘토용 테스트 계정에서 만든 계획안을 찍은 것이다.
 */

const STEPS = [
  {
    id: "types",
    tab: "형식 고르기",
    title: "우리 원 방식에 맞춰 시작해요",
    text: "생활주제를 따라 내려가는 월별 주제형과, 아이들 놀이에서 출발하는 놀이 중심형 중에서 골라요.",
    points: ["월별 주제형 — 연간 · 월간 · 주간", "놀이 중심형 — 연간 · 월간"],
    image: {
      src: "/landing/v2/plan-types.webp",
      width: 1600,
      height: 578,
      alt: "계획안 형식 고르기 화면. 월별 주제형과 놀이 중심형 카드가 나란히 있다.",
    },
  },
  {
    id: "annual",
    tab: "연간 계획안",
    title: "1년 주제가 한 장에 채워져요",
    text: "3월부터 이듬해 2월까지 달마다 생활주제와 주별 소주제가 먼저 채워져요. 읽고 고친 뒤 확정하면 끝이에요.",
    points: ["확정하면 바로 월간 계획안으로", "PDF · HWPX · HWP 로 내려받기"],
    image: {
      src: "/landing/v2/plan-annual.webp",
      width: 1600,
      height: 1074,
      alt: "확정한 2026학년도 연간 보육계획안. 달마다 생활주제와 주별 소주제가 표로 채워져 있다.",
    },
  },
  {
    id: "monthly",
    tab: "월간 계획안",
    title: "연간 주제를 이어받아 한 달을 채워요",
    text: "연간에서 정한 주제와 소주제를 이어받아 주별 놀이를 채워요. 고칠 칸은 눌러서 바로 고쳐요.",
    points: ["주별 바깥놀이 · 안전교육 칸", "확정하면 요일별 주간 계획안으로"],
    image: {
      src: "/landing/v2/plan-monthly.webp",
      width: 1600,
      height: 976,
      alt: "11월 월간계획안 편집 화면. 주별 바깥놀이와 안전교육 칸이 있는 양식이 보인다.",
    },
  },
];

export function PlanTabs() {
  const [active, setActive] = useState(1);
  const step = STEPS[active];

  function moveWithArrows(e: KeyboardEvent<HTMLButtonElement>) {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const next = (active + (e.key === "ArrowRight" ? 1 : STEPS.length - 1)) % STEPS.length;
    setActive(next);
    document.getElementById(`plan-tab-${STEPS[next].id}`)?.focus();
  }

  return (
    <div className={s.plans}>
      <div className={s.planTabs} role="tablist" aria-label="계획안 만드는 순서">
        {STEPS.map((st, i) => (
          <button
            key={st.id}
            id={`plan-tab-${st.id}`}
            type="button"
            role="tab"
            aria-selected={i === active}
            aria-controls="plan-panel"
            tabIndex={i === active ? 0 : -1}
            className={s.planTab}
            onClick={() => setActive(i)}
            onKeyDown={moveWithArrows}
          >
            <span className={s.planStep}>{i + 1}</span>
            {st.tab}
          </button>
        ))}
      </div>
      <div
        id="plan-panel"
        role="tabpanel"
        aria-labelledby={`plan-tab-${step.id}`}
        className={s.planPanel}
        key={step.id}
      >
        <div className={s.planText}>
          <h3 className={s.featureTitle}>{step.title}</h3>
          <p>{step.text}</p>
          <ul>
            {step.points.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </div>
        <div className={s.planShot}>
          <Image
            src={step.image.src}
            alt={step.image.alt}
            width={step.image.width}
            height={step.image.height}
            sizes="(max-width: 860px) 92vw, 640px"
          />
        </div>
      </div>
    </div>
  );
}
