"use client";

import type { ReactNode } from "react";
import { useIsCompact } from "./compact-shell";

/** 사이드바 폭만큼 본문 왼쪽 여백을 준다. 접힌 화면에서는 72px 이다. */
export default function ContentShell({ children }: { children: ReactNode }) {
  const compact = useIsCompact();
  return (
    <div
      className={`min-w-0 pb-[84px] lg:pb-0 transition-[margin] duration-300 ${compact ? "lg:ml-[72px]" : "lg:ml-[232px]"}`}
    >
      {children}
    </div>
  );
}
