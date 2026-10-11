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
