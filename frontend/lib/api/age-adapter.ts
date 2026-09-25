import { selectedAgesFor } from "../onboarding/types";

/**
 * 반 연령을 API 요청 형태로 만든다.
 *
 * 체크박스 선택값을 `age_min`·`age_max` 두 값으로 바꾼다 (docs/api-spec.md §2).
 * 「떨어진 조합은 범위로 채운다」 — 만3·만5 만 고른 반은 `3 · 5` 로 나가고, 화면은
 * 「만 3~5세반」으로 표시한다. `classes` 가 범위 컬럼이고 `CHECK (age_min <= age_max)` 가
 * 걸려 있어 「4세만 제외」를 애초에 저장할 수 없다 — 배열로 보내면 422 다.
 *
 * 선택값 자체는 화면 상태(`selectedAges`)에 그대로 남는다. 서버 값을 되읽어 체크박스를
 * 덮어쓰지 않는다 — 그러면 만3·만5 선택이 만3·4·5 로 보이게 된다.
 */
export function ageRangePayload(value: { selectedAges?: unknown; ageGroup?: unknown }): {
  age_min: number;
  age_max: number;
} {
  const ages = selectedAgesFor(value);
  if (!ages.length) throw new Error("연령을 하나 이상 선택해주세요.");
  return { age_min: Math.min(...ages), age_max: Math.max(...ages) };
}
