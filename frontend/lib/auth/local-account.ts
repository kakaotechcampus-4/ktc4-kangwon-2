import { selectedAgesFor } from "../onboarding/types";
// 브라우저에 남기는 계정 기록. **판정은 서버가 한다**(docs/api-spec.md §0).
// 여기 남는 것은 이름과 온보딩 진행 상태처럼 화면이 쓰는 값뿐이다.
//
// 예전에는 `crypto.subtle` 로 비밀번호를 해싱해 이 안에 두고 로그인 판정에 썼다.
// `crypto.subtle` 은 **https 나 localhost 에서만 존재한다** — http 로 배포된 서버에서
// 회원가입이 `Cannot read properties of undefined (reading 'importKey')` 로 죽었다
// (PR #52 멘토 리뷰). 서버가 비밀번호를 들게 되면서 그 해싱 자체가 필요 없어졌다.
import { currentAccountEmail, hasDemoSession } from "./demo-session";
import { accountKey, readAccount, readLegacyAccount, type Account } from "./account-store";
import { loadClassSettings, sanitizeClassSettingsStorage } from "../onboarding/settings";
import { kakaoLogin, login, signup, type AuthResult } from "../api/auth";
import { sanitizeBrowserChildMetadata } from "../privacy/browser-storage";
function read(email = currentAccountEmail()): Account | null {
  return email ? readAccount(email) : null;
}
export function onboardingDestination():
  "/onboarding/center" | "/onboarding/classes" | "/onboarding/children" {
  const settings = loadClassSettings();
  if (
    !settings?.orgName.trim() ||
    !settings.directorName.trim() ||
    !settings.regionProvince ||
    !settings.regionDistrict
  )
    return "/onboarding/center";
  if (
    !settings.classes.length ||
    settings.classes.some(
      (c) => !c.className.trim() || !c.teacherName.trim() || !selectedAgesFor(c).length,
    )
  )
    return "/onboarding/classes";
  return "/onboarding/children";
}
/** 원 · 반이 다 찼는가. 메인 밖 메뉴는 원 · 반이 있어야 돈다. */
export function roomReady(): boolean {
  try {
    return onboardingDestination() === "/onboarding/children";
  } catch {
    return false;
  }
}
export function completeAccountOnboarding(): boolean {
  try {
    if (!hasDemoSession()) return false;
    const account = read();
    if (!account) return false;
    localStorage.setItem(
      accountKey(account.email),
      JSON.stringify({ ...account, onboardingCompletedAt: new Date().toISOString() }),
    );
    return true;
  } catch {
    return false;
  }
}
export function accountName() {
  try {
    return hasDemoSession() ? read()?.name || null : null;
  } catch {
    return null;
  }
}
/**
 * 로그인 안 한 사람을 어디로 보낼지. 주소만 치고 들어온 첫 방문(`/`)은 소개 화면으로,
 * 다른 화면 주소(즐겨찾기 · 링크)로 온 사람은 쓰던 중이니 로그인으로 보낸다.
 */
export function accessRedirect(pathname = ""): string | null {
  if (hasDemoSession()) return null;
  return pathname === "/" ? "/welcome" : "/login";
}
/**
 * 계정을 만들고 로그인한다.
 *
 * **서버가 진짜 계정을 갖는다.** 여기 남는 기록은 이름과 온보딩 진행 상태처럼 화면이
 * 쓰는 값뿐이다 — 비밀번호 판정은 서버가 한다(docs/api-spec.md §0).
 * 브라우저 기록만 남기던 시절의 해시는 로그인 판정에 더 이상 쓰지 않는다.
 */
