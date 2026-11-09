/**
 * 관찰 기록의 상황 칸을 그날 일과로 채운다 (딸깍 시안 「상황 칸 채우기」).
 *
 * 일과 줄을 누르면 그 이름이, 놀이 시간이면 흥미 영역까지 「실내놀이, 쌓기」로 들어간다.
 * 넣는 말은 짧게 — 서버 `observations.context` 가 50자다.
 */

/** 어린이집에서 흔히 쓰는 흥미 영역 일곱. 「수조작」은 숫자 · 퍼즐 · 끼우기 놀잇감을 두는 곳이다. */
export const PLACES = ["쌓기", "역할", "미술", "수조작", "언어", "과학", "음률"] as const;

export const CONTEXT_MAX = 50;

/** 그날 일과 한 줄 — 시각은 `HH:MM`, 없으면 빈 문자열. */
export interface DaySlot {
  name: string;
  start: string;
  end: string;
}

/**
 * 흥미 영역을 고를 일과인가. 이름에 「놀이」가 있는 실내 일과다.
 * 바깥 · 실외 놀이는 흥미 영역이 교실 안 자리라 묻지 않는다.
 */
export const isIndoorPlay = (name: string) => name.includes("놀이") && !/바깥|실외/.test(name);

export const contextFor = (name: string, place?: string) =>
  (place ? `${name}, ${place}` : name).slice(0, CONTEXT_MAX);

/** 상황 칸 글이 어느 일과 · 어느 영역을 가리키나. 손으로 고친 글이면 둘 다 없다. */
export function pickedSlot(slots: DaySlot[], context: string) {
  for (const slot of slots) {
    if (context === slot.name) return { slot, place: "" };
    const place = context.startsWith(`${slot.name}, `) ? context.slice(slot.name.length + 2) : "";
    if ((PLACES as readonly string[]).includes(place)) return { slot, place };
  }
  return null;
}

/**
 * 지금 시각(`HH:MM`)이 들어 있는 일과. 끝 시각이 없으면 다음 일과 시작까지로 본다.
 * 마지막 일과에 끝이 없으면 고르지 않는다 — 언제 끝났는지 모른다.
 */
export function slotAt(slots: DaySlot[], now: string): DaySlot | null {
  const timed = slots.filter((s) => s.start).sort((a, b) => a.start.localeCompare(b.start));
  for (const [i, slot] of timed.entries()) {
    const end = slot.end || timed[i + 1]?.start || "";
    if (slot.start <= now && end && now < end) return slot;
  }
  return null;
}

/** 지금 시각 `HH:MM` — 보는 사람의 시간대다. */
export function nowTime() {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}
