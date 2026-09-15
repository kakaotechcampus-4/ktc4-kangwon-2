import localFont from "next/font/local";

/**
 * 자체 호스팅 폰트 (public/fonts, 전부 woff2).
 * - display: Gowun Dodum — 제목/헤딩용. 라틴·한글 subset을 나눠 필요한 것만 받는다.
 * - body:    Pretendard Variable — 본문/입력 UI용. 한 파일로 100~900 굵기를 모두 제공한다.
 * - mono:    JetBrains Mono — 숫자·코드성 라벨용.
 */
export const display = localFont({
  src: [
    { path: "../public/fonts/GowunDodum-Latin.woff2", weight: "400", style: "normal" },
    { path: "../public/fonts/GowunDodum-Korean.woff2", weight: "400", style: "normal" },
  ],
  variable: "--font-display",
  display: "swap",
  preload: true,
  fallback: ["Pretendard", "Apple SD Gothic Neo", "Malgun Gothic", "sans-serif"],
});

export const body = localFont({
  src: "../public/fonts/PretendardVariable.woff2",
  weight: "45 920",
  style: "normal",
  variable: "--font-body",
  display: "swap",
  preload: true,
  fallback: ["Apple SD Gothic Neo", "Malgun Gothic", "system-ui", "sans-serif"],
});

export const mono = localFont({
  src: "../public/fonts/JetBrainsMono.ttf",
  weight: "100 800",
  variable: "--font-mono",
  display: "swap",
  preload: false,
  fallback: ["ui-monospace", "SFMono-Regular", "monospace"],
});

export const fontClassName = `${display.variable} ${body.variable} ${mono.variable}`;
