import { selectedAgesFor } from "../onboarding/types";

/**
 * 반 연령을 API 요청 형태로 만든다.
 * 체크박스 선택값을 그대로 배열로 보낸다 — [3,5]는 3세·5세만 뜻하므로
 * age_min/age_max 같은 범위값으로 절대 변환하지 않는다.
 */
export function selectedAgesPayload(value: { selectedAges?: unknown; ageGroup?: unknown }): {
  selected_ages: number[];
} {
  const ages = selectedAgesFor(value);
  if (!ages.length) throw new Error("연령을 하나 이상 선택해주세요.");
  return { selected_ages: [...ages] };
}
