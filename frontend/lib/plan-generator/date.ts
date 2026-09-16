/** Date-only inputs must not be converted from UTC into the browser's timezone. */
export function isValidDate(date: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return false;
  const parsed = new Date(`${date}T00:00:00Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === date;
}

export function formatDateLabel(date: string): string {
  if (!isValidDate(date)) return "날짜 미선택";
  const [, month, day] = date.split("-");
  return `${Number(month)}월 ${Number(day)}일`;
}
