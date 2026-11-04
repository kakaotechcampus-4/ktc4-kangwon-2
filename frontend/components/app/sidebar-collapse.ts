"use client";

import { useSyncExternalStore } from "react";

/**
 * 사이드바를 **교사가** 접어 두었는지.
 *
 * 화면이 켜는 `compact-shell` 과 다르다. 저쪽은 표를 넓게 써야 하는 편집 화면이 자기 사정으로
 * 켜고, 화면을 떠나면 저절로 펴진다. 이쪽은 교사가 직접 누른 값이라 다음에 들어와도 그대로다.
 *
 * 아직 한 번도 안 눌렀으면 `null` 이고, 그때만 화면이 정한다. 한 번 누르면 교사 쪽이 이긴다.
 */
const KEY = "ssample.sidebar.collapsed";

let pref: boolean | null = null;
let loaded = false;
const listeners = new Set<() => void>();

function readPref(): boolean | null {
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw === "1" ? true : raw === "0" ? false : null;
  } catch {
    // 사생활 보호 창이거나 저장소를 막아 둔 경우. 접기는 이번 방문에만 산다.
    return null;
  }
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function getSnapshot(): boolean | null {
  if (!loaded) {
    pref = readPref();
    loaded = true;
  }
  return pref;
}

export function setSidebarCollapsed(next: boolean) {
  pref = next;
  loaded = true;
  try {
    window.localStorage.setItem(KEY, next ? "1" : "0");
  } catch {
    // 저장은 못 해도 이번 방문에서는 접힌 채로 쓴다.
  }
  listeners.forEach((listener) => listener());
}

export function useSidebarCollapsed(): boolean | null {
  return useSyncExternalStore(subscribe, getSnapshot, () => null);
}
