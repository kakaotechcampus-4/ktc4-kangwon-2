export const runtime = "nodejs";

/**
 * 화면 서버는 모델을 부르지 않는다 — 늘 `available: false` 다. 문서 · 계획안 · 검증 · 트렌드는 모두
 * 백엔드가 부르고, 아이 이름이 들어가는 글은 가명으로 바꾼 뒤 보낸다(ADR-004 · ADR-016 · ADR-057 · ADR-071).
 *
 * 남겨 두는 이유: `WorkspaceUI.tsx` 의 `useAIStatus` 가 이 주소를 읽고, e2e 두 곳이 이 주소를 목으로 막고,
 * nginx 가 이 경로를 화면 서버로 보낸다. 그 셋이 이 주소를 안 쓰게 되면 파일째 지운다.
 */
export async function GET() {
  return Response.json({ available: false }, { headers: { "Cache-Control": "no-store" } });
}
