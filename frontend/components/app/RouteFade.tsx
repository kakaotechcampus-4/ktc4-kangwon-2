"use client";

import { useLayoutEffect, useRef, type ReactNode } from "react";
import { useHydrated } from "@/lib/hooks/use-client-state";

/**
 * 화면을 옮길 때 새 화면을 한 번에 부드럽게 띄운다. `template.tsx` 가 이걸 그대로 내보낸다
 * (template 은 이동마다 새로 붙는다).
 *
 * 화면은 데이터를 뜬 뒤에 가져와서 「불러오는 중」 → 내용으로 몇 번 툭툭 바뀐다. 그 사이를 가리려고
 * 본문을 잠깐 숨겨 두었다가 「불러오는 중」이 걷히면(늦어도 0.6초) 다 차린 화면을 떠오르게 한다.
 * 처음 페이지를 열 때(hydration)와 「움직임 줄이기」는 건드리지 않는다.
 * 감싸는 div 를 두지 않으려고(화면별 높이 · flex 사슬을 건드리지 않게) 표시 span 뒤 형제를 CSS 로 숨긴다 —
 * 화면이 불러오는 중 → 내용으로 뿌리 요소를 갈아 끼워도 함께 숨는다.
 */
const HOLD = "pg-route-hold";
const BUSY = /불러오는 중|확인하고 있어요/;

export default function RouteFade({ children }: { children: ReactNode }) {
  const mark = useRef<HTMLSpanElement>(null);
  const navigated = useRef(useHydrated()); // 첫 렌더 값만 — 클라이언트 이동이면 true
  useLayoutEffect(() => {
    const m = mark.current;
    if (!m || !navigated.current || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const after = () => {
      const out: Element[] = [];
      for (let el = m.nextElementSibling; el; el = el.nextElementSibling) out.push(el);
      return out;
    };
    m.classList.add(HOLD);
    const start = performance.now();
    let raf = 0;
    const tick = () => {
      const busy = after().some((el) => BUSY.test(el.textContent ?? ""));
      if (busy && performance.now() - start < 600) {
        raf = requestAnimationFrame(tick);
        return;
      }
      m.classList.remove(HOLD);
      for (const el of after())
        el.animate(
          [
            { opacity: 0, transform: "translateY(8px)" },
            { opacity: 1, transform: "none" },
          ],
          { duration: 260, easing: "cubic-bezier(.2,.7,.3,1)" },
        );
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      m.classList.remove(HOLD);
    };
  }, []);
  return (
    <>
      <style>{`.${HOLD} ~ * { opacity: 0 }`}</style>
      <span ref={mark} hidden />
      {children}
    </>
  );
}
