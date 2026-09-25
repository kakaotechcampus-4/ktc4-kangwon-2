import { selectedAgesFor } from "../onboarding/types";
// 브라우저에 저장하는 계정. 실제 서비스 인증은 서버 구현이 필요하다.
import { currentAccountEmail, hasDemoSession } from "./demo-session";
import { accountKey, readAccount, readLegacyAccount, type Account } from "./account-store";
import { loadClassSettings } from "../onboarding/settings";
import { login, signup } from "../api/auth";
async function hash(password: string, salt: number[]) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(password),
    "PBKDF2",
    false,
    ["deriveBits"],
  );
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", hash: "SHA-256", salt: new Uint8Array(salt), iterations: 210000 },
    key,
    256,
  );
  return Array.from(new Uint8Array(bits), (b) => b.toString(16).padStart(2, "0")).join("");
}
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
export function loginDestination(): string {
  try {
    return hasDemoSession() &&
      read()?.onboardingCompletedAt &&
      onboardingDestination() === "/onboarding/children"
      ? "/"
      : onboardingDestination();
  } catch {
    return "/onboarding/center";
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
export function accessRedirect(requireOnboarding = true): string | null {
  if (!hasDemoSession()) return "/login";
  const destination = loginDestination();
  return requireOnboarding && destination !== "/" ? destination : null;
}
/**
 * 계정을 만든다.
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
  await signup(name.trim(), email.trim().toLowerCase(), password);
  const salt = Array.from(crypto.getRandomValues(new Uint8Array(16)));
  const digest = await hash(password, salt);
  if (read(email)) throw new Error("이미 가입된 이메일이에요. 로그인해주세요.");
  localStorage.setItem(
    accountKey(email),
    JSON.stringify({ name: name.trim(), email: email.trim().toLowerCase(), salt, hash: digest }),
  );
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
    const salt = Array.from(crypto.getRandomValues(new Uint8Array(16)));
    const digest = await hash(DEV_PASSWORD, salt);
    localStorage.setItem(
      accountKey(DEV_ACCOUNT_EMAIL),
      JSON.stringify({ name: "개발용 계정", email: DEV_ACCOUNT_EMAIL, salt, hash: digest }),
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
export async function verifyAccount(email: string, password: string) {
  const normalized = email.trim().toLowerCase();
  const result = await login(normalized, password);
  let account = read(normalized);
  if (!account) {
    const salt = Array.from(crypto.getRandomValues(new Uint8Array(16)));
    account = { name: result.user.name, email: normalized, salt, hash: await hash(password, salt) };
    localStorage.setItem(accountKey(normalized), JSON.stringify(account));
  }
  migrateLegacyData(account);
  window.sessionStorage.setItem("saessak.accountEmail", account.email);
}
function migrateLegacyData(account: Account) {
  // 기존 단일 계정의 자료는 그 계정으로만 이전한다. 원본은 보존한다.
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
