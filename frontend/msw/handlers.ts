import { http, HttpResponse } from "msw";
import { failure, scenario } from "./scenarios";
import { findCenter, addCenter, putConfig } from "./data/centers";
import { findClass, listClasses, addClass } from "./data/classes";
import { hasChild, listChildren, addChild, removeChild } from "./data/children";
import { findPlan, addPlan, patchMonth, confirmPlan } from "./data/annual-plans";
import type {
  CenterInput,
  ClassInput,
  PlanConfig,
  AnnualInput,
  MonthInput,
} from "../lib/api/types";
const text = (v: unknown): v is string => typeof v === "string" && !!v.trim();
const integer = (v: unknown): v is number => Number.isInteger(v);
const bad = (field: string) => failure("VALIDATION_FAILED", "입력값을 확인해주세요.", field);
const missing = () => failure("NOT_FOUND", "대상을 찾을 수 없습니다.");
async function body(request: Request): Promise<Record<string, unknown> | null> {
  try {
    const b = await request.json();
    return b && typeof b === "object" && !Array.isArray(b) ? b : null;
  } catch {
    return null;
  }
}
/** 목업 토큰. 서명이 없어도 된다 — 목업은 검증하지 않는다. */
const mockAuth = (email: string, name: string) => ({
  token: `mock.${encodeURIComponent(email)}`,
  user: { id: 1, email, name, center_id: null },
});

