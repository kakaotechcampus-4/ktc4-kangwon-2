"use client";

import type { ReactNode } from "react";
import { useIsCompact } from "./compact-shell";
import { useSidebarCollapsed } from "./sidebar-collapse";

/**
 * 사이드바 폭만큼 본문 왼쪽 여백을 준다. 접히면 75px 이다.
 *
 * 폭을 정하는 규칙은 AppSidebar 와 똑같아야 한다. 한쪽만 고치면 본문이 사이드바 밑으로 들어간다.
 */
export default function ContentShell({ children }: { children: ReactNode }) {
  const compact = useIsCompact();
  const pref = useSidebarCollapsed();
  const collapsed = pref ?? compact;
  return (
    <div className={`min-w-0 pb-[84px] lg:pb-0 ${collapsed ? "lg:ml-[75px]" : "lg:ml-[267px]"}`}>
      {children}
    </div>
  );
}
