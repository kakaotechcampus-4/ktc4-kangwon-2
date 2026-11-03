"use client";

import Link from "next/link";
import { useSyncExternalStore } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import {
  loadClassSettings,
  primaryClassFor,
  subscribeClassSettings,
} from "@/lib/onboarding/settings";
import { classServerId } from "@/lib/api/onboarding";
import { routinesScope } from "@/lib/workspace/routines-route";
import { Wordmark } from "./Wordmark";

/** 사이드바 메뉴 이름과 같아야 한다 — 다르면 어디 있는지 되묻게 된다. */
const PAGE_NAMES: [prefix: string, name: string][] = [
  ["/plans", "계획안"],
  ["/templates", "계획안"],
  ["/trends", "계획안"],
  ["/quick-records", "주간 기록"],
  ["/records/children", "아이들 전부 보기"],
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
    subscribeClassSettings,
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
  return (
    <header className="sticky top-0 z-20 flex h-[60px] items-center justify-between border-b border-line bg-cream/90 px-4 backdrop-blur lg:px-8">
      <div className="flex items-center gap-3 text-[13px]">
        <Link
          href="/"
          aria-label="쌤플 홈으로"
          className="flex min-h-11 items-center font-bold text-primary-deep lg:hidden"
        >
          Ssample.
        </Link>
        <span className="font-medium text-ink">{page}</span>
      </div>

      <div className="flex items-center gap-3 text-[13px] text-ink-soft">
        {/* 날짜는 바로 아래 손글씨 머리글에 크게 있다. 같은 날짜를 두 번 쓰는 대신
            쌤플 표시를 작게 둔다 — 화면을 캡처해 나눌 때 어느 서비스인지 남는다 (PM 선택). */}
        <Wordmark size="xs" label="쌤플 홈으로" className="hidden lg:inline-flex" />
        <span aria-hidden="true" className="hidden h-6 border-l border-line lg:inline" />
        {/* 휴대폰에서도 보인다 — 사이드바 반 카드가 없는 폭에서 지금 반을 알려 주는 곳은 여기뿐이다 */}
        <span aria-label="상단 현재 반" className="max-w-[40vw] truncate">
          {className}
        </span>
      </div>
    </header>
  );
}
