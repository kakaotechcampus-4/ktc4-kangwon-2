import { apiRequest } from "./client";

interface Indicator {
  indicator: string;
  area: string;
  title: string;
  content: string;
}

export interface AutoIndicator extends Indicator {
  kind: "AUTO";
  verdict: "SUPPORTED" | "INSUFFICIENT" | "NONE";
  required: number | null;
  count: number;
  children: { met: number; total: number } | null;
  classes: { met: number; total: number } | null;
  plan_ids: number[];
  document_ids: number[];
  period: { from: string; to: string };
  /** 4-1 만 — 보육일지 · 계획안 조건을 따로 채운 반 수(ADR-074 결정 2). 4-2 는 null */
  journal_classes: { met: number; total: number } | null;
  plan_classes: { met: number; total: number } | null;
}

export interface SelfCheckIndicator extends Indicator {
  kind: "SELF_CHECK";
  elements: { element: string; text: string; checked: boolean; checked_at: string | null }[];
  progress: { checked: number; total: number };
  complete: boolean;
}

/** 폴더 검사 결과 요약. 파일 이름 · 빈 날짜는 서버에 없다(ADR-074 결정 5). */
export interface FolderSummary {
  status: "found" | "partial" | "missing";
  /** 이름으로 센 파일 수 */
  files: number;
  /** 빈 평일 · 빈 달 수. 「일부 빠짐」일 때만 0 보다 크다 */
  gaps: number;
}

/** 로그인한 교사의 서류 한 줄(api-spec §12 「평가 서류 도장 근거」) */
export interface DocumentMark {
  doc: string;
  checked: boolean;
  checked_at: string | null;
  folder: (FolderSummary & { scanned_at: string; period: { from: string; to: string } }) | null;
}

/** 원장 서류 체크 — 원 단위 */
export interface DirectorCheck {
  item: string;
  checked: boolean;
  checked_at: string | null;
}

export interface EvaluationChecklist {
  school_year: number;
  items: (AutoIndicator | SelfCheckIndicator)[];
  /** 늘 서류 6줄 · 원장 서류 5줄이다 */
  documents: DocumentMark[];
  director: DirectorCheck[];
}

const path = (centerId: number) => `/api/centers/${centerId}/evaluation-checklist`;

export const getEvaluationChecklist = (centerId: number, signal?: AbortSignal) =>
  apiRequest<EvaluationChecklist>(path(centerId), { signal });

/** Only changed elements are sent. The complete response replaces the displayed checklist. */
export const saveEvaluationChecks = (
  centerId: number,
  checks: { element: string; checked: boolean }[],
) =>
  apiRequest<EvaluationChecklist>(path(centerId) + "/checks", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ checks }),
  });

const put = (url: string, body: unknown) =>
  apiRequest<EvaluationChecklist>(url, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

/** 직접확인 · 새 폴더 검사 결과. 폴더 검사는 이 교사의 폴더 결과를 통째로 바꾼다. 파일 이름은 보내지 않는다. */
export const saveEvaluationDocuments = (
  centerId: number,
  body: {
    checks?: { doc: string; checked: boolean }[];
    folder_scan?: {
      results: (FolderSummary & { doc: string; period: { from: string; to: string } })[];
    };
  },
) => put(path(centerId) + "/documents", body);

/** 원장 서류 체크. 같은 원 선생님이 같이 본다. */
export const saveDirectorChecks = (
  centerId: number,
  checks: { item: string; checked: boolean }[],
) => put(path(centerId) + "/director", { checks });
