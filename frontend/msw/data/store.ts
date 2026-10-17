import type { Center, ApiClass, ApiChild, AnnualPlan, PlanConfig } from "../../lib/api/types";
import type { Greetings } from "../../lib/api/centers";
export interface Database {
  next: number;
  centers: Center[];
  classes: ApiClass[];
  children: ApiChild[];
  plans: AnnualPlan[];
  configs: Record<number, PlanConfig>;
  greetings: Record<number, Greetings>;
  /** 원마다 트렌드봇을 켰는지 (FR-808). 기본은 꺼짐 — 칸이 없으면 꺼진 것이다. */
  centerSettings: Record<number, { trends_enabled: boolean }>;
}
const empty = (): Database => ({
  next: 1,
  centers: [],
  classes: [],
  children: [],
  plans: [],
  configs: {},
  greetings: {},
  centerSettings: {},
});
let memory = empty();
function key() {
  return (
    "saessak.mswSS.v1:" +
    encodeURIComponent(
      typeof window === "undefined"
        ? "test"
        : sessionStorage.getItem("saessak.accountEmail") || "anonymous",
    )
  );
}
export function read(): Database {
  if (typeof window === "undefined") return structuredClone(memory);
  const raw = localStorage.getItem(key());
  if (!raw) return empty();
  const parsed = JSON.parse(raw);
  if (
    !parsed ||
    !Number.isInteger(parsed.next) ||
    !["centers", "classes", "children", "plans"].every((k) => Array.isArray(parsed[k]))
  )
    throw new Error("Mock 저장 데이터가 손상되었습니다");
  // 옛 저장본에는 없던 칸이다. 없으면 빈 것으로 읽는다 — 저장본을 버리지 않는다.
  return {
    ...parsed,
    greetings: parsed.greetings ?? {},
    centerSettings: parsed.centerSettings ?? {},
  };
}
export function commit<T>(fn: (db: Database) => T): T {
  const db = read(),
    result = fn(db);
  if (typeof window === "undefined") memory = db;
  else localStorage.setItem(key(), JSON.stringify(db));
  return structuredClone(result);
}
export function resetTestData() {
  memory = empty();
}
