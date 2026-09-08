"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { loadClassSettings } from "@/lib/onboarding/settings";
import { Icon, type IconName } from "./icons";

interface NavItem {
  key: string;
  label: string;
  href?: string; // 없으면 "준비 중"
  icon: IconName;
  match?: (path: string) => boolean;
}

const NAV: NavItem[] = [
  { key: "home", label: "홈", href: "/home", icon: "home" },
  { key: "plans", label: "계획안", href: "/plans/create", icon: "plan", match: (p) => p.startsWith("/plans") },
  { key: "records", label: "기록", icon: "record" },
  { key: "docs", label: "문서", icon: "doc" },
  { key: "eval", label: "평가제", icon: "eval" },
];

/**
 * 좌측 고정 사이드바 (데스크톱) / 하단 네비게이션 (모바일).
 * Active 메뉴는 Main 을 옅게 탄 sage-tint 배경 + Dark 아이콘.
 */
export default function AppSidebar({
  teacherName = "김민지 선생님", // 가입 시 저장된 값
}: {
  teacherName?: string;
}) {
  const pathname = usePathname() ?? "";
  const [className, setClassName] = useState("햇살반");
  useEffect(() => {
    const s = loadClassSettings();
    if (s?.className) setClassName(s.className);
  }, []);

  const isActive = (item: NavItem) => (item.match ? item.match(pathname) : item.href === pathname);

  const itemBase =
    "flex items-center gap-3 rounded-[14px] px-3.5 py-3 min-h-[46px] text-[15px] text-ink-soft transition-colors " +
    "lg:flex-row flex-col lg:gap-3 gap-[3px] lg:text-[15px] text-[10.5px] lg:px-3.5 px-0.5 lg:py-3 py-1.5 flex-1 lg:flex-none justify-center lg:justify-start";
  const active = "bg-sage-tint text-ink lg:font-bold font-medium [&>svg]:text-sage-ink";
  const idle = "hover:bg-cream hover:text-ink";

  return (
    <aside
      aria-label="주 메뉴"
      className={
        "bg-paper border-line z-30 " +
        // desktop: sticky left column
        "lg:sticky lg:top-0 lg:h-screen lg:w-[232px] lg:border-r lg:flex lg:flex-col lg:gap-1.5 lg:px-3.5 lg:pt-[18px] lg:pb-3.5 " +
        // mobile: bottom nav
        "fixed bottom-0 inset-x-0 flex flex-row border-t px-2 pt-1.5 pb-[calc(6px+env(safe-area-inset-bottom))] lg:static lg:inset-auto"
      }
    >
      <Link href="/home" className="hidden lg:flex items-center gap-2.5 px-2 pt-1.5 pb-5">
        <span className="inline-flex items-center justify-center w-[34px] h-[34px] rounded-[11px] bg-sage-tint">
          <svg width="22" height="22" viewBox="0 0 30 30" aria-hidden="true">
            <circle cx="12" cy="15" r="9" className="fill-sage" />
            <circle cx="20" cy="10" r="6" className="fill-sage-ink" />
          </svg>
        </span>
        <span className="font-display text-xl text-ink">새싹플랜</span>
      </Link>

      <nav className="contents lg:flex lg:flex-col lg:gap-1">
        {NAV.map((item) =>
          item.href ? (
            <Link key={item.key} href={item.href} aria-current={isActive(item) ? "page" : undefined} className={`${itemBase} ${isActive(item) ? active : idle}`}>
              <Icon name={item.icon} className="w-5 h-5 shrink-0" />
              <span>{item.label}</span>
            </Link>
          ) : (
            <span key={item.key} className={`${itemBase} opacity-60 cursor-default`} title="준비 중인 메뉴예요">
              <Icon name={item.icon} className="w-5 h-5 shrink-0" />
              <span>{item.label}</span>
              <span className="hidden lg:inline ml-auto font-mono text-[10px] tracking-wide text-ink-soft border border-line rounded-full px-1.5 py-px">준비 중</span>
            </span>
          ),
        )}
      </nav>

      <div className="contents lg:flex lg:flex-col lg:gap-1.5 lg:mt-auto">
        <Link href="/onboarding" aria-current={pathname === "/onboarding" ? "page" : undefined} className={`${itemBase} ${idle}`}>
          <Icon name="settings" className="w-5 h-5 shrink-0" />
          <span>설정</span>
        </Link>
        <Link href="/onboarding" title="반 설정 다시 보기" className="hidden lg:flex items-center gap-2.5 px-2 pt-3.5 pb-1.5 mt-2 border-t border-line">
          <span className="inline-flex items-center justify-center w-9 h-9 rounded-full bg-sage-tint text-sage-ink font-bold text-sm shrink-0">{teacherName.slice(0, 1)}</span>
          <span className="min-w-0">
            <span className="block text-sm font-bold text-ink truncate">{teacherName}</span>
            <span className="block text-xs text-ink-soft truncate">{className} 담임</span>
          </span>
          <Icon name="chevron" className="w-4 h-4 ml-auto text-ink-soft" />
        </Link>
      </div>
    </aside>
  );
}
