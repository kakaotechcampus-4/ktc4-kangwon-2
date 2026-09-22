export type ErrorCode =
  "VALIDATION_FAILED" | "NOT_FOUND" | "GATE_BLOCKED" | "NO_ACTIVITIES" | "GENERATION_FAILED";
/** fields 는 항상 배열이다 — 하나여도 ["name"] 이다 (docs/api-spec.md 「공통」). */
export interface ErrorResponse {
  error: { code: ErrorCode; message: string; fields: string[] };
}
/** 지역은 두 값으로 받는다. centers.region_sido · region_sigungu 각각 String(30) (§1). */
export interface CenterInput {
  name: string;
  director_name: string;
  region_sido: string;
  region_sigungu: string;
}
export interface Center extends CenterInput {
  id: number;
  created_at: string;
}
/**
 * 반 연령은 age_min·age_max 두 값이다 (docs/api-spec.md §2).
 * classes 는 범위 컬럼이고 `CHECK (age_min <= age_max)` 가 걸려 있어 「4세만 제외」를 저장할 수 없다.
 * 체크박스 선택값은 화면 상태로만 남고, 요청 직전에 lib/api/age-adapter 가 범위로 바꾼다.
 */
export interface ClassInput {
  name: string;
  age_min: number;
  age_max: number;
  child_count?: number | null;
  teacher_name: string;
  /** 법정대리인 동의 확인 체크박스. true 면 서버가 consent_confirmed_at 에 시각을 넣는다. */
  consent_confirmed?: boolean;
}
/** `POST · GET /api/centers/{id}/classes` 응답. school_year 와 동의 시각은 서버가 채운다. */
export interface ApiClass {
  id: number;
  center_id: number;
  name: string;
  school_year: number;
  age_min: number;
  age_max: number;
  child_count: number | null;
  teacher_name: string;
  consent_confirmed_at: string | null;
  created_at: string;
}
export interface ChildInput {
  name: string;
}
export interface ApiChild extends ChildInput {
  id: number;
  class_id: number;
  code: string;
  created_at: string;
}
export interface PlanConfig {
  uses_monthly: boolean;
  weekly_location: "SEPARATE_WEEKLY" | "DAILY_LOG_PLAN_CELL" | "WEEKLY_LOG_PLAN_CELL";
  safety_edu_hours: number;
}
// TODO(BE): PUT plan-config 응답 body/status 미확정. 호출자는 응답 필드에 의존하지 않는다.
export type PlanConfigResponse = unknown;
export interface AnnualInput {
  class_id: number;
  school_year: number;
  source: "FROM_SCRATCH" | "FROM_UPLOAD";
  upload_id: number | null;
}
export interface MonthInput {
  theme: string;
  sub_themes: string[];
}
export interface AnnualMonth extends MonthInput {
  month: number;
  source_type: "TEMPLATE" | "TREND" | "AI" | "TEACHER";
  citation: { label: string; url: string | null };
}
export interface AnnualPlan {
  id: number;
  class_id: number;
  school_year: number;
  status: "DRAFT" | "CONFIRMED";
  months: AnnualMonth[];
}
export interface ConfirmResult {
  id: number;
  status: "CONFIRMED";
  confirmed_at: string;
}
