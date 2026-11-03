"use client";

import Link from "next/link";
import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { useIsCompact } from "./compact-shell";
import { setSidebarCollapsed, useSidebarCollapsed } from "./sidebar-collapse";
import { Icon, type IconName } from "./icons";
import { SsampleNote } from "./SsampleNote";
import { useClasses } from "@/components/workspace/WorkspaceUI";
import { accountName } from "@/lib/auth/local-account";
import { useClientState } from "@/lib/hooks/use-client-state";
import {
  loadClassSettings,
  primaryClassFor,
  saveClassSettings,
  subscribeClassSettings,
} from "@/lib/onboarding/settings";
import { AGE_LABEL, type AgeGroup } from "@/lib/plan-generator/types";
import type { ClassroomEntry } from "@/lib/onboarding/types";
import { Wordmark } from "./Wordmark";

interface NavItem {
  key: string;
  label: string;
  /** 접힌 75px 줄에 들어갈 짧은 이름. 없으면 `label` 을 그대로 쓴다. */
  short?: string;
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
        short: "관찰",
        href: "/records",
        icon: "users",
        match: (p) => p.startsWith("/records") || p === "/compare",
      },
      {
        key: "routines",
        label: "일과 기록",
        short: "일과",
        href: "/routines",
        icon: "edit",
        match: (p) => p.startsWith("/routines"),
      },
      { key: "quick", label: "주간 기록", short: "주간", href: "/quick-records", icon: "record" },
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
      { key: "docs", label: "문서 보관함", short: "보관함", href: "/documents", icon: "doc" },
      { key: "eval", label: "평가 점검", short: "평가", href: "/evaluation", icon: "eval" },
    ],
  },
];

const itemBase =
  "flex items-center gap-3 rounded-md px-3 py-3 min-h-[46px] text-[15px] font-medium transition-all " +
  "lg:flex-row flex-col lg:gap-3 gap-[3px] lg:text-[15px] text-[12px] lg:px-3 px-0.5 lg:py-3 py-1.5 flex-1 lg:flex-none justify-center lg:justify-start text-center lg:text-left";
const activeStyle = "border border-transparent bg-rail-on font-semibold text-white";
const idle =
  "border border-transparent text-rail-ink-soft lg:hover:translate-x-1 hover:bg-rail-hover";

const NO_ROOM = {
  orgName: "",
  className: "",
  age: "",
  classId: "",
  classes: [] as ClassroomEntry[],
};

/** 지금 보고 있는 원·반과 고를 수 있는 반 목록. */
function readRoom() {
  const settings = loadClassSettings();
  const klass = primaryClassFor(settings);
  return {
    orgName: settings?.orgName ?? "",
    className: klass?.className ?? "",
    age: klass?.ageGroup ? AGE_LABEL[klass.ageGroup as AgeGroup] : "",
    classId: klass?.id ?? "",
    classes: settings?.classes ?? [],
  };
}

