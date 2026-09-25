import { clearToken } from "./token";

// UI 체험용 세션. 서버 인증이나 계정별 데이터 접근 제어를 제공하지 않는다.
import { readAccount } from "./account-store";
const KEY = "saessak.demoSession";
export function currentAccountEmail(): string | null {
  try {
    return window.sessionStorage.getItem("saessak.accountEmail");
  } catch {
    return null;
  }
}
export function accountStorageKey(base: string): string {
  const email = currentAccountEmail();
  if (!hasDemoSession() || !email) throw new Error("로그인이 필요해요. 다시 로그인해주세요.");
  return `${base}:${encodeURIComponent(email.trim().toLowerCase())}`;
}

export function hasDemoSession(): boolean {
  if (typeof window === "undefined") return false;
  try {
    const email = currentAccountEmail();
    if (window.sessionStorage.getItem(KEY) === "active" && email && readAccount(email)) return true;
  } catch {
    /* 저장소 오류도 로그인 상태로 인정하지 않는다. */
  }
  endDemoSession();
  return false;
}

export function startDemoSession(): boolean {
  try {
    const email = currentAccountEmail();
    if (!email || !readAccount(email)) {
      endDemoSession();
      return false;
    }
    window.sessionStorage.setItem(KEY, "active");
    return true;
  } catch {
    return false;
  }
}

/** 로그아웃. 서버 토큰도 같이 버린다 — 안 버리면 다음 사람이 그 토큰으로 계속 부른다. */
export function endDemoSession(): boolean {
  clearToken();
  try {
    window.sessionStorage.removeItem(KEY);
    window.sessionStorage.removeItem("saessak.accountEmail");
    return true;
  } catch {
    return false;
  }
}
