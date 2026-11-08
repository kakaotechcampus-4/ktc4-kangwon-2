import type { ReactNode } from "react";

/** 계획안 화면 묶음. 선 색을 이 아래에서만 한 단계 진하게 한다 — globals.css 의 `.lineScope`. */
export default function PlansLayout({ children }: { children: ReactNode }) {
  return <div className="lineScope plansScope">{children}</div>;
}
