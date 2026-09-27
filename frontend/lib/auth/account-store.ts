// 기존 키와 계정 형식을 유지하며 현재/이전 계정을 안전하게 읽는다.
export const accountKey = (email: string) =>
  `saessak.demoAccount:${encodeURIComponent(email.trim().toLowerCase())}`;
/**
 * 브라우저에 남기는 계정 기록. **비밀번호는 여기 없다** — 서버가 들고 있다
 * (docs/api-spec.md §0). `salt`·`hash` 는 서버 인증이 붙기 전에 쓰던 값이라
 * 예전 기록에만 남아 있다. 읽을 때만 받아 주고 새로 만들지 않는다.
 */
export type Account = {
  name: string;
  email: string;
  salt?: number[];
  hash?: string;
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
      !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v.email)
    )
      return null;
    // 예전 기록의 salt·hash 는 모양이 맞을 때만 옮긴다. 이제 로그인 판정에 쓰지 않는다.
    const legacyHash = typeof v.hash === "string" && /^[a-f0-9]{64}$/.test(v.hash);
    const legacySalt =
      Array.isArray(v.salt) &&
      v.salt.length === 16 &&
      v.salt.every(
        (b: unknown) => typeof b === "number" && Number.isInteger(b) && b >= 0 && b <= 255,
      );
    return {
      email: v.email.trim().toLowerCase(),
      name: typeof v.name === "string" ? v.name : "",
      salt: legacySalt ? v.salt : undefined,
      hash: legacyHash ? v.hash : undefined,
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
