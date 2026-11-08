import { useEffect, useSyncExternalStore } from "react";
import { usePathname } from "next/navigation";

/**
 * 사이드바를 75px 아이콘 줄로 접을지.
 *
 * - **계획안 안쪽 화면(`/plans/…`)은 주소로 접는다.** 만들기 · 이어 쓰기 · 확정본 보기 모두다.
 *   주소는 처음 그릴 때부터 알기 때문에, 새로고침해도 펼쳤다가 접히며 깜빡이지 않는다.
 *   계획안 첫 화면(`/plans`)은 펼친다.
 * - 그 밖의 편집 화면은 자기 사정으로 `useCompactShell()` 을 켠다. 화면이 사라지면(unmount) 저절로 펼쳐진다.
 */
export const isPlanInner = (pathname: string) => pathname.startsWith("/plans/");

let active = 0;
const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function change(delta: number) {
  active += delta;
  listeners.forEach((listener) => listener());
}

export function useCompactShell(on = true) {
  useEffect(() => {
    if (!on) return;
    change(1);
    return () => change(-1);
  }, [on]);
}

export function useIsCompact() {
  const plan = isPlanInner(usePathname());
  const screen = useSyncExternalStore(
    subscribe,
    () => active > 0,
    () => false,
  );
  return plan || screen;
}
