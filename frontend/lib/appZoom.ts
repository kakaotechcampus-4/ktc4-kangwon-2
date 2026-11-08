/**
 * 화면 좌표(getBoundingClientRect · clientX)를 `within` 안의 style px 로 바꾸는 배율.
 * 화면 전체는 globals.css 의 `html { zoom }`(1440 기준 비례 화면)으로, 계획안 문서는 제 `zoom` 으로 줄어 그려진다.
 *
 * zoom 값을 읽지 않고 100px 자를 대 보고 잰다 — 브라우저마다 getBoundingClientRect 에 zoom 이 들어가는지가 달라서,
 * 값을 읽어 나누면 어떤 브라우저에서는 두 번 나눠져 튜토리얼 강조 · 끄는 줄이 제자리를 벗어났다.
 */
export function appZoom(within: HTMLElement = document.body) {
  const ruler = document.createElement("div");
  ruler.style.cssText =
    "position:absolute;left:0;top:0;width:100px;height:0;visibility:hidden;pointer-events:none";
  within.append(ruler);
  const scale = ruler.getBoundingClientRect().width / 100;
  ruler.remove();
  return scale || 1;
}
