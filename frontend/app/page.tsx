"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { loadClassSettings } from "@/lib/onboarding/settings";

/**
 * 진입점: 반 설정(온보딩)이 끝났으면 /home, 아니면 /onboarding.
 * 지금은 mock 저장소(localStorage) 기준. 로그인/세션 API가 붙으면 서버 컴포넌트 redirect 로 교체.
 */
export default function Entry() {
  const router = useRouter();
  useEffect(() => {
    const s = loadClassSettings();
    router.replace(s?.completedAt ? "/home" : "/onboarding");
  }, [router]);
  return null;
}
