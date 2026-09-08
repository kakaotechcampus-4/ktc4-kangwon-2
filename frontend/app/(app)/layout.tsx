import type { ReactNode } from "react";
import AppLayout from "@/components/app/AppLayout";

/** 온보딩 이후 서비스 화면(/home, /plans/…)의 공통 셸: 사이드바 + 콘텐츠 */
export default function AppGroupLayout({ children }: { children: ReactNode }) {
  return <AppLayout>{children}</AppLayout>;
}
