export type ErrorCode =
  "VALIDATION_FAILED" | "NOT_FOUND" | "GATE_BLOCKED" | "NO_ACTIVITIES" | "GENERATION_FAILED";
export interface ErrorResponse {
  error: { code: ErrorCode; message: string; field?: string };
}
export interface CenterInput {
  name: string;
  director_name: string;
  region: string;
}
export interface Center extends CenterInput {
  id: number;
  created_at: string;
}
/** 반 연령은 실제 선택값 배열이다. [3,5]는 만 3세와 만 5세만 포함한다(4세 제외). 범위(min/max)로 바꾸지 않는다. */
export interface ClassInput {
  name: string;
  selected_ages: number[];
  child_count?: number | null;
  teacher_name: string;
}
// TODO(BE): 반 Response 전체 스키마 미확정. 현재 mock에서만 id/center_id와 요청 필드를 반환한다.
export interface ApiClass extends ClassInput {
  id: number;
  center_id: number;
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
