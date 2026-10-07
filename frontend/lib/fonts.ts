import localFont from "next/font/local";

/**
 * 자체 호스팅 폰트 (public/fonts, 전부 woff2).
 * - mono: JetBrains Mono — 숫자·코드성 라벨용. 라틴만 남긴 가변 subset(38KB).
 *
 * 한글 폰트(display·body)는 여기에 없다. next/font/local 은 src 별
 * unicode-range 를 못 줘서 한글 한 덩어리를 통째로 받게 되는데, 구글 폰트는
 * 이미 구간별로 쪼개 보낸다. 그래서 Noto Sans KR · Gaegu 는 globals.css 의
 * @import 로 받고, --font-body · --font-display 도 거기서 정한다.
 */
export const mono = localFont({
  src: "../public/fonts/JetBrainsMono-Latin.woff2",
  weight: "100 800",
  variable: "--font-mono",
  display: "swap",
  preload: false,
  fallback: ["ui-monospace", "SFMono-Regular", "monospace"],
});

export const fontClassName = mono.variable;
