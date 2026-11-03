const DOW = ["일", "월", "화", "수", "목", "금", "토"];

/** 2026. 09. 07 · 월요일 */
export function formatKoreanDate(d: Date): string {
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}. ${mm}. ${dd} · ${DOW[d.getDay()]}요일`;
}

/**
 * 「11월 3일」 과 「화요일」 로 쪼갠 날짜.
 *
 * 첫 화면 머리글이 날짜를 손글씨로 크게 쓰고 요일만 작게 붙인다 — 한 문장으로 받으면
 * 글자 크기를 둘로 나눌 수 없다.
 */
export function koreanDateParts(d: Date): { day: string; dow: string } {
  return { day: `${d.getMonth() + 1}월 ${d.getDate()}일`, dow: `${DOW[d.getDay()]}요일` };
}

/** 시간대별 인사말 */
export function greetingFor(d: Date): string {
  const h = d.getHours();
  if (h < 5) return "늦은 밤이에요, 선생님 🌙";
  if (h < 12) return "좋은 아침이에요, 선생님 👋";
  if (h < 18) return "좋은 오후예요, 선생님 👋";
  return "좋은 저녁이에요, 선생님 🌙";
}
