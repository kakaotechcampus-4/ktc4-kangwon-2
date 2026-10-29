"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon, type IconName } from "./icons";
import { accountName } from "@/lib/auth/local-account";
import { useClientState } from "@/lib/hooks/use-client-state";
import { loadClassSettings, primaryClassFor, saveClassSettings } from "@/lib/onboarding/settings";
import { AGE_LABEL, type AgeGroup } from "@/lib/plan-generator/types";
import type { ClassroomEntry } from "@/lib/onboarding/types";

interface NavItem {
  key: string;
  label: string;
  href: string;
  icon: IconName;
  match?: (path: string) => boolean;
}

/**
 * 메뉴를 **재료와 결과물**로 가른다.
 *
 * 교사가 친 한 줄(기록)과 그것으로 만든 문서(보육일지·계획안)는 하는 일이 다른데,
 * 이름이 둘 다 「기록」·「문서」로 섞여 있어 어디서 무엇을 하는지 헷갈렸다.
 */
const HOME: NavItem = { key: "home", label: "우리 반", href: "/", icon: "home" };

const GROUPS: { title: string; items: NavItem[] }[] = [
  {
    title: "기록",
    items: [
      {
        key: "records",
        label: "관찰 기록",
        href: "/records",
        icon: "users",
        match: (p) => p.startsWith("/records") || p === "/compare",
      },
      {
        key: "routines",
        label: "일과 기록",
        href: "/routines",
        icon: "edit",
        match: (p) => p.startsWith("/routines"),
      },
      { key: "quick", label: "주간 기록", href: "/quick-records", icon: "record" },
    ],
  },
  {
    title: "문서",
    items: [
      {
        key: "plans",
        label: "계획안",
        href: "/plans",
        icon: "plan",
        match: (p) => p.startsWith("/plans") || p === "/templates" || p === "/trends",
      },
      { key: "docs", label: "문서 보관함", href: "/documents", icon: "doc" },
      { key: "eval", label: "평가 점검", href: "/evaluation", icon: "eval" },
    ],
  },
];

const itemBase =
  "flex items-center gap-3 rounded-md px-3 py-3 min-h-[46px] text-[15px] font-medium transition-all " +
  "lg:flex-row flex-col lg:gap-3 gap-[3px] lg:text-[15px] text-[12px] lg:px-3 px-0.5 lg:py-3 py-1.5 flex-1 lg:flex-none justify-center lg:justify-start";
const activeStyle =
  "border border-primary-tint-line bg-primary-tint font-semibold text-primary-ink shadow-pg-card";
