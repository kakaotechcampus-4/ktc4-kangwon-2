import { accountStorageKey } from "../auth/demo-session";
import { API_STORAGE_CONTEXT } from "../api/storage-context";
import type { AgeGroup, PeriodState, PlanType } from "./types";
import type { PlanContent } from "../workspace/plans";
import { ageSelectionLabel, selectedAgesFor, type ClassroomEntry } from "../onboarding/types";
export interface AnnualContext {
  request: {
    age: AgeGroup;
    ageLabel?: string;
    selectedTypes: PlanType[];
    period: PeriodState;
    memo: string;
  };
  classId: string;
  className: string;
  companions: Partial<Record<PlanType, PlanContent>>;
}
const key = () => accountStorageKey("saessak.annualContext.v1:" + API_STORAGE_CONTEXT);
export function saveAnnualContext(id: number, value: AnnualContext) {
  const all = readAll();
  all[id] = value;
  localStorage.setItem(key(), JSON.stringify(all));
}
function readAll(): Record<string, AnnualContext> {
  try {
    const raw = localStorage.getItem(key());
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}
export const loadAnnualContext = (id: number) => readAll()[id];
export const annualContextIds = () =>
  Object.keys(readAll()).map(Number).filter(Number.isSafeInteger);

/** 반 정보만으로 만든 표시 정보. 생성 · 가져오기 화면은 반 말고 다른 조건을 받지 않는다. */
export function classAnnualContext(klass: ClassroomEntry, year: number): AnnualContext {
  const ages = selectedAgesFor(klass);
  return {
    request: {
      age: ages.length === 1 ? (String(ages[0]) as AgeGroup) : "mixed",
      ageLabel: ageSelectionLabel(ages),
      selectedTypes: ["annual"],
      period: {
        annual: { year },
        monthly: { month: 3 },
        weekly: { month: 3, week: 1 },
        daily: { date: "" },
      },
      memo: "",
    },
    classId: klass.id,
    className: klass.className,
    companions: {},
  };
}