export const handlers = [
  // MSW interception 판정 전용 probe — 실제 백엔드 API가 아니다.
  // 이 응답이 오면 fetch가 정말 MSW handler를 통과했다는 뜻이다.
  http.get("*/api/__msw_health", () => HttpResponse.json({ msw: true })),
  // 인증 (docs/api-spec.md §0). **목업은 토큰을 검증하지 않는다** —
  // 진짜 검증은 서버가 하고, 여기서는 화면이 토큰을 받고 저장하는 흐름만 흉내낸다.
  http.post("*/api/auth/signup", async ({ request }) => {
    const b = await body(request);
    if (!b) return bad("body");
    for (const k of ["email", "name", "password"]) if (!text(b[k])) return bad(k);
    if (String(b.password).length < 8) return bad("password");
    return HttpResponse.json(mockAuth(String(b.email), String(b.name)), { status: 201 });
  }),
  http.post("*/api/auth/login", async ({ request }) => {
    const b = await body(request);
    if (!b) return bad("body");
    for (const k of ["email", "password"]) if (!text(b[k])) return bad(k);
    return HttpResponse.json(mockAuth(String(b.email), "교사"));
  }),
  http.post("*/api/centers", async ({ request }) => {
    console.info("[MSW] intercepted POST /api/centers");
    const s = await scenario(request, "center");
    if (s) return s;
    const b = await body(request);
    if (!b) return bad("body");
    for (const k of ["name", "director_name", "region_sido", "region_sigungu"])
      if (!text(b[k])) return bad(k);
    return HttpResponse.json(addCenter(b as unknown as CenterInput), { status: 201 });
  }),
  http.post("*/api/centers/:centerId/classes", async ({ request, params }) => {
    const s = await scenario(request, "class-create");
    if (s) return s;
    const id = Number(params.centerId);
    if (!findCenter(id)) return missing();
    const b = await body(request);
    if (!b) return bad("body");
    for (const k of ["name", "teacher_name"]) if (!text(b[k])) return bad(k);
    // 연령은 범위 두 값이다 (docs/api-spec.md §2). 배열은 받지 않는다.
    for (const k of ["age_min", "age_max"])
      if (!integer(b[k]) || Number(b[k]) < 3 || Number(b[k]) > 5) return bad(k);
    if (Number(b.age_min) > Number(b.age_max)) return bad("age_min");
    if (b.child_count != null && (!integer(b.child_count) || Number(b.child_count) < 1))
      return bad("child_count");
    return HttpResponse.json(addClass(id, b as unknown as ClassInput), { status: 201 });
  }),
  http.get("*/api/centers/:centerId/classes", async ({ request, params }) => {
    const s = await scenario(request, "classes");
    if (s) return s;
    const id = Number(params.centerId);
    return findCenter(id) ? HttpResponse.json({ items: listClasses(id) }) : missing();
  }),
  http.get("*/api/classes/:classId/children", async ({ request, params }) => {
    const s = await scenario(request, "children");
    if (s) return s;
    const id = Number(params.classId);
    if (!findClass(id)) return missing();
    // 목록 봉투는 { items } 하나다 — count 를 따로 주지 않는다 (§2-1).
    return HttpResponse.json({ items: listChildren(id) });
  }),
  http.post("*/api/classes/:classId/children", async ({ request, params }) => {
    const s = await scenario(request, "child-create");
    if (s) return s;
    const id = Number(params.classId);
    if (!findClass(id)) return missing();
    const b = await body(request);
    if (!b || !text(b.name) || Object.keys(b).some((k) => k !== "name")) return bad("name");
    return HttpResponse.json(addChild(id, b.name.trim()), { status: 201 });
  }),
  http.delete("*/api/children/:id", async ({ request, params }) => {
    const s = await scenario(request, "child-delete");
    if (s) return s;
    const id = Number(params.id);
    if (!hasChild(id)) return missing();
    removeChild(id);
    return new HttpResponse(null, { status: 204 });
  }),
  http.put("*/api/centers/:centerId/plan-config", async ({ request, params }) => {
    const s = await scenario(request, "plan-config");
    if (s) return s;
    const id = Number(params.centerId);
    if (!findCenter(id)) return missing();
    const b = await body(request);
    if (!b) return bad("body");
    if (typeof b.uses_monthly !== "boolean") return bad("uses_monthly");
    if (
      !["SEPARATE_WEEKLY", "DAILY_LOG_PLAN_CELL", "WEEKLY_LOG_PLAN_CELL"].includes(
        String(b.weekly_location),
      )
    )
      return bad("weekly_location");
    if (
      typeof b.safety_edu_hours !== "number" ||
      !Number.isFinite(b.safety_edu_hours) ||
      b.safety_edu_hours < 0
    )
      return bad("safety_edu_hours");
    putConfig(id, b as unknown as PlanConfig);
    // TODO(BE): 응답 미확정. mock은 임시 204, FE는 body에 의존하지 않음.
    return new HttpResponse(null, { status: 204 });
  }),
  http.post("*/api/plans/annual", async ({ request }) => {
    const s = await scenario(request, "annual", 1200);
    if (s) return s;
    const b = await body(request);
    if (!b) return bad("body");
    if (!integer(b.class_id)) return bad("class_id");
    if (!findClass(Number(b.class_id))) return missing();
    if (!integer(b.school_year)) return bad("school_year");
    if (!["FROM_SCRATCH", "FROM_UPLOAD"].includes(String(b.source))) return bad("source");
    if (b.source === "FROM_UPLOAD" && (!integer(b.upload_id) || Number(b.upload_id) <= 0))
      return bad("upload_id");
    if (b.source === "FROM_SCRATCH" && b.upload_id !== null) return bad("upload_id");
    if (request.signal.aborted) return HttpResponse.error();
    return HttpResponse.json(addPlan(b as unknown as AnnualInput), { status: 201 });
  }),
  http.get("*/api/plans/annual/:id", async ({ request, params }) => {
    const s = await scenario(request, "annual-get");
    if (s) return s;
    const plan = findPlan(Number(params.id));
    return plan ? HttpResponse.json(plan) : missing();
  }),
  http.patch("*/api/plans/annual/:id/months/:month", async ({ request, params }) => {
    const s = await scenario(request, "month");
    if (s) return s;
    const id = Number(params.id),
      month = Number(params.month),
      plan = findPlan(id);
    if (!plan || !plan.months.some((m) => m.month === month)) return missing();
    if (plan.status === "CONFIRMED")
      return failure("GATE_BLOCKED", "확정된 계획안은 수정할 수 없습니다.");
    const b = await body(request);
    if (!b) return bad("body");
    if (typeof b.theme !== "string") return bad("theme");
    if (!Array.isArray(b.sub_themes) || !b.sub_themes.every((v) => typeof v === "string"))
      return bad("sub_themes");
    return HttpResponse.json(patchMonth(id, month, b as unknown as MonthInput));
  }),
  http.post("*/api/plans/annual/:id/confirm", async ({ request, params }) => {
    const s = await scenario(request, "confirm");
    if (s) return s;
    const id = Number(params.id),
      plan = findPlan(id);
    if (!plan) return missing();
    const invalid = plan.months.find(
      (m) => !m.theme.trim() || !m.sub_themes.length || m.sub_themes.some((t) => !t.trim()),
    );
    if (invalid)
      return failure("VALIDATION_FAILED", "빈 칸을 확인해주세요.", "months." + invalid.month);
    return HttpResponse.json(confirmPlan(id));
  }),
];
