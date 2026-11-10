/**
 * 손으로 친 동그라미 — 보육일지 요일에 치는 것과 같은 획(RoutinesPage `CircleMark`).
 * 한 바퀴를 덜 닫아 손으로 그은 자국으로 보인다. 놓을 자리 · 색은 `className` 이 정한다.
 */
export function CircleMark({ className }: { className?: string }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 150 70" preserveAspectRatio="none" className={className}>
      <path
        d="M74 6 C112 4 146 18 143 36 C140 56 100 66 68 64 C32 62 6 50 8 32 C10 14 42 6 78 7"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.6"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
