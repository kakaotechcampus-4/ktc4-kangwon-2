import type { ReactNode } from "react";
import DemoSessionGate from "@/components/auth/DemoSessionGate";

/** 온보딩 전 구간에 데모 세션 가드를 한 번만 적용한다. */
export default function OnboardingLayout({ children }: { children: ReactNode }) {
  return <DemoSessionGate>{children}</DemoSessionGate>;
}
