/**
 * docs/api-spec.md 「공통」의 에러 표 전체. 표에 코드를 더하면 여기도 더한다.
 * 빠뜨리면 msw/scenarios.ts 의 `Record<ErrorCode, number>` 에서 타입 검사가 잡는다.
 */
export type ErrorCode =
  | "UNAUTHENTICATED"
  | "VALIDATION_FAILED"
  | "NOT_FOUND"
  | "GATE_BLOCKED"
  | "ALREADY_EXISTS"
  | "ALREADY_CONFIRMED"
  | "STALE_WRITE"
  | "UNSUPPORTED_FILE_TYPE"
  | "NO_ACTIVITIES"
  | "LLM_BUDGET_EXCEEDED"
  | "DEPENDENCY_UNAVAILABLE"
  | "GENERATION_FAILED";
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
/** `school_year` 를 받지 않는다 — `class_id` 가 학년도를 정한다 (§4). */
export interface AnnualInput {
  class_id: number;
  /** 원이 등록한 기관 양식 (§8). `null` 이면 기본 양식으로 만든다. */
  form_id: number | null;
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
/** 목록용. months 12개는 담지 않는다 — 상세는 단건 조회가 준다(§5). */
export interface AnnualPlanSummary {
  id: number;
  class_id: number;
  school_year: number;
  status: "DRAFT" | "CONFIRMED";
  created_at: string;
  confirmed_at: string | null;
}
export interface ConfirmResult {
  id: number;
  status: "CONFIRMED";
  confirmed_at: string;
}
/** 관찰 기록 (docs/api-spec.md §10). 서버 모양 그대로 — snake_case 와 정수 id 를 유지한다. */
export interface ObservationUpdate {
  /** `YYYY-MM-DD`. */
  date: string;
  /** 5영역 중 하나. */
  domain: string;
  /** 선택 — 빈 문자열을 허용한다. */
  context: string;
  fact: string;
}
/** `PUT` 은 위 네 칸만 받는다 (§10). */
export interface ObservationInput extends ObservationUpdate {
  class_id: number;
  child_id: number;
}
export interface ApiObservation extends ObservationInput {
  id: number;
  class_name: string;
  /** 아동 실명. */
  child_name: string;
  /** 실명 대신 LLM 에 나가는 대체 코드 (ADR-004). */
  child_code: string;
  created_at: string;
}
/** 양식 표의 칸 하나 (docs/api-spec.md §8). 병합은 rowspan · colspan 으로 온다. */
export interface FormCell {
  text: string;
  rowspan: number;
  colspan: number;
}
/** 원에 등록된 양식. 저장하는 것은 파싱 결과뿐이다 — 원본 파일은 없다(ADR-020). */
export interface ApiForm {
  id: number;
  center_id: number;
  /** 지금은 `filename` 과 같다. */
  name: string;
  filename: string;
  /** 표 → 행 → 칸. */
  tables: FormCell[][][];
  labels: string[];
  /** 라벨 → 표준 키(ADR-009). 데이터 값이거나 매핑표에 없는 표현이면 `null`. */
  label_map: Record<string, string | null>;
  created_at: string;
}
