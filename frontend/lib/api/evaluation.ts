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
}

export interface SelfCheckIndicator extends Indicator {
  kind: "SELF_CHECK";
  elements: { element: string; text: string; checked: boolean; checked_at: string | null }[];
  progress: { checked: number; total: number };
  complete: boolean;
}

export interface EvaluationChecklist {
  school_year: number;
  items: (AutoIndicator | SelfCheckIndicator)[];
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
