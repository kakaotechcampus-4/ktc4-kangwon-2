import { http, HttpResponse } from "msw";
import { failure, scenario } from "./scenarios";
import { findClass } from "./data/classes";
import { addPlan, findPlan } from "./data/annual-plans";
import { annualFor } from "./data/monthly-plans";
import { commit } from "./data/store";
import type { AnnualInput } from "../lib/api/types";

/**
 * 연간 가져오기 목업 (계약 I-A · I-B). 화면 작업용이라 파일 글자는 읽지 않고 확장자만 본다.
 * 추출 결과는 고정값이고, 한 달(2월)은 일부러 「못 찾음」으로 둔다.
 */
const MONTHS = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2];
const THEMES = [
  "새 친구와 우리 반",
  "봄과 동식물",
  "나와 가족",
  "우리 동네",
  "건강과 안전",
  "여름과 물놀이",
  "교통기관",
  "가을과 열매",
  "환경과 생활",
  "겨울과 놀이",
  "세계 여러 나라",
];
const FORMATS = { hwpx: "HWPX", docx: "DOCX", pdf: "PDF" } as const;
const bad = (field: string) => failure("VALIDATION_FAILED", "입력값을 확인해주세요.", field);

export const annualImportHandlers = [
  http.post("*/api/plans/annual/import/extract", async ({ request }) => {
    const s = await scenario(request, "annual-import-extract", 1200);
    if (s) return s;
    const form = await request.formData().catch(() => null);
    const file = form?.get("file");
    if (!(file instanceof File) || file.size === 0) return bad("file");
    const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
    const format = FORMATS[ext as keyof typeof FORMATS];
    if (!format)
      return failure("UNSUPPORTED_FILE_TYPE", "한글에서 HWPX나 PDF로 저장해서 올려 주세요", "file");
    if (!findClass(Number(form?.get("class_id"))))
      return failure("NOT_FOUND", "반을 찾을 수 없습니다.", "class_id");
    const hash = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
    const sha256 = [...new Uint8Array(hash)].map((b) => b.toString(16).padStart(2, "0")).join("");
    return HttpResponse.json({
      file: { format, sha256 },
      months: MONTHS.map((month, i) =>
        THEMES[i]
          ? {
              month,
              theme: THEMES[i],
              sub_themes: [`${THEMES[i]} 알아보기`, `${THEMES[i]} 놀이`],
              missing: false,
            }
          : { month, theme: null, sub_themes: [], missing: true },
      ),
      notices: ["2월 생활주제를 찾지 못했어요"],
    });
  }),
  http.post("*/api/plans/annual/import", async ({ request }) => {
    const s = await scenario(request, "annual-import", 600);
    if (s) return s;
    const b = (await request.json().catch(() => null)) as Record<string, unknown> | null;
    if (!b || typeof b !== "object") return bad("body");
    if (!Number.isInteger(b.class_id)) return bad("class_id");
    if (b.source !== "MANUAL" && b.source !== "FILE") return bad("source");
    // 서버 검증: 12개월 · 3월 → 2월 순서 · 생활주제 non-blank.
    const months = b.months as { month: number; theme: string; sub_themes: string[] }[];
    if (
      !Array.isArray(months) ||
      months.length !== 12 ||
      months.some(
        (m, i) => m?.month !== MONTHS[i] || typeof m.theme !== "string" || !m.theme.trim(),
      )
    )
      return bad("months");
    const klass = findClass(Number(b.class_id));
    if (!klass) return failure("NOT_FOUND", "반을 찾을 수 없습니다.", "class_id");
    if (annualFor(klass.id))
      return failure("ALREADY_EXISTS", "이 반의 연간계획안이 이미 있습니다.", "class_id");
    // 생성 목업으로 한 건 만들고 달마다 교사 글로 덮는다. THEME_REFERENCE 근거는 없다.
    const plan = addPlan(
      { class_id: klass.id, format: "MONTHLY_THEME" } as AnnualInput,
      klass.school_year,
    );
    const method = b.source === "FILE" ? "IMPORTED" : "MANUAL";
    commit((db) => {
      const saved = db.plans.find((p) => p.id === plan.id);
      if (saved?.format !== "MONTHLY_THEME") return;
      saved.months = saved.months.map((m, i) => ({
        ...m,
        theme: months[i].theme.trim(),
        sub_themes: months[i].sub_themes.map((v) => v.trim()).filter(Boolean),
        evidence: [],
        generation: { method, rule_id: null, rule_version: null },
      }));
    });
    return HttpResponse.json(findPlan(plan.id), { status: 201 });
  }),
];
