import type { IconName } from "@/components/app/icons";

/**
 * 누리과정 다섯 영역의 그림과 색. 관찰 기록 배지와 홈 칠판 쪽지가 같이 쓴다 —
 * 두 화면에서 같은 영역이 다르게 보이면 같은 영역으로 안 읽힌다.
 *
 * 배지가 전부 같은 보라였다. 열세 줄이 흐르는 목록에서 영역은 **글자를 읽어야만**
 * 갈렸다. 색을 나누면 어느 영역이 비어 있는지 훑기만 해도 보인다.
 *
 * `tone` 은 `Workspace.module.css` 의 `.recordDomain[data-tone]`, `ink` 는 그 배지 글자색과 같은 Tailwind 색이다.
 */
export const DOMAIN_LOOK: Record<string, { icon: IconName; tone: string; ink: string }> = {
  "신체운동·건강": { icon: "body", tone: "body", ink: "text-alert-ink" },
  의사소통: { icon: "talk", tone: "talk", ink: "text-primary-ink" },
  사회관계: { icon: "social", tone: "social", ink: "text-sun-ink" },
  예술경험: { icon: "art", tone: "art", ink: "text-primary-deep" },
  자연탐구: { icon: "nature", tone: "nature", ink: "text-sage-ink" },
};
