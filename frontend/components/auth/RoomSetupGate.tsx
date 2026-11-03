"use client";

import Link from "next/link";
import { useEffect, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { PageContainer } from "@/components/app/AppLayout";
import { Posty } from "@/components/app/Posty";
import { Icon } from "@/components/app/icons";
import { roomReady } from "@/lib/auth/local-account";
import { useClientState } from "@/lib/hooks/use-client-state";

const OPEN_PATHS = ["/", "/documents"];

// 메인(/)과 문서 보관함(/documents)은 원 · 반이 없어도 열린다(보관함은 원·반 없이도 둘러볼 수 있게). 그 밖의 화면은 원 · 반이 있어야 돌아서 안내 카드를 보인다.
// 브라우저 저장소는 hydration 뒤에만 읽는다(useClientState — 하이드레이션 불일치 방지).
// 화면을 옮길 때마다 다시 읽도록 pathname 을 key 로 건다.
export default function RoomSetupGate({ children }: { children: ReactNode }) {
  return <Gate key={usePathname()}>{children}</Gate>;
}

function Gate({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [ready, setReady] = useClientState<boolean | null>(roomReady, null);
  useEffect(() => {
    const check = () => setReady(roomReady());
    window.addEventListener("pageshow", check);
    window.addEventListener("focus", check);
    window.addEventListener("storage", check);
    return () => {
      window.removeEventListener("pageshow", check);
      window.removeEventListener("focus", check);
      window.removeEventListener("storage", check);
    };
  }, [setReady]);
  if (OPEN_PATHS.includes(pathname) || ready) return children;
  if (ready === null)
    return (
      <p role="status" className="p-10 text-center text-ink-soft">
        이용 정보를 확인하고 있어요.
      </p>
    );
  return (
    <PageContainer>
      <div className="mx-auto mt-10 flex max-w-md flex-col items-center border border-line bg-paper p-8 text-center shadow-pg-hard">
        <span className="relative inline-block">
          <Posty pose="hand" tone="check" face="oh" size={88} label={null} />
          <span
            aria-hidden
            className="absolute left-[76px] -top-[18px] rotate-[14deg] font-display text-[48px] font-bold leading-none text-alert-strong-line"
          >
            !
          </span>
        </span>
        <h1 className="mt-4 font-display text-[24px] font-bold">원·반을 먼저 등록해 주세요</h1>
        <p className="mt-2 text-xs text-ink-soft">계획안과 기록은 우리 반 정보로 만들어져요.</p>
        <Link
          href="/onboarding"
          className="mt-6 inline-flex min-h-11 items-center gap-2 rounded-md border border-primary-line bg-primary px-4 text-xs font-semibold text-white shadow-pg-card hover:bg-primary-hover"
        >
          등록하러 가기
          <Icon name="arrow" className="h-4 w-4" />
        </Link>
      </div>
    </PageContainer>
  );
}
