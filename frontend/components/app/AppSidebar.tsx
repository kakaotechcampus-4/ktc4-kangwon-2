"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon, type IconName } from "./icons";
import { accountName } from "@/lib/auth/local-account";
import { useClientState } from "@/lib/hooks/use-client-state";
import { loadClassSettings, primaryClassFor } from "@/lib/onboarding/settings";
import { AGE_LABEL, type AgeGroup } from "@/lib/plan-generator/types";

interface NavItem {
  key: string;
  label: string;
  href: string;
  icon: IconName;
  match?: (path: string) => boolean;
}

/** 이름은 디자인의 작업실 용어를 따른다 — 「계획안」보다 「계획 노트」가 교사의 말이다. */
const NAV: NavItem[] = [
  { key: "home", label: "우리 반", href: "/", icon: "home" },
  {
    key: "plans",
    label: "계획 노트",
    href: "/plans",
    icon: "plan",
    match: (p) => p.startsWith("/plans") || p === "/templates" || p === "/trends",
  },
  {
    key: "records",
    label: "관찰 기록",
    href: "/records",
    icon: "users",
    match: (p) => p.startsWith("/records") || p === "/compare",
  },
  { key: "docs", label: "문서 보관함", href: "/documents", icon: "doc" },
  { key: "eval", label: "평가 준비", href: "/evaluation", icon: "eval" },
];

/** 데스크톱 좌측 고정 사이드바. 모바일에서는 하단 네비게이션으로 접힌다. */
export default function AppSidebar() {
  const pathname = usePathname() ?? "";
  const [teacher] = useClientState(() => accountName() || "", "");
  const [room] = useClientState(
    () => {
      const settings = loadClassSettings();
      const klass = primaryClassFor(settings);
      return {
        orgName: settings?.orgName ?? "",
        className: klass?.className ?? "",
        age: klass?.ageGroup ? AGE_LABEL[klass.ageGroup as AgeGroup] : "",
      };
    },
    { orgName: "", className: "", age: "" },
  );

  const isActive = (item: NavItem) => (item.match ? item.match(pathname) : item.href === pathname);

  const itemBase =
    "flex items-center gap-3 rounded-md px-3 py-3 min-h-[46px] text-[13px] font-medium transition-all " +
    "lg:flex-row flex-col lg:gap-3 gap-[3px] lg:text-[13px] text-[10.5px] lg:px-3 px-0.5 lg:py-3 py-1.5 flex-1 lg:flex-none justify-center lg:justify-start";
  const active =
    "border border-primary-tint-line bg-primary-tint font-semibold text-primary-ink shadow-pg-card";
  const idle =
    "border border-transparent text-ink-soft lg:hover:translate-x-1 hover:bg-shell-hover";

  return (
    <aside
      aria-label="주 메뉴"
      className={
        "bg-shell z-30 " +
        "lg:fixed lg:inset-y-0 lg:left-0 lg:w-[232px] lg:border-r lg:border-shell-line lg:flex lg:flex-col " +
        "fixed bottom-0 inset-x-0 flex flex-row border-t border-shell-line px-2 pt-1.5 pb-[calc(6px+env(safe-area-inset-bottom))] lg:px-0 lg:pt-0 lg:pb-0"
      }
    >
      <Link href="/" aria-label="쌤플 홈으로" className="hidden lg:block px-7 pt-7 pb-6">
        <span className="block text-[30px] font-bold tracking-[-0.06em] text-primary-deep">
          Ssample<span className="text-peach-strong">.</span>
        </span>
        <span className="font-display text-xl font-bold text-ink">쌤플</span>
      </Link>

      {/* 어느 반 작업실에 들어와 있는지. 반을 바꾸는 건 설정에서 한다. */}
      <Link
        href="/settings"
        className="hidden lg:flex mx-4 mb-7 items-center gap-2.5 rounded-md border border-line bg-paper p-3 text-left shadow-pg-card"
      >
        <span className="flex h-8 w-8 items-center justify-center rounded-full border border-sun bg-sun-tint text-lg text-sun-ink">
          ☀
        </span>
        <span className="flex-1 min-w-0">
          <span className="block truncate text-[11px] text-ink-soft">
            {room.orgName || "원 정보 없음"}
          </span>
          <span className="mt-1 block truncate text-xs font-medium text-ink">
            {room.className || "반 정보 없음"}
            {room.age && <span className="text-[11px] text-ink-soft"> · {room.age}</span>}
          </span>
        </span>
        <Icon name="chevronDown" className="h-3.5 w-3.5 shrink-0 text-ink-soft" />
      </Link>

      <p className="hidden lg:block px-6 pb-3 text-[9px] tracking-[0.18em] text-ink-soft">
        MY WORKSPACE
      </p>

      <nav className="contents lg:block lg:space-y-1 lg:px-3">
        {NAV.map((item) => (
          <Link
            key={item.key}
            href={item.href}
            aria-current={isActive(item) ? "page" : undefined}
            className={`${itemBase} ${isActive(item) ? active : idle}`}
          >
            <Icon name={item.icon} className="h-[17px] w-[17px] shrink-0" />
            <span>{item.label}</span>
            {isActive(item) && (
              <span aria-hidden="true" className="ml-auto hidden lg:inline font-display text-lg">
                ↗
              </span>
            )}
          </Link>
        ))}
      </nav>

      <div className="hidden lg:block mt-auto px-5 pb-5">
        <div className="relative mb-6 -rotate-2 border border-note-line bg-note px-4 py-5 shadow-pg-card">
          <Tape />
          <p className="font-display text-[22px] font-bold leading-tight text-ink">
            쌤의 계획이
            <br />
            쉬워지는 순간,
            <br />
            <span className="text-primary">쌤플.</span>
          </p>
          <span
            aria-hidden="true"
            className="absolute bottom-3 right-3 -rotate-12 font-display text-3xl text-sun"
          >
            ✳
          </span>
        </div>

        <div className="flex items-center justify-between px-1">
          <Link
            href="/settings"
            className="flex min-h-11 items-center gap-2 text-[11px] text-ink-soft"
          >
            <Icon name="settings" className="h-4 w-4" />
            설정
          </Link>
          <Link href="/logout" aria-label="로그아웃" title="로그아웃">
            <Icon name="help" className="h-4 w-4 text-ink-soft" />
          </Link>
        </div>

        <div className="mt-5 flex items-center gap-2.5 border-t border-shell-line pt-4">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-sun-tint text-xs text-ink">
            {teacher.slice(0, 1) || "쌤"}
          </span>
          <div className="min-w-0">
            <p className="truncate text-[11px] font-medium text-ink">
              {teacher ? `${teacher} 선생님` : "선생님"}
            </p>
            <p className="mt-0.5 text-[9px] text-ink-soft">오늘도 수고 많으세요.</p>
          </div>
        </div>
      </div>
    </aside>
  );
}

/** 쪽지 윗변에 붙인 종이테이프. 장식이라 읽어주지 않는다. */
function Tape() {
  return (
    <span
      aria-hidden="true"
      className="pointer-events-none absolute -top-3 left-1/2 h-6 w-20 -translate-x-1/2 -rotate-3 border-x border-white/60 bg-tape shadow-[0_1px_2px_rgba(106,96,80,.09)]"
    />
  );
}
