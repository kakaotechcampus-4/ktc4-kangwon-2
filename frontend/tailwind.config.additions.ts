// ---------------------------------------------------------------------
// 쌤플 · tailwind theme.extend
//
// 색은 전부 styles/plan-generator-tokens.css 의 CSS 변수를 가리킨다.
// 여기에 #색상값을 직접 적지 않는다 — 적는 순간 색을 두 군데서 고치게 된다.
// ---------------------------------------------------------------------

export const planGeneratorThemeExtend = {
  colors: {
    cream: "var(--pg-cream)",
    shell: {
      DEFAULT: "var(--pg-shell)",
      line: "var(--pg-shell-line)",
      hover: "var(--pg-shell-hover)",
    },
    note: {
      DEFAULT: "var(--pg-note)",
      line: "var(--pg-note-line)",
      soft: "var(--pg-note-soft)",
      "soft-line": "var(--pg-note-soft-line)",
    },
    tape: "var(--pg-tape)",
    "paper-warm": { DEFAULT: "var(--pg-paper-warm)", line: "var(--pg-paper-warm-line)" },
    paper: "var(--pg-paper)",
    line: "var(--pg-line)",
    ink: "var(--pg-ink)",
    "ink-soft": "var(--pg-ink-soft)",
    primary: {
      DEFAULT: "var(--pg-primary)",
      hover: "var(--pg-primary-hover)",
      line: "var(--pg-primary-line)",
      soft: "var(--pg-primary-soft)",
      tint: "var(--pg-primary-tint)",
      "tint-line": "var(--pg-primary-tint-line)",
      ink: "var(--pg-primary-ink)",
      deep: "var(--pg-primary-deep)",
    },
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
    display: ["var(--font-display)", "Apple SD Gothic Neo", "Malgun Gothic", "sans-serif"],
    body: ["var(--font-body)", "Apple SD Gothic Neo", "Malgun Gothic", "system-ui", "sans-serif"],
    mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
  },
  boxShadow: {
    pg: "var(--pg-shadow)",
    // 버튼용. 도장 찍은 듯 각진 그림자 — 디자인 파일의 3px 4px 0.
    "pg-hard": "var(--pg-shadow-hard)",
    // 카드·쪽지용. 버튼보다 얕다.
    "pg-card": "var(--pg-shadow-card)",
  },
};
