/** 계절 탭의 손그림 아이콘 — 꽃 · 해 · 잎 · 눈송이. 모르는 구간 키면 그리지 않는다. */
const PATHS: Record<string, { color: string; d: string; fill?: string; dot?: string }> = {
  // 봄: 꽃잎 다섯 장과 노란 꽃술
  m03_m05: {
    color: "#d9708f",
    fill: "#f9dbe4",
    dot: "#f2b630",
    d: "M9.2 7a2.8 2.8 0 1 0 5.6 0a2.8 2.8 0 1 0 -5.6 0M14 10.5a2.8 2.8 0 1 0 5.6 0a2.8 2.8 0 1 0 -5.6 0M12.1 16a2.8 2.8 0 1 0 5.6 0a2.8 2.8 0 1 0 -5.6 0M6.3 16a2.8 2.8 0 1 0 5.6 0a2.8 2.8 0 1 0 -5.6 0M4.4 10.5a2.8 2.8 0 1 0 5.6 0a2.8 2.8 0 1 0 -5.6 0",
  },
  // 여름: 해와 햇살
  m06_m08: {
    color: "#d98a1f",
    fill: "#fbe7b5",
    d: "M12 7.6c2.6-.1 4.5 1.9 4.4 4.5-.1 2.5-2.1 4.3-4.6 4.2-2.4-.1-4.2-2.1-4.1-4.5.1-2.4 1.9-4.1 4.3-4.2ZM12 2.6v2.3M12 19.2v2.2M2.7 12h2.3M19.1 12.1h2.2M5.4 5.4l1.6 1.7M17 17l1.6 1.6M18.6 5.5 17 7.1M7 17l-1.6 1.6",
  },
  // 가을: 잎 하나와 잎맥
  m09_m11: {
    color: "#b8612f",
    fill: "#f6d9c2",
    d: "M5.2 18.8C4.1 12 8 5.6 18.9 4.6c.9 10.4-5.3 15.1-12.1 14.4ZM5.2 18.8c3.6-4.6 6.6-7.6 10.4-10.4M9.4 14.3l.2-3.3M11.9 11.8l3 .3",
  },
  // 겨울: 눈송이
  m12_m02: {
    color: "#4f84bd",
    d: "M12 3v18M4.3 7.5l15.4 9M4.3 16.5l15.4-9M10 4.8l2 1.8 2-1.8M10 19.2l2-1.8 2 1.8M4.9 10.2l2.6-.6-.8-2.6M19.1 13.8l-2.6.6.8 2.6M6.7 17l.8-2.6-2.6-.6M17.3 7l-.8 2.6 2.6.6",
  },
};

export default function SeasonIcon({ periodKey }: { periodKey: string }) {
  const icon = PATHS[periodKey];
  if (!icon) return null;
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      width="18"
      height="18"
      fill={icon.fill ?? "none"}
      stroke={icon.color}
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="shrink-0"
    >
      <path d={icon.d} />
      {icon.dot && <circle cx="12" cy="12" r="2.2" fill={icon.dot} stroke="none" />}
    </svg>
  );
}