export async function registerAccount(name: string, email: string, password: string) {
  if (!name.trim() || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()) || password.length < 8)
    throw new Error("이름, 이메일과 8자 이상의 비밀번호를 입력해주세요.");
  if (read(email))
    throw new Error("이미 가입된 이메일이에요. 다른 이메일을 입력하거나 로그인해주세요.");
  const account: Account = { name: name.trim(), email: email.trim().toLowerCase() };
  await signup(account.name, account.email, password);
  // **여기부터는 계정이 이미 서버에 있다.** 브라우저 저장소가 막혀 있어도 원래 오류를 띄우면
  // 가입이 안 된 줄 알고 다시 가입하다 「이미 가입된 이메일」을 본다. 로그인으로 보낸다.
  try {
    localStorage.setItem(accountKey(email), JSON.stringify(account));
    finishSignIn(account);
  } catch {
    throw new Error("가입은 됐어요. 로그인 화면에서 다시 로그인해주세요.");
  }
}
/**
 * 개발용 임시 계정. `NODE_ENV === "development"`에서만 동작하고,
 * 저장은 전용 이메일(test@test.dev) 키로만 이뤄져 다른 계정 데이터와 섞이지 않는다.
 */
const DEV_LOGIN_ID = "test@test";
const DEV_ACCOUNT_EMAIL = "test@test.dev";
const DEV_PASSWORD = "123";
export function isDevLogin(email: string, password: string): boolean {
  return (
    process.env.NODE_ENV === "development" &&
    email.trim().toLowerCase() === DEV_LOGIN_ID &&
    password === DEV_PASSWORD
  );
}
export async function verifyDevAccount(email: string, password: string) {
  if (!isDevLogin(email, password)) throw new Error("이메일 또는 비밀번호를 확인해주세요.");
  if (!read(DEV_ACCOUNT_EMAIL)) {
    localStorage.setItem(
      accountKey(DEV_ACCOUNT_EMAIL),
      JSON.stringify({ name: "개발용 계정", email: DEV_ACCOUNT_EMAIL }),
    );
  }
  window.sessionStorage.setItem("saessak.accountEmail", DEV_ACCOUNT_EMAIL);
}

/**
 * 로그인한다. **판정은 서버가 한다.**
 *
 * 성공하면 토큰이 저장되고(`lib/api/auth.ts`), 이후 모든 요청에 실려 나간다.
 * 브라우저 기록은 이름·온보딩 상태를 위해 없으면 만들어 둔다.
 */
export async function verifyAccount(email: string, password: string): Promise<number | null> {
  return rememberSignIn(await login(email.trim().toLowerCase(), password));
}

/**
 * 카카오 인가 코드로 로그인한다 (ADR-069). 이메일 로그인과 같은 브라우저 기록을 남긴다 —
 * 열쇠가 서버가 돌려준 이메일이라, 같은 이메일로 가입했던 교사는 쓰던 반 설정을 그대로 본다.
 */
export async function verifyKakao(code: string): Promise<number | null> {
  return rememberSignIn(await kakaoLogin(code));
}

function rememberSignIn(result: AuthResult): number | null {
  const email = result.user.email.trim().toLowerCase();
  let account = read(email);
  if (!account) {
    account = { name: result.user.name, email };
    localStorage.setItem(accountKey(email), JSON.stringify(account));
  }
  finishSignIn(account);
  // 원이 있으면 화면이 서버 값으로 채운다 (#291) — 이 브라우저에 기록이 없을 수 있다.
  return result.user.center_id;
}
function finishSignIn(account: Account) {
  // 옛 단일 계정 자료를 먼저 그 계정 키로 옮긴다. 정리가 먼저 돌면 계정을 모르는 공통 키의
  // 예전 증빙이 서버로 옮겨 보기도 전에 지워진다.
  migrateLegacyData(account);
  sanitizeClassSettingsStorage(account.email);
  sanitizeBrowserChildMetadata();
  window.sessionStorage.setItem("saessak.accountEmail", account.email);
}
function migrateLegacyData(account: Account) {
  // 기존 단일 계정의 자료는 그 계정으로만 이전한다. 반 설정 원본도 이후 sanitize한다.
  const legacy = readLegacyAccount();
  if (legacy?.email.toLowerCase() === account.email) {
    for (const base of ["saessak.classSettings", "saessak.workspace.v1"]) {
      const target = `${base}:${encodeURIComponent(account.email)}`;
      const value = localStorage.getItem(base);
      if (value !== null && localStorage.getItem(target) === null)
        localStorage.setItem(target, value);
    }
    if (!localStorage.getItem(accountKey(account.email)))
      localStorage.setItem(accountKey(account.email), JSON.stringify(account));
  }
}
