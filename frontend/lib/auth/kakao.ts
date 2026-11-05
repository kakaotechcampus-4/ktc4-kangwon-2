/**
 * 카카오 로그인 — 동의 화면으로 보내고, 돌아온 `state` 를 맞춰 본다 (ADR-063 · docs/api-spec.md §0-1).
 *
 * **`state` 는 `sessionStorage` 에 둔다.** 다른 사이트가 우리 콜백 주소로 남의 코드를 밀어 넣는 것을
 * 막는다(CSRF). 탭을 닫으면 사라지고, 한 번 꺼내면 지운다 — 같은 값을 두 번 받지 않는다.
 * 아동 정보가 아니다(ADR-013).
 */
import { kakaoAuthorizeUrl } from "../api/auth";

const KEY = "ssample.kakaoState";

/** 24바이트 무작위 → base64url 32자. 서버가 받는 모양(16~128자, A-Z a-z 0-9 _ -)에 맞춘다. */
export function newKakaoState(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(24));
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

/** 동의 화면 주소를 서버에서 받아 이동한다. 서버에 키가 없으면 503 이 그대로 올라간다. */
export async function startKakaoLogin(): Promise<void> {
  const state = newKakaoState();
  window.sessionStorage.setItem(KEY, state);
  const { url } = await kakaoAuthorizeUrl(state);
  window.location.assign(url);
}

/** 돌아온 `state` 가 이 탭에서 보낸 것과 같은가. 맞든 틀리든 저장한 값은 지운다. */
export function takeKakaoState(returned: string | null): boolean {
  let saved: string | null = null;
  try {
    saved = window.sessionStorage.getItem(KEY);
    window.sessionStorage.removeItem(KEY);
  } catch {
    return false;
  }
  return !!saved && saved === returned;
}
