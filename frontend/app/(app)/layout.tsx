import type { ReactNode } from "react";
import AppLayout from "@/components/app/AppLayout";
import DemoSessionGate from "@/components/auth/DemoSessionGate";
import RoomSetupGate from "@/components/auth/RoomSetupGate";

/** 서비스 화면(/, /plans/…)의 공통 셸: 사이드바 + 콘텐츠. 메인 밖 화면은 원 · 반이 있어야 열린다. */
export default function AppGroupLayout({ children }: { children: ReactNode }) {
  return (
    <DemoSessionGate>
      <AppLayout>
        <RoomSetupGate>{children}</RoomSetupGate>
      </AppLayout>
    </DemoSessionGate>
  );
}
