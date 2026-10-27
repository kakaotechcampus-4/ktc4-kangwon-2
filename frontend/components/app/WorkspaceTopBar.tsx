"use client";

import Link from "next/link";
import { useSyncExternalStore } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { formatKoreanDate } from "@/lib/greeting";
import { useClientState } from "@/lib/hooks/use-client-state";
import {
  CLASS_SETTINGS_CHANGED,
  loadClassSettings,
  primaryClassFor,
} from "@/lib/onboarding/settings";
import { classServerId } from "@/lib/api/onboarding";
import { routinesScope } from "@/lib/workspace/routines-route";

const subscribeClasses = (changed: () => void) => {
  window.addEventListener(CLASS_SETTINGS_CHANGED, changed);
  window.addEventListener("storage", changed);
  return () => {
    window.removeEventListener(CLASS_SETTINGS_CHANGED, changed);
    window.removeEventListener("storage", changed);
  };
};

/** 사이드바 메뉴 이름과 같아야 한다 — 다르면 어디 있는지 되묻게 된다. */
const PAGE_NAMES: [prefix: string, name: string][] = [
  ["/plans", "계획안"],
  ["/templates", "계획안"],
  ["/trends", "계획안"],
  ["/quick-records", "주간 기록"],
  ["/records", "관찰 기록"],
  ["/compare", "관찰 기록"],
  ["/documents", "문서 보관함"],
  ["/evaluation", "평가 점검"],
  ["/settings", "설정"],
];

/**
 * 본문 맨 위 얇은 띠. 지금 어느 화면에서 어느 반을 보고 있는지만 알린다.
 *
 * 「우리 반 작업실 /」 는 뺐다 — 한 단뿐인 길 안내는 알려주는 것이 없다.
 * 설정 아이콘도 뺐다 — 사이드바에 「설정」이 이미 있다.
 * 모바일에서는 사이드바가 하단으로 내려가므로 여기에 로고를 같이 둔다.
 */
export default function WorkspaceTopBar() {
  const pathname = usePathname() ?? "/";
  const search = useSearchParams();
  const requestedClass = routinesScope(`?${search}`).classId;
  const page = PAGE_NAMES.find(([prefix]) => pathname.startsWith(prefix))?.[1] ?? "우리 반";
  const className = useSyncExternalStore(
    subscribeClasses,
    () => {
      const settings = loadClassSettings();
      if (pathname === "/" && requestedClass !== null)
        return (
          settings?.classes.find((c) => classServerId(c.id) === requestedClass)?.className ?? ""
        );
      return primaryClassFor(settings)?.className ?? "";
    },
    () => "",
  );
  const [today] = useClientState(() => formatKoreanDate(new Date()), "");

  return (
    <header className="sticky top-0 z-20 flex h-[60px] items-center justify-between border-b border-line bg-cream/90 px-4 backdrop-blur lg:px-8">
      <div className="flex items-center gap-3 text-[12px]">
        <Link
          href="/"
          aria-label="쌤플 홈으로"
          className="flex min-h-11 items-center font-bold text-primary-deep lg:hidden"
        >
          Ssample.
        </Link>
        <span className="font-medium text-ink">{page}</span>
      </div>

      <div className="flex items-center gap-3 text-[12px] text-ink-soft">
        <span className="hidden md:inline">{today}</span>
        <span aria-hidden="true" className="hidden h-6 border-l border-line md:inline" />
        <span aria-label="상단 현재 반" className="hidden truncate sm:inline">
          {className}
        </span>
      </div>
    </header>
  );
}
