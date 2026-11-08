"use client";

import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";
import { isPlanInner } from "./compact-shell";
import { clearSidebarCollapsed } from "./sidebar-collapse";

/**
 * 계획안 첫 화면과 안쪽 화면 사이를 넘을 때 교사가 눌러 둔 접기 · 펼치기를 지운다 — 안 지우면 눌러 둔 값이
 * 이겨서 들어가도 안 접히고 나와도 안 펴진다. 안쪽에서 다시 누르면 다음에 넘을 때까지는 그 값을 따른다.
 * 처음 열 때(새로고침)는 넘은 게 아니라 지우지 않는다. 화면 이동에도 다시 붙지 않는 셸 자리에 둔다.
 */
export default function PlanSidebarReset() {
  const inside = isPlanInner(usePathname());
  const was = useRef(inside);
  useEffect(() => {
    if (was.current === inside) return;
    was.current = inside;
    clearSidebarCollapsed();
  }, [inside]);
  return null;
}
