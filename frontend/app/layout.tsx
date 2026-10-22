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
      <body className="font-body bg-cream text-ink antialiased [word-break:keep-all]">
        <MockProvider>{children}</MockProvider>
      </body>
    </html>
  );
}
