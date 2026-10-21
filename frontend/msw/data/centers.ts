import { read, commit } from "./store";
import type { CenterInput, PlanConfig } from "../../lib/api/types";
import type { Greetings } from "../../lib/api/centers";
import { DEFAULT_CHARACTER_MESSAGES, MONTH_ORDER } from "../../lib/onboarding/types";
export const findCenter = (id: number) => read().centers.find((c) => c.id === id);
export const currentCenterId = () => read().centers[0]?.id ?? null;
const defaultGreetings = (): Greetings => ({
  enabled: false,
  items: MONTH_ORDER.map((month) => ({ month, text: DEFAULT_CHARACTER_MESSAGES[month] })),
});
export const findGreetings = (id: number): Greetings => read().greetings[id] ?? defaultGreetings();
export const putGreetings = (id: number, data: Greetings) =>
  commit((db) => {
    const previous = db.greetings[id] ?? defaultGreetings();
    const next = data.enabled ? data : { ...previous, enabled: false };
    db.greetings[id] = next;
    return next;
  });
/** 트렌드봇 설정. **계정마다 따로 두고 새로고침해도 남는다** — 모듈 전역에 들면
 *  다른 계정이 만든 1번 원이 남의 설정을 물려받는다. */
/** 토요일(`weekly_saturday_enabled`)은 칸이 없으면 꺼진 것이다 — 주간 기본은 월~금 (§3-2). */
export const findCenterSettings = (id: number) =>
  read().centerSettings[id] ?? { trends_enabled: false, weekly_saturday_enabled: false };
export const putCenterSettings = (
  id: number,
  patch: { trends_enabled?: boolean; weekly_saturday_enabled?: boolean },
) =>
  commit((db) => {
    const next = { ...(db.centerSettings[id] ?? { trends_enabled: false }), ...patch };
    db.centerSettings[id] = next;
    return next;
  });
export const addCenter = (data: CenterInput) =>
  commit((db) => {
    const c = { ...data, id: db.next++, created_at: new Date().toISOString() };
    db.centers.push(c);
    return c;
  });
export const putConfig = (id: number, data: PlanConfig) =>
  commit((db) => {
    db.configs[id] = data;
    return data;
  });
