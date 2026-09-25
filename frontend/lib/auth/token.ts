/**
 * 서버가 준 로그인 토큰을 들고 있는 곳 (docs/api-spec.md 「인증」).
 *
 * **`sessionStorage` 에 둔다.** 탭을 닫으면 사라진다 — 어린이집 공용 컴퓨터를 쓰는
 * 교사가 로그아웃을 잊어도 다음 사람이 이어받지 못한다. `localStorage` 면 남는다.
 *
 * 토큰 안에는 교사 id 와 만료 시각만 들어 있고 아동 정보는 없다(ADR-013).
 */

const KEY = "saessak.authToken";

export function saveToken(token: string): void {
  try {
    window.sessionStorage.setItem(KEY, token);
  } catch {
    // 사생활 보호 모드 등으로 저장이 막힐 수 있다. 이번 세션만 못 쓰는 것이라 조용히 넘긴다.
  }
}

export function readToken(): string | null {
  try {
    return window.sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function clearToken(): void {
  try {
    window.sessionStorage.removeItem(KEY);
  } catch {
    // 위와 같다.
  }
}
