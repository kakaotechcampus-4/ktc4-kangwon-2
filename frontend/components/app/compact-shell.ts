import { useEffect, useSyncExternalStore } from "react";

/**
 * 사이드바를 72px 아이콘 줄로 접을지. 표·문서를 넓게 써야 하는 편집 단계(생성 중 · 놀이 고르기 ·
 * 다듬기) 화면이 `useCompactShell()` 로 켠다.
 *
 * **경로가 아니라 화면이 정한다.** 같은 `/plans/annual/{id}` 가 확정 전에는 접고 확정 뒤에는
 * 펼친다. 화면이 사라지면(unmount) 저절로 펼쳐진다.
 */
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
  return useSyncExternalStore(
    subscribe,
    () => active > 0,
    () => false,
  );
}
