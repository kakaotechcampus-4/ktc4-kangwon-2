import type { IconName } from "@/components/app/icons";

/**
 * 누리과정 다섯 영역의 그림과 색. 관찰 기록 · 아이별 기록 · 관찰일지가 같이 쓴다 —
 * 화면마다 같은 영역이 다르게 보이면 같은 영역으로 안 읽힌다.
 *
 * 배지가 전부 같은 보라였다. 열세 줄이 흐르는 목록에서 영역은 **글자를 읽어야만**
 * 갈렸다. 색을 나누면 어느 영역이 비어 있는지 훑기만 해도 보인다. `tone` 은 화면 CSS 의
 * `data-tone` 값이다. 2축(일상생활 · 놀이활동)은 그림이 없어 여기 없다 — 화면이 글자로 둔다.
 */
export const DOMAIN_LOOK: Record<string, { icon: IconName; tone: string }> = {
  "신체운동·건강": { icon: "body", tone: "body" },
  의사소통: { icon: "talk", tone: "talk" },
  사회관계: { icon: "social", tone: "social" },
  예술경험: { icon: "art", tone: "art" },
  자연탐구: { icon: "nature", tone: "nature" },
};