const idle = "border border-transparent text-ink-soft lg:hover:translate-x-1 hover:bg-shell-hover";

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
        classId: klass?.id ?? "",
        classes: settings?.classes ?? [],
      };
    },
    { orgName: "", className: "", age: "", classId: "", classes: [] as ClassroomEntry[] },
  );

  const isActive = (item: NavItem) => (item.match ? item.match(pathname) : item.href === pathname);

  return (
    <aside
      aria-label="주 메뉴"
      className={
        "bg-shell z-30 " +
        // 묶음 제목이 생기며 세로가 길어졌다. 낮은 화면(720p 노트북)에서 맨 아래 설정·로그아웃이
        // 뷰포트 밖으로 밀려 눌리지 않았다. 넘치면 사이드바만 스크롤한다.
        "lg:fixed lg:inset-y-0 lg:left-0 lg:w-[232px] lg:overflow-y-auto lg:border-r lg:border-shell-line lg:flex lg:flex-col " +
        "fixed bottom-0 inset-x-0 flex flex-row border-t border-shell-line px-2 pt-1.5 pb-[calc(6px+env(safe-area-inset-bottom))] lg:px-0 lg:pt-0 lg:pb-0"
      }
    >
      <Link href="/" aria-label="쌤플 홈으로" className="hidden lg:block px-7 pt-7 pb-6">
        <span className="block text-[30px] font-bold tracking-[-0.06em] text-primary-deep">
          Ssample<span className="text-peach-strong">.</span>
        </span>
        <span className="font-display text-xl font-bold text-ink">쌤플</span>
      </Link>

      {/*
        어느 반 작업실에 들어와 있는지. 카드에 꺾쇠가 달려 있어 반 목록이 열릴 것처럼 보이는데
        설정 화면으로 넘어가 버렸다 (수린 점검 4). 반이 둘 이상이면 여기서 바로 바꾼다.
        반이 하나뿐이면 바꿀 것이 없으므로 예전처럼 설정으로 보낸다.
      */}
      <div className="relative mx-4 mb-7 hidden lg:flex items-center gap-2.5 rounded-md border border-line bg-paper p-3 text-left shadow-pg-card">
        <span className="flex h-8 w-8 items-center justify-center rounded-full border border-sun bg-sun-tint text-lg text-sun-ink">
          ☀
        </span>
        <span className="flex-1 min-w-0">
          <span className="block truncate text-[13px] text-ink-soft">
            {room.orgName || "원 정보 없음"}
          </span>
          <span className="mt-1 block truncate text-xs font-medium text-ink">
            {room.className || "반 정보 없음"}
            {room.age && <span className="text-[13px] text-ink-soft"> · {room.age}</span>}
          </span>
        </span>
        <Icon name="chevronDown" className="h-3.5 w-3.5 shrink-0 text-ink-soft" />
        {room.classes.length > 1 ? (
          <select
            aria-label="반 바꾸기"
            value={room.classId}
            onChange={(e) => switchClass(e.target.value)}
            className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
          >
            {room.classes.map((c) => (
              <option key={c.id} value={c.id}>
                {c.className}
                {c.ageGroup ? ` · ${AGE_LABEL[c.ageGroup as AgeGroup]}` : ""}
              </option>
            ))}
          </select>
        ) : (
          <Link href="/settings" aria-label="원·반 설정" className="absolute inset-0" />
        )}
      </div>

      {/* 모바일에서는 하단 띠 한 줄이라 묶음 제목을 접는다 (`contents`). */}
      <nav className="contents lg:block lg:space-y-1 lg:px-3">
        <NavLink item={HOME} active={isActive(HOME)} />
        {GROUPS.map((group) => (
          <div key={group.title} className="contents lg:block lg:pt-4">
            <p className="hidden px-3 pb-1 text-[13px] font-medium text-ink-soft lg:block">
              {group.title}
            </p>
            {group.items.map((item) => (
              <NavLink key={item.key} item={item} active={isActive(item)} />
            ))}
          </div>
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
            className="flex min-h-11 items-center gap-2 text-[13px] text-ink-soft"
          >
            <Icon name="settings" className="h-4 w-4" />
            설정
          </Link>
          <Link href="/logout" className="flex min-h-11 items-center text-[13px] text-ink-soft">
            로그아웃
          </Link>
        </div>

        <div className="mt-5 flex items-center gap-2.5 border-t border-shell-line pt-4">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-sun-tint text-xs text-ink">
            {teacher.slice(0, 1) || "쌤"}
          </span>
          <div className="min-w-0">
            <p className="truncate text-[13px] font-medium text-ink">
              {teacher ? `${teacher} 선생님` : "선생님"}
            </p>
          </div>
        </div>
      </div>
    </aside>
  );
}

/**
 * 주 반을 바꾸고 화면을 다시 읽는다.
 *
 * 각 화면은 들어올 때 담당 반을 한 번만 읽어 둔다. 설정만 고쳐 두면 사이드바 이름만 바뀌고
 * 본문은 그대로 이전 반의 기록을 보여준다. 다시 불러와야 모든 화면이 같은 반을 본다.
 */
function switchClass(classId: string) {
  const settings = loadClassSettings();
  if (!settings || classId === settings.primaryClassId) return;
  if (!saveClassSettings({ ...settings, primaryClassId: classId })) return;
  window.location.reload();
}

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={`${itemBase} ${active ? activeStyle : idle}`}
    >
      <Icon name={item.icon} className="h-[17px] w-[17px] shrink-0" />
      <span>{item.label}</span>
      {active && (
        <span aria-hidden="true" className="ml-auto hidden lg:inline font-display text-lg">
          ↗
        </span>
      )}
    </Link>
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
