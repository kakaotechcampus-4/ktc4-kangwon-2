// 기존 키와 계정 형식을 유지하며 현재/이전 계정을 안전하게 읽는다.
export const accountKey = (email: string) =>
  `saessak.demoAccount:${encodeURIComponent(email.trim().toLowerCase())}`;
export type Account = {
  name: string;
  email: string;
  salt: number[];
  hash: string;
  onboardingCompletedAt?: string;
};
function parse(raw: string | null): Account | null {
  try {
    const v = JSON.parse(raw || "null");
    if (
      !v ||
      typeof v !== "object" ||
      Array.isArray(v) ||
      typeof v.email !== "string" ||
      !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v.email) ||
      typeof v.hash !== "string" ||
      !/^[a-f0-9]{64}$/.test(v.hash) ||
      !Array.isArray(v.salt) ||
      v.salt.length !== 16 ||
      !v.salt.every(
        (b: unknown) => typeof b === "number" && Number.isInteger(b) && b >= 0 && b <= 255,
      )
    )
      return null;
    return {
      email: v.email.trim().toLowerCase(),
      name: typeof v.name === "string" ? v.name : "",
      salt: v.salt,
      hash: v.hash,
      onboardingCompletedAt:
        typeof v.onboardingCompletedAt === "string" &&
        Number.isFinite(Date.parse(v.onboardingCompletedAt))
          ? v.onboardingCompletedAt
          : undefined,
    };
  } catch {
    return null;
  }
}
export function readCurrentAccount(email: string): Account | null {
  const account = parse(window.localStorage.getItem(accountKey(email)));
  return account?.email === email.trim().toLowerCase() ? account : null;
}
export function readLegacyAccount(): Account | null {
  return parse(window.localStorage.getItem("saessak.demoAccount"));
}
export function readAccount(email: string): Account | null {
  const current = readCurrentAccount(email);
  if (current) return current;
  const legacy = readLegacyAccount();
  return legacy?.email === email.trim().toLowerCase() ? legacy : null;
}
