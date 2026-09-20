"use client";

import { useState, useSyncExternalStore, type Dispatch, type SetStateAction } from "react";

const subscribe = () => () => {};

/** 서버 렌더와 hydration 렌더에서는 false, 그 직후부터 true. */
export function useHydrated(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );
}

/**
 * localStorage처럼 브라우저에서만 읽을 수 있는 값을 effect 없이 초기값으로 읽는다.
 * hydration 전에는 fallback을 반환하므로 서버 HTML과 어긋나지 않는다.
 * (read는 서버에서도 호출되므로 window 접근을 자체적으로 막아야 한다.)
 */
export function useClientState<T>(read: () => T, fallback: T): [T, Dispatch<SetStateAction<T>>] {
  const hydrated = useHydrated();
  const [value, setValue] = useState<T>(read);
  return [hydrated ? value : fallback, setValue];
}
