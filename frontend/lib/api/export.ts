import { ApiError } from "./client";
import { readToken } from "../auth/token";

/**
 * 서버가 만든 hwpx 를 내려받는다 (`.../export/hwp`).
 *
 * `apiRequest` 를 못 쓴다 — 그건 JSON 을 되돌려 주는데 여기는 파일이다.
 * 실패 응답만 JSON 이라, 그때는 같은 모양(`ApiError`)으로 던져 화면이 서버 문구를 띄운다.
 *
 * 파일 이름은 서버가 `Content-Disposition` 에 담아 준다. 한글이라 `filename*` 쪽을 읽고,
 * 없으면 영문 `filename` 을 쓴다. 둘 다 없을 때만 `fallbackName` 을 쓴다 — 이름이 비면
 * 브라우저가 아무 이름이나 붙이고 `.hwpx` 확장자까지 빠져 한글에서 안 열린다.
 */
export async function downloadHwpx(path: string, fallbackName: string): Promise<void> {
  const token = readToken();
  const response = await fetch(path, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    throw new ApiError(response.status, body);
  }

  const disposition = response.headers.get("Content-Disposition") ?? "";
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition)?.[1];
  const plain = /filename="([^"]+)"/i.exec(disposition)?.[1];
  const name = encoded ? decodeURIComponent(encoded) : (plain ?? fallbackName);

  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