/** 데스크톱 좌측 고정 사이드바. 모바일에서는 하단 네비게이션으로 접힌다. */
export default function AppSidebar() {
  const pathname = usePathname() ?? "";
  const [teacher] = useClientState(() => accountName() || "", "");
  const [room, setRoom] = useClientState(readRoom, NO_ROOM);
  // 반을 고르는 자리는 여기 하나뿐이다. **서버에만 있는 반**(다른 선생님이 만든 반,
  // 기기를 바꾼 경우)도 여기 목록에 있어야 그 반으로 갈 수 있다. 들여오면서 저장소에도
  // 남으므로, 아래 구독이 그것을 받아 목록을 그 자리에서 고친다.
  const classes = useClasses();
  useEffect(() => subscribeClassSettings(() => setRoom(readRoom())), [setRoom]);

  const isActive = (item: NavItem) => (item.match ? item.match(pathname) : item.href === pathname);
  // 데스크톱 사이드바는 접었다 폈다 한다. 접으면 75px 아이콘 줄만 남는다.
  //
  // 접힌 줄의 아이콘 가운데와 펼친 줄의 아이콘 가운데를 **같은 자리(37.5px)** 에 둔다.
  // 펼침은 nav 의 px-[17px] + 줄의 px-3(12) + 아이콘 17 의 절반 8.5 이고, 접힘은 폭 75 의 절반이다.
  // 그래서 여닫아도 메뉴 아이콘이 제자리에 있고 글자만 나타났다 사라진다.
  //
  // 교사가 한 번도 안 눌렀으면 편집 화면(compact-shell)이 정하고, 한 번 누르면 그 선택이 이긴다.
  const compact = useIsCompact();
  const pref = useSidebarCollapsed();
  const collapsed = pref ?? compact;

  return (
    <>
      {collapsed && (
        <aside
          aria-label="주 메뉴"
          className="bg-rail z-30 hidden lg:fixed lg:inset-y-0 lg:left-0 lg:flex lg:w-[75px] lg:flex-col lg:items-center lg:gap-0.5 lg:overflow-y-auto lg:border-r lg:border-rail-line lg:py-4"
        >
          <Link
            href="/"
            aria-label="쌤플 홈으로"
            className="flex h-11 w-11 items-center justify-center text-primary-tint-line"
          >
            <Icon name="star" className="h-5 w-5" />
          </Link>
          <button
            type="button"
            onClick={() => setSidebarCollapsed(false)}
            aria-expanded={false}
            aria-label="메뉴 펼치기"
            title="메뉴 펼치기"
            className="mb-2 flex h-11 w-11 items-center justify-center rounded-md text-rail-ink-soft hover:bg-rail-hover"
          >
            <Icon name="panel" className="h-[18px] w-[18px]" />
          </button>
          {[HOME, ...GROUPS.flatMap((g) => g.items)].map((item) => (
            <Link
              key={item.key}
              href={item.href}
              aria-label={item.label}
              title={item.label}
              aria-current={isActive(item) ? "page" : undefined}
              className={`flex w-full flex-col items-center justify-center gap-[3px] rounded-md border py-1.5 text-[11px] font-medium ${isActive(item) ? activeStyle : "border-transparent text-rail-ink-soft hover:bg-rail-hover"}`}
            >
              <Icon name={item.icon} className="h-[17px] w-[17px]" />
              <span>{item.short ?? item.label}</span>
            </Link>
          ))}
          <Link
            href="/settings"
            aria-label="설정"
            title="설정"
            className="mt-auto flex h-11 w-11 items-center justify-center rounded-md text-rail-ink-soft hover:bg-rail-hover"
          >
            <Icon name="settings" className="h-[18px] w-[18px]" />
          </Link>
        </aside>
      )}
      <aside
        aria-label="주 메뉴"
        className={
          "bg-rail z-30 " +
          // 여닫기는 단추로만 한다. 마우스만 올려도 펼쳐지면 글 읽다가 지나가기만 해도 덮인다 (PM).
          (collapsed ? "lg:hidden " : "") +
          // 묶음 제목이 생기며 세로가 길어졌다. 낮은 화면(720p 노트북)에서 맨 아래 설정·로그아웃이
          // 뷰포트 밖으로 밀려 눌리지 않았다. 넘치면 사이드바만 스크롤한다.
          // 그 스크롤바가 267px 안쪽을 15px 쯤 먹어 글자 자리가 화면마다 달라 보였다 (PM 점검).
          // 자리를 늘 잡아 두면 스크롤바가 생기든 말든 폭이 그대로다.
          "lg:fixed lg:inset-y-0 lg:left-0 lg:w-[267px] lg:overflow-y-auto lg:[scrollbar-gutter:stable] lg:border-r lg:border-rail-line lg:flex lg:flex-col " +
          "fixed bottom-0 inset-x-0 flex flex-row border-t border-rail-line px-2 pt-1.5 pb-[calc(6px+env(safe-area-inset-bottom))] lg:px-0 lg:pt-0 lg:pb-0"
        }
      >
        <button
          type="button"
          onClick={() => setSidebarCollapsed(!collapsed)}
          aria-expanded={!collapsed}
          aria-label={collapsed ? "메뉴 펼치기" : "메뉴 접기"}
          title={collapsed ? "메뉴 펼치기" : "메뉴 접기"}
          className="absolute right-3 top-5 hidden h-11 w-11 items-center justify-center rounded-md text-rail-ink-soft hover:bg-rail-hover lg:flex"
        >
          <Icon name="panel" className="h-[18px] w-[18px]" />
        </button>
        {/* 워드마크 왼쪽에 쌤플 마크를 세운다. 글자 S 를 쓰면 바로 옆 Ssample 과 같은 글자가
            두 번 나온다 — 쪽지에 쓰던 ✳ 는 글자와 겹치지 않고 작게 줄여도 안 뭉갠다. */}
        <Wordmark tone="rail" className="hidden px-6 pt-6 pb-5 lg:flex" />

        {/*
        어느 반 작업실에 들어와 있는지. 카드에 꺾쇠가 달려 있어 반 목록이 열릴 것처럼 보이는데
        설정 화면으로 넘어가 버렸다 (수린 점검 4). 반이 둘 이상이면 여기서 바로 바꾼다.
        반이 하나뿐이면 바꿀 것이 없으므로 예전처럼 설정으로 보낸다.
      */}
        <div className="relative mx-4 mb-6 hidden lg:flex items-center gap-2.5 rounded-md border border-rail-card-line bg-rail-card p-3 text-left">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-peach-strong text-lg text-rail">
            ☀
          </span>
          <span className="flex-1 min-w-0">
            <span className="block truncate text-[13px] text-rail-ink-hint">
              {room.orgName || "원 정보 없음"}
            </span>
            <span className="mt-1 block truncate text-xs font-medium text-rail-ink">
              {room.className || "반 정보 없음"}
              {room.age && <span className="text-[13px] text-rail-ink-hint"> · {room.age}</span>}
            </span>
          </span>
          {classes.length > 1 && (
            <Icon name="chevronDown" className="h-3.5 w-3.5 shrink-0 text-rail-ink-soft" />
          )}
          {classes.length > 1 ? (
            <select
              aria-label="반 바꾸기"
              value={room.classId}
              onChange={(e) => switchClass(e.target.value)}
              className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
            >
              {classes.map((c) => (
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
        <nav className="contents lg:block lg:space-y-1 lg:px-[17px]">
          <NavLink item={HOME} active={isActive(HOME)} />
          {GROUPS.map((group) => (
            <div key={group.title} className="contents lg:block lg:pt-4">
              <p className="hidden px-3 pb-1 text-[13px] font-medium text-rail-ink-hint lg:block">
                {group.title}
              </p>
              {group.items.map((item) => (
                <NavLink key={item.key} item={item} active={isActive(item)} />
              ))}
            </div>
          ))}
        </nav>

        <div className="hidden lg:block mt-auto px-5 pb-5">
          {/*
            쪽지는 장식이다. 세로가 모자랄 때 메뉴·설정이 스크롤 뒤로 숨는 것보다
            이것이 먼저 빠지는 쪽이 낫다. 880px 은 사이드바의 나머지가 다 들어가는 높이다.
          */}
          <div className="relative mb-5 hidden pt-[29px] [@media(min-height:880px)]:block">
            {/*
              쪽지 뒤에서 쌤플이 눈만 내민다. 쪽지 윗변이 입을 가리는 높이(pt-[29px])라
              얼굴을 통째로 올려 두는 것보다 「뒤에 있다」가 분명하다.
              색이 다른 작은 장을 겹쳐야 한 장이 아니라 여러 장으로 보인다.
            */}
            <SsampleNote
              tint="plum"
              size={30}
              label={null}
              className="absolute left-[74px] top-[13px] rotate-[9deg]"
            />
            <SsampleNote
              tint="sage"
              size={28}
              label={null}
              className="absolute left-[104px] top-[14px] -rotate-[11deg]"
            />
            <SsampleNote
              tint="clay"
              size={26}
              label={null}
              className="absolute left-[130px] top-[15px] rotate-[15deg]"
            />
            <SsampleNote size={56} label={null} className="absolute left-4 top-0" />
            <div className="relative -rotate-2 border border-note-line bg-note px-4 py-4 shadow-pg-card">
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
          </div>

          <div className="flex items-center justify-between px-1">
            <Link
              href="/settings"
              className="flex min-h-11 items-center gap-2 text-[13px] text-rail-ink-soft"
            >
              <Icon name="settings" className="h-4 w-4" />
              설정
            </Link>
            <Link
              href="/logout"
              className="flex min-h-11 items-center gap-2 text-[13px] text-rail-ink-soft"
            >
              <Icon name="logout" className="h-4 w-4" />
              로그아웃
            </Link>
          </div>

          <div className="mt-5 flex items-center gap-2.5 border-t border-rail-line pt-4">
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-peach-strong text-xs font-semibold text-rail">
              {teacher.slice(0, 1) || "쌤"}
            </span>
            <div className="min-w-0">
              <p className="truncate text-[13px] font-medium text-rail-ink">
                {teacher ? `${teacher} 선생님` : "선생님"}
              </p>
            </div>
          </div>
        </div>
      </aside>
    </>
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
  // 화면들은 주소에 적힌 반을 주 반보다 먼저 본다 (깊은 링크로 들어온 길이니까).
  // 그대로 다시 읽으면 옛 반이 이겨서 바꾼 것이 먹히지 않는다. 반만 떼고 날짜는 둔다.
  const params = new URLSearchParams(window.location.search);
  params.delete("class_id");
  params.delete("class");
  const query = params.toString();
  window.location.href = window.location.pathname + (query ? `?${query}` : "");
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
