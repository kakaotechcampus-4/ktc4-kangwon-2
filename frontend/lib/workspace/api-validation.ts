export class BodyLimitError extends Error {}
export async function readLimitedBody(request: Request, maxBytes: number): Promise<ArrayBuffer> {
  if (Number(request.headers.get("content-length") || 0) > maxBytes) throw new BodyLimitError();
  const reader = request.body?.getReader();
  if (!reader) return new ArrayBuffer(0);
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > maxBytes) {
        await reader.cancel();
        throw new BodyLimitError();
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const result = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    result.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return result.buffer;
}

/**
 * 같은 사이트 화면에서 온 요청인지 본다. 아니면 403 응답을, 맞으면 null 을 준다.
 *
 * Origin 은 브라우저만 붙인다 — curl · 스크립트 · 다른 서버는 안 붙인다.
 * 그래서 "없으면 통과"로 두면 검사가 사실상 없는 것과 같다.
 * 쓰는 경로(템플릿 추출)는 공개 배포돼 있고 파일 파싱을 하므로
 * 없는 경우도 막는다(fail-closed). 서버 간 호출이 필요해지면 별도 인증을 붙인다.
 *
 * 비교 대상은 request.url 이 아니라 Host 헤더다. Next 는 --hostname 이 IP 여도
 * request.url 을 localhost 로 채울 때가 있어서, 그걸 기준으로 삼으면
 * 같은 사이트 요청까지 막힌다. 프로토콜은 보지 않는다 — TLS 를 앞단에서 끊으면
 * 브라우저가 보낸 https 와 서버가 보는 http 가 어긋난다.
 */
export function sameOriginGuard(request: Request): Response | null {
  const origin = request.headers.get("origin");
  const host = request.headers.get("host");
  if (origin && host) {
    try {
      if (new URL(origin).host === host) return null;
    } catch {
      // Origin 이 URL 형태가 아니면 통과시키지 않는다.
    }
  }
  return Response.json({ error: "허용되지 않은 요청입니다." }, { status: 403 });
}
