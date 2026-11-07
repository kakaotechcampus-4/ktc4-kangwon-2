/**
 * 서버 검사 결과(`verification.findings[]`)를 교사 문장으로 — 월간 v1 · 주간이 같이 쓴다.
 * 서버 `message` 는 영어라 화면에 그대로 띄우지 않는다. `null` 은 띄우지 않는 코드다.
 */
const TEXT: Record<string, string | null> = {
  ACTIVITY_REFERENCE_NOT_VERIFIED:
    "수정한 내용과 기존 참고 활동의 연결을 자동으로 확인하지 못했어요. 교사가 내용을 확인해주세요.",
  // 직접 쓴 바깥놀이의 연령 안내는 띄우지 않는다(2026-11-05 피드백 — 모든 계획안 화면 공통).
  ACTIVITY_FREE_TEXT_AGE_NOT_VERIFIED: null,
  ACTIVITY_AGE_UNSUPPORTED:
    "우리 반 연령을 모두 지원하지 않는 참고 활동이 있어요. 활동 내용과 대상 연령을 확인해주세요.",
  SAFETY_ANNUAL_HOURS_NOT_VERIFIED:
    "계획안에는 교육 시간이 없어 안전교육 연간 법정 시간은 자동으로 확인하지 못했어요. 실제 교육 시간은 따로 확인해주세요.",
  SAFETY_OFFICIAL_GROUNDING_MISSING:
    "법정 안전교육 칸의 공식 교육 내용 근거를 확인하지 못했어요. 안전교육 내용을 확인해주세요.",
  SAFETY_SUPPLEMENTAL_GROUNDING_INVALID:
    "생활안전 칸의 참고 근거를 확인하지 못했어요. 안전교육 내용을 확인해주세요.",
  // 주간 — AI 가 쓴 칸마다 오는 사실 범위 안내는 띄우지 않는다(PM 2026-11-06).
  WEEKLY_FACT_SCOPE_NOT_VERIFIED: null,
  WEEKLY_SAFETY_PARENT_CITATION_INVALID:
    "안전교육 칸이 월간계획안의 안전교육과 이어지는지 확인하지 못했어요. 안전교육 내용을 확인해주세요.",
};
const OTHER = "자동으로 확인하지 못한 내용이 있어요. 교사가 내용을 확인해주세요.";

/** 띄울 문장 — 같은 문장은 한 번. 모르는 코드도 영어 대신 한 줄 안내로. */
export const findingLines = (findings: { code: string }[]) => [
  ...new Set(
    findings.map((f) => (f.code in TEXT ? TEXT[f.code] : OTHER)).filter((t): t is string => !!t),
  ),
];
