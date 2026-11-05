import type { Metadata } from "next";
import type { ReactNode } from "react";
import { fontClassName } from "@/lib/fonts";
import MockProvider from "@/msw/MockProvider";
import "./globals.css"; // styles/plan-generator-tokens.css 내용을 여기에 포함(또는 @import)

export const metadata: Metadata = {
  title: { default: "쌤플", template: "%s · 쌤플" },
  description: "어린이집 교사를 위한 AI 계획안·보육 문서 작성 지원",
  /**
   * 구글 Search Console 소유권 확인.
   *
   * 「URL 접두어 속성」의 HTML 태그 방식을 쓴다.
   * DuckDNS 도 API 로 TXT 레코드를 설정할 수 있지만, 여기서는 페이지의 태그로 확인한다.
   *
   * **이 값은 비밀이 아니다.** `<meta>` 로 페이지에 그대로 실려 누구나 본다 —
   * 그게 소유권 확인의 원리다(그 자리에 글을 올릴 수 있어야 증명이 된다).
   * 그래서 `.env` 가 아니라 여기 둔다. 환경 변수로 두면 서버에서 값을 안 넣었을 때
   * 태그가 조용히 빠지고, 확인이 왜 안 되는지 알기 어렵다.
   *
   * 도메인을 옮기면 구글이 새 값을 준다. 그때 이 줄을 바꾼다.
   */
  verification: { google: "mLlrR5jcO4fPHP_DRMfXCW7UVNcCImmBR9XtwUes2f4" },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko" className={fontClassName}>
      <head>
        {/*
         * 글꼴은 구글 폰트에서 받는다. 여기 `<link>` 로 받는 이유가 있다.
         *
         * globals.css 안에서 `@import` 로 받으면 브라우저가 이렇게 움직인다 —
         * HTML 받기 → 우리 CSS 받기 → 그 안의 `@import` 를 보고 구글 CSS 받기.
         * 세 번이 줄줄이 이어져, 마지막 글꼴 조각은 한참 뒤에야 내려온다.
         * 그동안 글자는 기본 글꼴로 보이다가 뒤늦게 바뀐다 — 「폰트가 깨졌다」는
         * 말은 대개 이 장면이다.
         *
         * `<link>` 로 올리면 HTML 을 읽는 즉시 우리 CSS 와 **나란히** 받는다.
         * preconnect 두 줄은 그 전에 연결(TCP · TLS)을 미리 터 둔다 —
         * 글꼴 파일은 fonts.gstatic.com 에서 오므로 두 곳 다 필요하다.
         * gstatic 쪽은 다른 출처(CORS)라 crossOrigin 이 있어야 연결이 재사용된다.
         */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        {/* 아래 규칙은 옛 pages/_document 기준이다. App Router 의 루트 layout 은
            모든 화면이 함께 쓰는 head 라 한 페이지에만 실리지 않는다. */}
        {/* eslint-disable-next-line @next/next/no-page-custom-font */}
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&family=Gaegu:wght@400;700&display=swap"
        />
      </head>
      <body className="font-body bg-cream text-ink antialiased [word-break:keep-all]">
        <MockProvider>{children}</MockProvider>
      </body>
    </html>
  );
}
