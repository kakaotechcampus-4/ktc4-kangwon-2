"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "./icons";
import { formatKoreanDate } from "@/lib/greeting";
import { useClientState } from "@/lib/hooks/use-client-state";
import { loadClassSettings, primaryClassFor } from "@/lib/onboarding/settings";

/** 사이드바 메뉴 이름과 같아야 한다 — 다르면 어디 있는지 되묻게 된다. */
const PAGE_NAMES: [prefix: string, name: string][] = [
  ["/plans", "계획 노트"],
  ["/templates", "계획 노트"],
  ["/trends", "계획 노트"],
  ["/quick-records", "기록 모아보기"],
  ["/records", "관찰 기록"],
  ["/compare", "관찰 기록"],
  ["/documents", "문서 보관함"],
  ["/evaluation", "평가 준비"],
  ["/settings", "설정"],
];

/**
 * 본문 맨 위 얇은 띠. 「우리 반 작업실 / 계획 노트」 처럼 지금 어디인지만 알린다.
 * 모바일에서는 사이드바가 하단으로 내려가므로 여기에 로고를 같이 둔다.
 */
export default function WorkspaceTopBar() {
  const pathname = usePathname() ?? "/";
  const page = PAGE_NAMES.find(([prefix]) => pathname.startsWith(prefix))?.[1] ?? "우리 반";
  const [className] = useClientState(
    () => primaryClassFor(loadClassSettings())?.className ?? "",
    "",
  );
  const [today] = useClientState(() => formatKoreanDate(new Date()), "");

  return (
    <header className="sticky top-0 z-20 flex h-[60px] items-center justify-between border-b border-line bg-cream/90 px-4 backdrop-blur lg:px-8">
      <div className="flex items-center gap-3 text-[11px]">
        <Link
          href="/"
          aria-label="쌤플 홈으로"
          className="flex min-h-11 items-center font-bold text-primary-deep lg:hidden"
        >
          Ssample.
        </Link>
        <span className="hidden text-ink-soft sm:inline">우리 반 작업실</span>
        <span aria-hidden="true" className="hidden text-line sm:inline">
          /
        </span>
        <span className="font-medium text-ink">{page}</span>
      </div>

      <div className="flex items-center gap-3 text-[11px] text-ink-soft">
        <span className="hidden md:inline">{today}</span>
        <span aria-hidden="true" className="hidden h-6 border-l border-line md:inline" />
        <span className="hidden truncate sm:inline">{className}</span>
        <Link href="/settings" aria-label="설정" className="flex min-h-11 items-center">
          <Icon name="settings" className="h-4 w-4" />
        </Link>
      </div>
    </header>
  );
}
