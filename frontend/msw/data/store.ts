import type {
  Center,
  ApiClass,
  ApiChild,
  AnnualPlan,
  PlanConfig,
  MonthlyAuditEvent,
  MonthlyPlan,
  ProfileRef,
  ReadyProfile,
} from "../../lib/api/types";
import type { Greetings } from "../../lib/api/centers";
export interface Database {
  next: number;
  centers: Center[];
  classes: ApiClass[];
  children: ApiChild[];
  plans: MockAnnualPlan[];
  configs: Record<number, PlanConfig>;
  greetings: Record<number, Greetings>;
  monthlyPlans: MonthlyPlan[];
  /** 월간 변경 이력. 키는 plan id. 서버처럼 계획안 단위와 칸(item_id) 단위로 따로 쌓는다. */
  monthlyAudit: Record<number, MockPlanAudit>;
  /** 원 소유 양식 설정 버전. 지금 목업은 READY 만 만든다(DRAFT · ARCHIVED 는 테스트가 넣는다). */
  profiles: MockProfile[];
  /** 원 기본 포인터(키 = center id) · 반 override 포인터(키 = class id). */
  defaultPointers: Record<number, MockPointer>;
  overridePointers: Record<number, MockPointer>;
  /** 테스트 · 개발 전용 승인 Fixture(`template_id@template_version`). 운영 Template 은 승인 대기다. */
  approvedTemplates: string[];
}
/** 연간계획안 + 서버가 목록 · 확정 응답에만 주는 시각. 단건 응답에서는 뺀다. */
export type MockAnnualPlan = AnnualPlan & { created_at: string; confirmed_at: string | null };
/** 저장된 이벤트. 칸 위치(scope · item_id · section_key · week_id)는 읽을 때 칸에서 붙인다. */
export type MockAuditEvent = Omit<
  MonthlyAuditEvent,
  "scope" | "item_id" | "section_key" | "week_id"
>;
export interface MockPlanAudit {
  plan: MockAuditEvent[];
  cells: Record<string, MockAuditEvent[]>;
}
export interface MockProfile {
  center_id: number;
  status: "DRAFT" | "READY" | "ARCHIVED";
  profile: ReadyProfile;
}
export interface MockPointer {
  profile_ref: ProfileRef;
  changed_by: number;
  changed_at: string;
}
const empty = (): Database => ({
  next: 1,
  centers: [],
  classes: [],
  children: [],
  plans: [],
  configs: {},
  greetings: {},
  monthlyPlans: [],
  monthlyAudit: {},
  profiles: [],
  defaultPointers: {},
  overridePointers: {},
  approvedTemplates: [],
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
  return {
    ...parsed,
    greetings: parsed.greetings ?? {},
    monthlyPlans: parsed.monthlyPlans ?? [],
    monthlyAudit: parsed.monthlyAudit ?? {},
    profiles: parsed.profiles ?? [],
    defaultPointers: parsed.defaultPointers ?? {},
    overridePointers: parsed.overridePointers ?? {},
    approvedTemplates: parsed.approvedTemplates ?? [],
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
