"use client";

import { useEffect, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { accessRedirect, roomReady } from "@/lib/auth/local-account";
import { moveLegacyImports } from "@/lib/workspace/store";

// 화면 이동을 위한 데모 전용 가드. 실제 인증은 서버에서 별도로 검증해야 한다.
// 세션은 주소와 상관없으니, 한 번 통과하면 화면을 옮겨도 안내 문장으로 갈아 끼우지 않는다 —
// 갈아 끼우면 사이드바까지 통째로 사라졌다 다시 붙어 화면이 끊긴다. 옮길 때마다 다시 확인은 한다.
export default function DemoSessionGate({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const check = () => {
      const destination = accessRedirect(pathname);
      setReady(!destination);
      if (destination) router.replace(destination);
      // 로그인한 채 새 버전을 연 교사도 예전 증빙을 서버로 옮긴다. 반 · 아동 서버 번호가 있어야
      // 올릴 수 있어서 원 · 반이 준비된 뒤에만 부른다. 옮길 것이 없으면 바로 끝난다.
      else if (roomReady()) void moveLegacyImports().catch(() => {});
    };
    check();
    window.addEventListener("pageshow", check);
    window.addEventListener("focus", check);
    window.addEventListener("storage", check);
    return () => {
      window.removeEventListener("pageshow", check);
      window.removeEventListener("focus", check);
      window.removeEventListener("storage", check);
    };
  }, [router, pathname]);
  return ready ? (
    children
  ) : (
    <p role="status" className="p-10 text-center text-ink-soft">
      이용 정보를 확인하고 있어요.
    </p>
  );
}
