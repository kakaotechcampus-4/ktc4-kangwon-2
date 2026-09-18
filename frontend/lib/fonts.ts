import localFont from "next/font/local";

/**
 * 자체 호스팅 폰트 (public/fonts, 전부 woff2).
 * - mono: JetBrains Mono — 숫자·코드성 라벨용. 라틴만 남긴 가변 subset(38KB).
 *
 * 한글 폰트(display·body)는 여기에 없다. 둘 다 한 파일이라 첫 화면에서
 * 안 쓰는 글자까지 통째로 받았다(Pretendard 2.0MB · Gowun Dodum 397KB).
 * 유니코드 구간별로 나눈 dynamic subset 으로 바꿨는데, next/font/local 은
 * src 별 unicode-range 를 못 준다. 그래서 styles/*-dynamic-subset.css 가
 * @font-face 와 --font-display · --font-body 를 직접 정의하고,
 * globals.css 가 두 파일을 @import 한다.
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
