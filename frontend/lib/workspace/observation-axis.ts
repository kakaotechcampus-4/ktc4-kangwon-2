/**
 * 관찰 기록의 영역 축 (backend `observations/models.py` AXES).
 *
 * **원마다 다르다.** 교사가 쓴 관찰일지 3건을 재 보니 2건이 누리과정 5영역이 아니라
 * 일상생활 · 놀이활동 2축이었다 (`docs/references/관찰일지-서술-기준.md`).
 * 5영역으로 박아 두면 2축을 쓰는 원은 관찰 기록을 아예 넣을 수 없다.
 *
 * 목록을 서버와 두 군데 적는다 — 서버가 받는 값과 화면이 고르게 하는 값이 같아야 한다.
 * 어긋나면 교사가 고른 값이 422 로 돌아온다. 바꿀 때 둘 다 고친다.
 *
 * **이 파일은 아무것도 import 하지 않는다.** `model.ts` 가 여기를 다시 내보내는데,
 * React 나 API 클라이언트를 끌어오면 그것들을 쓰지 않는 쪽까지 같이 딸려 온다.
 * 축을 실제로 읽어 오는 일은 `lib/hooks/use-observation-domains.ts` 가 한다.
 */
export const NURI_DOMAINS = [
  "신체운동·건강",
  "의사소통",
  "사회관계",
  "예술경험",
  "자연탐구",
] as const;
export const DAILY_PLAY_DOMAINS = ["일상생활", "놀이활동"] as const;

export type ObservationAxis = "NURI_5" | "DAILY_PLAY_2";
export const AXES: Record<ObservationAxis, readonly string[]> = {
  NURI_5: NURI_DOMAINS,
  DAILY_PLAY_2: DAILY_PLAY_DOMAINS,
};
export const DEFAULT_AXIS: ObservationAxis = "NURI_5";

/** 축을 사람의 말로. 설정 화면이 고르게 할 때 쓴다. */
export const AXIS_LABELS: Record<ObservationAxis, string> = {
  NURI_5: "누리과정 5영역",
  DAILY_PLAY_2: "일상생활 · 놀이활동",
};
