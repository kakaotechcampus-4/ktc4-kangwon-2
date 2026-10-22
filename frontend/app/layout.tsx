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
   * **DNS 로는 못 한다** — duckdns 무료 계정에는 TXT 레코드를 넣을 칸이 없다.
   * 그래서 「URL 접두어 속성」의 HTML 태그 방식을 쓴다.
   *
   * **빌드 때 박힌다.** 값을 바꾸면 프런트 이미지를 다시 빌드해야 한다
   * (`docker-compose.yml` 의 build args · `frontend/Dockerfile`).
   * 값이 없으면 태그를 아예 넣지 않는다.
   */
  verification: process.env.GOOGLE_SITE_VERIFICATION
    ? { google: process.env.GOOGLE_SITE_VERIFICATION }
    : undefined,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko" className={fontClassName}>
      <body className="font-body bg-cream text-ink antialiased [word-break:keep-all]">
        <MockProvider>{children}</MockProvider>
      </body>
    </html>
  );
}
