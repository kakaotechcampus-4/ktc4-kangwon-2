/**
 * 화면 전체 배율(globals.css 의 `html { zoom }` — 1440 기준 비례 화면).
 * getBoundingClientRect · clientX · innerWidth 는 실제 화면 px 이고, 그 안에서 쓰는 style px 는 이 배율만큼
 * 줄어 그려진다. 그래서 화면 좌표를 style 에 넣을 때는 이 값으로 나눈다.
 */
export function appZoom() {
  return Number(getComputedStyle(document.documentElement).zoom) || 1;
}
