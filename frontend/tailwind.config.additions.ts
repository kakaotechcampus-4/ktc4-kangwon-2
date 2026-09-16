// ---------------------------------------------------------------------
// 새싹플랜 · 계획안 생성 페이지 — tailwind.config 추가분
//
// 아래 theme.extend 내용을 프로젝트의 기존 tailwind.config.{ts,js}에
// 병합하세요. 색상은 styles/plan-generator-tokens.css 에 정의한
// CSS 변수를 그대로 참조하므로, 라이트/다크 전환이 값 교체 없이 자동으로 됩니다.
//
// Tailwind v4(CSS 기반 @theme)를 쓰는 프로젝트라면, 이 객체 대신
// globals.css 안에 `@theme { --color-cream: var(--pg-cream); ... }`
// 형태로 옮겨 적으면 동일하게 동작합니다.
// ---------------------------------------------------------------------

export const planGeneratorThemeExtend = {
  colors: {
    cream: "var(--pg-cream)",
    paper: "var(--pg-paper)",
    line: "var(--pg-line)",
    ink: "var(--pg-ink)",
    "ink-soft": "var(--pg-ink-soft)",
    sage: { DEFAULT: "var(--pg-sage)", tint: "var(--pg-sage-tint)", ink: "var(--pg-sage-ink)" },
    mint: {
      DEFAULT: "var(--pg-mint)",
      tint: "var(--pg-mint-tint)",
      strong: "var(--pg-mint-strong)",
      ink: "var(--pg-mint-ink)",
    },
    sun: { DEFAULT: "var(--pg-sun)", tint: "var(--pg-sun-tint)", ink: "var(--pg-sun-ink)" },
    peach: {
      DEFAULT: "var(--pg-peach)",
      tint: "var(--pg-peach-tint)",
      strong: "var(--pg-peach-strong)",
      ink: "var(--pg-peach-ink)",
    },
    success: { DEFAULT: "var(--pg-success)", tint: "var(--pg-success-tint)" },
  },
  fontFamily: {
    display: [
      "var(--font-display)",
      "Pretendard",
      "Apple SD Gothic Neo",
      "Malgun Gothic",
      "sans-serif",
    ],
    body: [
      "var(--font-body)",
      "Pretendard",
      "Apple SD Gothic Neo",
      "Malgun Gothic",
      "system-ui",
      "sans-serif",
    ],
    mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
  },
  boxShadow: {
    pg: "var(--pg-shadow)",
  },
};

// tailwind.config.ts 사용 예:
//
// import type { Config } from "tailwindcss";
// import { planGeneratorThemeExtend } from "./tailwind.config.additions";
//
// export default {
//   content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
//   theme: { extend: { ...planGeneratorThemeExtend /* , ...기존 extend 항목 */ } },
// } satisfies Config;
