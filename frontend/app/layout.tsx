import type { Metadata } from "next";
import type { ReactNode } from "react";
import { fontClassName } from "@/lib/fonts";
import "./globals.css"; // styles/plan-generator-tokens.css 내용을 여기에 포함(또는 @import)

export const metadata: Metadata = {
  title: { default: "새싹플랜", template: "%s · 새싹플랜" },
  description: "어린이집 교사를 위한 AI 계획안·보육 문서 작성 지원",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko" className={fontClassName}>
      <body className="font-body bg-cream text-ink antialiased [word-break:keep-all]">{children}</body>
    </html>
  );
}
