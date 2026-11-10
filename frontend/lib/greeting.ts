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

/** 이름 끝의 호칭. 교사가 이름 칸에 호칭까지 적는 일이 잦다. */
const TITLE_END = /\s*(선생님|교사|쌤)$/;

/**
 * 「김하늘 선생님」 — 이름 뒤 호칭을 한 번만 붙인다.
 *
 * 이름이 이미 「선생님」으로 끝나면 적은 그대로 두고, 「교사」 · 「쌤」으로 끝나면 떼고
 * 「선생님」을 붙인다. 사이드바 · 교사 메뉴 · 설정이 같이 쓴다 — 한 곳만 고치면 화면마다
 * 다른 이름이 보인다.
 */
export function teacherTitle(name: string | null | undefined): string {
  const written = (name ?? "").trim();
  const base = written.replace(TITLE_END, "").trim();
  if (!base) return "선생님";
  return written.endsWith("선생님") ? written : `${base} 선생님`;
}
