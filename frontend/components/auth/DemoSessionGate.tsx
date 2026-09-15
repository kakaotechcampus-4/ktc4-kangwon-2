"use client";

import { useEffect, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { accessRedirect } from "@/lib/auth/local-account";

// 화면 이동을 위한 데모 전용 가드. 실제 인증은 서버에서 별도로 검증해야 한다.
export default function DemoSessionGate({ children, requireOnboarding = false }: { children: ReactNode; requireOnboarding?: boolean }) {
  const router = useRouter();
  const pathname = usePathname();
  const [readyPath, setReadyPath] = useState<string | null>(null);
  useEffect(() => {
    const check = () => {
      const destination = accessRedirect(requireOnboarding);
      setReadyPath(destination ? null : pathname);
      if (destination) router.replace(destination);
    };
    check();
    window.addEventListener("pageshow", check);
    window.addEventListener("focus", check);
    window.addEventListener("storage", check);
    return () => { window.removeEventListener("pageshow", check); window.removeEventListener("focus", check); window.removeEventListener("storage", check); };
  }, [router, pathname, requireOnboarding]);
  return readyPath === pathname ? children : <p role="status" className="p-10 text-center text-ink-soft">이용 정보를 확인하고 있어요.</p>;
}
