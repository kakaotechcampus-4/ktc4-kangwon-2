import { apiRequest } from "./client";
import type { AnnualPlan } from "./types";
import { MONTH_ORDER } from "../onboarding/types";

/**
 * 연간 가져오기 (계약 I-A · I-B, 2026-11-01). 월별 주제형만 있다.
 *
 * 추출은 저장하지 않는다. 교사가 12개월 표를 확인하고 [저장]을 눌러야 계획안이 생긴다.
 */
export type ImportFileMeta = { format: "HWP" | "HWPX" | "DOCX" | "PDF"; sha256: string };
export type ImportMonth = { month: number; theme: string; sub_themes: string[] };
export interface ExtractResult {
  file: ImportFileMeta;
  /** 못 찾은 달은 `theme` 이 null 이고 `missing` 이 true 다. */
  months: { month: number; theme: string | null; sub_themes: string[]; missing: boolean }[];
  notices: string[];
}
export interface AnnualImportInput {
  class_id: number;
  /** 교사가 표에 바로 입력했으면 MANUAL, 파일에서 뽑은 것을 확인했으면 FILE. */
  source: "MANUAL" | "FILE";
  file: ImportFileMeta | null;
  months: ImportMonth[];
}

/** 원본 파일은 서버도 저장하지 않는다. 그 밖의 형식은 400 `UNSUPPORTED_FILE_TYPE` 이고 문구를 그대로 띄운다. */
export function extractAnnualFile(classId: number, file: File, signal?: AbortSignal) {
  const body = new FormData();
  body.append("file", file);
  body.append("class_id", String(classId));
  return apiRequest<ExtractResult>("/api/plans/annual/import/extract", {
    method: "POST",
    body,
    signal,
  });
}

/** 201 이면 DRAFT 연간이다. 반에 연간이 이미 있으면 409 `ALREADY_EXISTS`. */
export const importAnnualPlan = (data: AnnualImportInput) =>
  apiRequest<AnnualPlan>("/api/plans/annual/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

/** 확인 표 한 줄. 소주제는 한 줄에 하나씩 적는다. */
export type ImportRow = { month: number; theme: string; subThemes: string; missing: boolean };

export const emptyImportRows = (): ImportRow[] =>
  MONTH_ORDER.map((month) => ({ month, theme: "", subThemes: "", missing: false }));

/** 서버가 준 순서를 믿지 않고 3월 → 2월로 다시 세운다. 빠진 달도 「못 찾음」으로 둔다. */
export const rowsFromExtract = (months: ExtractResult["months"]): ImportRow[] =>
  MONTH_ORDER.map((month) => {
    const found = months.find((m) => m.month === month);
    return {
      month,
      theme: found?.theme ?? "",
      subThemes: (found?.sub_themes ?? []).join("\n"),
      missing: !found || found.missing || !found.theme,
    };
  });

/** 생활주제가 빈 달. 하나라도 있으면 저장하지 않는다(서버도 422). */
export const blankThemeMonths = (rows: ImportRow[]) =>
  rows.filter((row) => !row.theme.trim()).map((row) => row.month);

/** 저장 본문의 `months`. 소주제는 앞뒤 공백을 털고 빈 줄을 뺀다. */
export const importMonths = (rows: ImportRow[]): ImportMonth[] =>
  rows.map((row) => ({
    month: row.month,
    theme: row.theme.trim(),
    sub_themes: row.subThemes
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean),
  }));
