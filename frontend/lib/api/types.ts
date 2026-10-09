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
/** 생성에 쓰는 정확한 양식 설정 버전 (docs/api-spec.md §9-1 · §9-2). 「latest」 같은 별칭은 없다. */
export interface ProfileRef {
  profile_id: string;
  profile_version: string;
}
export interface TemplateRef {
  template_id: string;
  template_version: string;
}
/** `school_year` · 부모 연간계획안은 보내지 않는다 — 서버가 반으로 찾는다 (§9-1). */
export interface MonthlyInput {
  class_id: number;
  /** 달력의 달 1~12. 1~2월은 학년도의 다음 해다. */
  month: number;
  profile_ref: ProfileRef;
}
/**
 * 칸 하나 (§9-1). 출처는 세 축이다 — `evidence` 는 근거, `generation` 은 만든 방법.
 * 변경 이력(audit)은 응답에 없다.
 */
export interface MonthlyCell {
  /** 칸의 주소. 편집 · 재생성 뒤에도 바뀌지 않는다. */
  item_id: string;
  /** `repeat_by: "NONE"` 이면 null. */
  week_id: string | null;
  value: string;
  state: "FILLED" | "EMPTY_VALID" | "EMPTY_UNRESOLVED";
  evidence: {
    source_type: string;
    source_id: string;
    source_version: string | null;
    effective_date: string | null;
    display_name: string | null;
  }[];
  generation: { method: string; rule_id: string | null; rule_version: string | null };
}
/** 주 · Section · 칸 개수를 정하지 않는다 — 화면은 받은 만큼 그린다. */
export interface MonthlyPlan {
  id: number;
  class_id: number;
  school_year: number;
  month: number;
  /** `YYYY-MM`. */
  target_month: string;
  status: "DRAFT" | "CONFIRMED";
  /** 편집 · 재생성 · 확정에 `expected_revision` 으로 그대로 보낸다 (§9-3). */
  revision: number;
  generation_mode: "RULE_ONLY" | "LLM_PLANNER";
  profile_ref: ProfileRef;
  base_template_ref: TemplateRef;
  parent: { annual_plan_id: number; theme: string | null; confirmed_at: string };
  weeks: {
    week_id: string;
    label: string;
    start_date: string;
    end_date: string;
    active: boolean;
  }[];
  sections: {
    section_key: string;
    label: string | null;
    role: "CONTENT" | "AXIS";
    repeat_by: "NONE" | "WEEK" | null;
    visible: boolean;
    order: number;
    semantic_variant: "SUBTHEME" | "EXPECTED_PLAY" | "WEEKLY_THEME" | "NEUTRAL" | null;
    cells: MonthlyCell[];
  }[];
  constraints: {
    code: string;
    verification: string;
    affected_section_keys: string[];
    required_source_kinds: string[];
    rule_version: string;
    detail: string;
  }[];
  verification: {
    executed_rules: { rule_id: string; rule_version: string }[];
    findings: {
      code: string;
      kind: "VIOLATION" | "NOT_VERIFIED";
      severity: string;
      section_key: string | null;
      week_id: string | null;
      message: string;
    }[];
  };
  created_at: string;
  confirmed_at: string | null;
}
/** 목록용. 칸은 단건 조회가 준다. */
export type MonthlyPlanSummary = Pick<
  MonthlyPlan,
  | "id"
  | "class_id"
  | "school_year"
  | "month"
  | "target_month"
  | "status"
  | "revision"
  | "profile_ref"
  | "created_at"
  | "confirmed_at"
>;
/** 반에 적용되는 양식 설정 (§9-2). 반 override → 원 기본 → 「선택 필요」. */
export interface ProfileResolution {
  source: "CLASSROOM_OVERRIDE" | "INSTITUTION_DEFAULT" | "SELECTION_REQUIRED";
  /** `SELECTION_REQUIRED` 면 null. */
  profile_ref: ProfileRef | null;
  /** `SELECTION_REQUIRED` 일 때만 값 (`NO_POINTER` · `CLASSROOM_OVERRIDE_NOT_READY` …). */
  reason: string | null;
}
/** 원의 READY 양식 설정. 이름 칸은 없다 — 버전 · 기반 Template · Section 으로 구분한다. */
export interface ReadyProfile {
  profile_ref: ProfileRef;
  status: "READY";
  base_template_ref: TemplateRef;
  selected_optional_keys: string[];
  sections: {
    section_key: string;
    label: string | null;
    repeat_by: "NONE" | "WEEK" | null;
    visible: boolean;
  }[];
  created_at: string;
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
