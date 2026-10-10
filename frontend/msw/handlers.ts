import { http, HttpResponse } from "msw";
import { failure, scenario } from "./scenarios";
import {
  findCenter,
  addCenter,
  putConfig,
  currentCenterId,
  findGreetings,
  putGreetings,
} from "./data/centers";
import type { Greetings } from "../lib/api/centers";
import { findClass, listClasses, addClass } from "./data/classes";
import { hasChild, listChildren, addChild, removeChild } from "./data/children";
import { findPlan, listPlans, addPlan, putMonth, confirmPlan } from "./data/annual-plans";
import {
  REGENERATABLE,
  addMonthly,
  annualFor,
  confirmMonthly,
  editCell,
  findCell,
  findMonthly,
  findMonthlyFor,
  listAudit,
  listMonthly,
  regenerateCell,
  targetMonthOf,
} from "./data/monthly-plans";
import {
  addReadyProfile,
  defaultPointer,
  findReady,
  findTemplate,
  listReady,
  listTemplates,
  movePointer,
  overridePointer,
  resolveProfile,
  startProblem,
} from "./data/template-profiles";
import type {
  CenterInput,
  ClassInput,
  PlanConfig,
  AnnualInput,
  MonthInput,
  ProfileRef,
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
  http.get("*/api/auth/me", ({ request }) => {
    const token = request.headers.get("Authorization")?.replace(/^Bearer /, "");
    if (!token?.startsWith("mock.")) return failure("UNAUTHENTICATED", "다시 로그인해주세요.");
    const user = mockAuth(decodeURIComponent(token.slice(5)), "교사").user;
    return HttpResponse.json({ ...user, center_id: currentCenterId() });
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
  http.get("*/api/centers/:centerId/greetings", async ({ request, params }) => {
    const s = await scenario(request, "greetings");
    if (s) return s;
    const id = Number(params.centerId);
    if (!findCenter(id) || id !== currentCenterId()) return missing();
    return HttpResponse.json(findGreetings(id));
  }),
  http.put("*/api/centers/:centerId/greetings", async ({ request, params }) => {
    const s = await scenario(request, "greetings-save");
    if (s) return s;
    const id = Number(params.centerId);
    if (!findCenter(id) || id !== currentCenterId()) return missing();
    const b = await body(request);
    if (!b) return bad("body");
    if (Object.keys(b).some((key) => key !== "enabled" && key !== "items")) return bad("body");
    if (typeof b.enabled !== "boolean") return bad("enabled");
    if (!Array.isArray(b.items) || b.items.length !== 12) return bad("items");
    const months = new Set<number>();
    for (const item of b.items) {
      if (
        !item ||
        typeof item !== "object" ||
        Object.keys(item).some((key) => key !== "month" && key !== "text") ||
        !integer(item.month) ||
        item.month < 1 ||
        item.month > 12 ||
        months.has(item.month) ||
        typeof item.text !== "string"
      )
        return bad("items");
      months.add(item.month);
    }
    return HttpResponse.json(putGreetings(id, b as unknown as Greetings));
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
    if (b.form_id != null && !integer(b.form_id)) return bad("form_id");
    // 연간 목업은 「지금 원」 소유 검사를 하지 않는다(서버는 남의 원 반이면 404) — 화면 목업 흐름 유지.
    const klass = findClass(Number(b.class_id));
    if (!klass) return classMissing();
    // 서버처럼 반 하나에 연간 하나다.
    if (annualFor(klass.id))
      return failure("ALREADY_EXISTS", "이 반의 연간계획안이 이미 있습니다.", "class_id");
    if (request.signal.aborted) return HttpResponse.error();
    return HttpResponse.json(addPlan(b as unknown as AnnualInput, klass.school_year), {
      status: 201,
    });
  }),
  http.get("*/api/plans/annual", async ({ request }) => {
    const s = await scenario(request, "annual-list");
    if (s) return s;
    const raw = new URL(request.url).searchParams.get("class_id");
    if (raw === null) return HttpResponse.json({ items: listPlans() });
    if (!/^-?\d+$/.test(raw)) return bad("class_id");
    if (!findClass(Number(raw))) return classMissing();
    return HttpResponse.json({ items: listPlans(Number(raw)) });
  }),
  http.get("*/api/plans/annual/:id", async ({ request, params }) => {
    const s = await scenario(request, "annual-get");
    if (s) return s;
    const plan = findPlan(Number(params.id));
    return plan ? HttpResponse.json(plan) : annualMissing();
  }),
  http.put("*/api/plans/annual/:id/months/:month", async ({ request, params }) => {
    const s = await scenario(request, "month");
    if (s) return s;
    // 서버 순서: 본문 형식 422 → 계획안 404 → 달 404 → 확정 409 → 공백 주제 422 (§6).
    const b = await body(request);
    if (!b) return bad("body");
    const extra = Object.keys(b).find((k) => k !== "theme" && k !== "sub_themes");
    if (extra) return bad(extra);
    if (typeof b.theme !== "string" || !b.theme) return bad("theme");
    if (!Array.isArray(b.sub_themes) || !b.sub_themes.every((v) => typeof v === "string"))
      return bad("sub_themes");
    const id = Number(params.id),
      month = Number(params.month),
      plan = findPlan(id);
    if (!plan) return annualMissing();
    if (!plan.months.some((m) => m.month === month))
      return failure("NOT_FOUND", "그 달이 없습니다.", "month");
    if (plan.status === "CONFIRMED")
      return failure("ALREADY_CONFIRMED", "확정된 계획안은 수정할 수 없습니다.");
    // 공백만 있는 주제는 Core 가 거절한다 — 서버도 fields 를 주지 않는다.
    if (!b.theme.trim()) return failure("VALIDATION_FAILED", "입력값을 확인해주세요.");
    return HttpResponse.json(putMonth(id, month, b as unknown as MonthInput));
  }),
  http.post("*/api/plans/annual/:id/confirm", async ({ request, params }) => {
    const s = await scenario(request, "confirm");
    if (s) return s;
    const id = Number(params.id);
    if (!findPlan(id)) return annualMissing();
    // 재호출은 200 · 같은 응답 · 상태 변화 없음(§7). 서버는 빈 소주제로 확정을 막지 않는다.
    return HttpResponse.json(confirmPlan(id));
  }),
  // 월간계획안 (docs/api-spec.md §9-1 · §9-3). 소유 검사는 「지금 원」 기준 — 남의 원 것은 없는 것과 같다.
  http.post("*/api/plans/monthly", async ({ request }) => {
    const s = await scenario(request, "monthly", 1200);
    if (s) return s;
    const b = await body(request);
    if (!b) return bad("body");
    if (!integer(b.class_id)) return bad("class_id");
    if (!integer(b.month) || b.month < 1 || b.month > 12) return bad("month");
    const ref = b.profile_ref as Record<string, unknown> | null;
    if (typeof ref !== "object" || ref === null) return bad("profile_ref");
    for (const k of ["profile_id", "profile_version"])
      if (typeof ref[k] !== "string" || !ref[k]) return bad("profile_ref." + k);
    const klass = myClass(b.class_id);
    if (!klass) return classMissing();
    if (findMonthlyFor(klass.id, targetMonthOf(klass.school_year, b.month)))
      return failure(
        "ALREADY_EXISTS",
        "이 반의 그 달 월간계획안이 이미 있습니다.",
        "class_id",
        "month",
      );
    const annual = annualFor(klass.id);
    if (!annual)
      return failure("GATE_BLOCKED", "연간계획안을 먼저 만들어 확정해주세요.", "class_id");
    if (annual.status !== "CONFIRMED")
      return failure("GATE_BLOCKED", "연간계획안을 먼저 확정해주세요.", "class_id");
    const profileRef = {
      profile_id: String(ref.profile_id),
      profile_version: String(ref.profile_version),
    };
    const profile = findReady(klass.center_id, profileRef);
    if (!profile) return failure("NOT_FOUND", "고른 양식 설정을 찾을 수 없습니다.", "profile_ref");
    // 생성 직전에도 기반 Template 승인을 다시 본다(서버: 422 profile_ref).
    if (!findTemplate(profile.base_template_ref)?.approved)
      return failure(
        "VALIDATION_FAILED",
        "고른 양식 설정으로는 월간계획안을 만들 수 없습니다. 다른 설정을 골라주세요.",
        "profile_ref",
      );
    if (request.signal.aborted) return HttpResponse.error();
    return HttpResponse.json(addMonthly(klass, annual, b.month, profile), { status: 201 });
  }),
  http.get("*/api/plans/monthly", async ({ request }) => {
    const s = await scenario(request, "monthly-list");
    if (s) return s;
    const raw = new URL(request.url).searchParams.get("class_id");
    if (raw === null) {
      const center = currentCenterId();
      const ids = center === null ? [] : listClasses(center).map((c) => c.id);
      return HttpResponse.json({ items: listMonthly(ids) });
    }
    if (!/^-?\d+$/.test(raw)) return bad("class_id");
    const klass = myClass(Number(raw));
    return klass ? HttpResponse.json({ items: listMonthly([klass.id]) }) : classMissing();
  }),
  http.get("*/api/plans/monthly/:id", async ({ request, params }) => {
    const s = await scenario(request, "monthly-get");
    if (s) return s;
    const plan = myMonthly(Number(params.id));
    return plan ? HttpResponse.json(plan) : planMissing();
  }),
  // 변경 이력 (§9-5). 소유를 먼저 본다 — 남의 계획안이면 item_id 를 보기 전에 404 ["id"].
  http.get("*/api/plans/monthly/:id/audit", async ({ request, params }) => {
    const s = await scenario(request, "monthly-audit");
    if (s) return s;
    const plan = myMonthly(Number(params.id));
    if (!plan) return planMissing();
    const items = listAudit(plan, new URL(request.url).searchParams.get("item_id"));
    return items
      ? HttpResponse.json({ items })
      : failure("NOT_FOUND", "그 칸을 찾을 수 없습니다.", "item_id");
  }),
  http.put("*/api/plans/monthly/:id/cells/:itemId", async ({ request, params }) => {
    const s = await scenario(request, "monthly-cell");
    if (s) return s;
    const w = await cellWrite(request, String(params.id), String(params.itemId), true);
    if (w instanceof Response) return w;
    if (w.cell.value === w.b.value)
      return failure(
        "VALIDATION_FAILED",
        "칸의 값이 바뀌지 않았거나 쓸 수 없는 값입니다.",
        "value",
      );
    return HttpResponse.json(
      editCell(w.plan.id, w.cell.item_id, String(w.b.value), w.section.section_key),
    );
  }),
  // LLM 을 부르지 않는다 — 다음 revision 을 넣은 고정 문장으로 바꾼다.
  http.post("*/api/plans/monthly/:id/cells/:itemId/regenerate", async ({ request, params }) => {
    const s = await scenario(request, "monthly-regenerate", 1200);
    if (s) return s;
    const w = await cellWrite(request, String(params.id), String(params.itemId), false);
    if (w instanceof Response) return w;
    if (!REGENERATABLE.includes(w.section.section_key))
      return failure("VALIDATION_FAILED", "이 칸은 다시 만들 수 없습니다.", "item_id");
    if (request.signal.aborted) return HttpResponse.error();
    const label = w.section.label ?? w.section.section_key;
    return HttpResponse.json(regenerateCell(w.plan.id, w.cell.item_id, label, w.plan.revision + 1));
  }),
  http.post("*/api/plans/monthly/:id/confirm", async ({ request, params }) => {
    const s = await scenario(request, "monthly-confirm");
    if (s) return s;
    const b = await body(request);
    if (!b) return bad("body");
    if (badRevision(b)) return bad("expected_revision");
    const plan = myMonthly(Number(params.id));
    if (!plan) return planMissing();
    // 이미 확정이면 revision 과 상관없이 200 · 저장된 그대로 (D-M5-CONFIRM-01).
    if (plan.status === "CONFIRMED") return HttpResponse.json(plan);
    if (plan.revision !== b.expected_revision) return stale();
    return HttpResponse.json(confirmMonthly(plan.id));
  }),
  // 월간 양식 설정 조회 (§9-2).
  http.get("*/api/classes/:classId/template-profile", async ({ request, params }) => {
    const s = await scenario(request, "template-profile");
    if (s) return s;
    const klass = myClass(Number(params.classId));
    return klass ? HttpResponse.json(resolveProfile(klass.id, klass.center_id)) : classMissing();
  }),
  http.get("*/api/centers/:centerId/template-profiles", async ({ request, params }) => {
    const s = await scenario(request, "template-profiles");
    if (s) return s;
    const id = Number(params.centerId);
    return myCenter(id) ? HttpResponse.json({ items: listReady(id) }) : centerMissing();
  }),
  // 월간 양식 설정 관리 (§9-4). 서버처럼 입력 모양(422)을 먼저, 소유(404)를 다음에 본다.
  http.get("*/api/monthly-templates", async ({ request }) => {
    const s = await scenario(request, "monthly-templates");
    return s ?? HttpResponse.json({ items: listTemplates() });
  }),
  http.post("*/api/centers/:centerId/template-profiles", async ({ request, params }) => {
    const s = await scenario(request, "template-profile-create");
    if (s) return s;
    const b = await body(request);
    if (!b) return bad("body");
    const base = b.base_template_ref as Record<string, unknown> | null;
    if (typeof base !== "object" || base === null) return bad("base_template_ref");
    for (const k of ["template_id", "template_version"])
      if (typeof base[k] !== "string" || !base[k]) return bad("base_template_ref." + k);
    const keys = b.selected_optional_keys ?? [];
    if (!Array.isArray(keys) || !keys.every((k) => typeof k === "string"))
      return bad("selected_optional_keys");
    const labels = b.display_labels ?? {};
    if (
      typeof labels !== "object" ||
      labels === null ||
      Array.isArray(labels) ||
      !Object.values(labels).every((v) => typeof v === "string")
    )
      return bad("display_labels");
    const variant = b.focus_variant ?? null;
    if (variant !== null && typeof variant !== "string") return bad("focus_variant");
    const id = Number(params.centerId);
    if (!myCenter(id)) return centerMissing();
    const input = {
      base_template_ref: {
        template_id: String(base.template_id),
        template_version: String(base.template_version),
      },
      selected_optional_keys: keys as string[],
      display_labels: labels as Record<string, string>,
      focus_variant: variant,
    };
    const problem = startProblem(input);
    if (problem) return failure("VALIDATION_FAILED", "입력값을 확인해주세요.", ...problem);
    const template = findTemplate(input.base_template_ref);
    if (!template)
      return failure("NOT_FOUND", "기반 Template 을 찾을 수 없습니다.", "base_template_ref");
    if (!template.approved)
      return failure(
        "GATE_BLOCKED",
        "기반 Template 이 아직 사람 승인 전이라 쓸 수 없습니다.",
        "base_template_ref",
      );
    return HttpResponse.json(addReadyProfile(id, input), { status: 201 });
  }),
  http.get("*/api/centers/:centerId/template-profile-default", async ({ request, params }) => {
    const s = await scenario(request, "template-profile-default");
    if (s) return s;
    const id = Number(params.centerId);
    return myCenter(id) ? HttpResponse.json(defaultPointer(id)) : centerMissing();
  }),
  http.put("*/api/centers/:centerId/template-profile-default", async ({ request, params }) => {
    const s = await scenario(request, "template-profile-default");
    if (s) return s;
    const input = await pointerInput(request);
    if (input instanceof Response) return input;
    const id = Number(params.centerId);
    if (!myCenter(id)) return centerMissing();
    return pointerResult(movePointer("defaultPointers", id, id, input));
  }),
  http.get("*/api/classes/:classId/template-profile-override", async ({ request, params }) => {
    const s = await scenario(request, "template-profile-override");
    if (s) return s;
    const klass = myClass(Number(params.classId));
    return klass ? HttpResponse.json(overridePointer(klass.id)) : classMissing();
  }),
  http.put("*/api/classes/:classId/template-profile-override", async ({ request, params }) => {
    const s = await scenario(request, "template-profile-override");
    if (s) return s;
    const input = await pointerInput(request);
    if (input instanceof Response) return input;
    const klass = myClass(Number(params.classId));
    if (!klass) return classMissing();
    return pointerResult(movePointer("overridePointers", klass.id, klass.center_id, input));
  }),
];
/** 두 키 모두 있어야 한다(null 이라도). 값은 null 또는 빈칸 없는 profile_ref. */
async function pointerInput(request: Request) {
  const b = await body(request);
  if (!b) return bad("body");
  const refs: Record<string, ProfileRef | null> = {};
  for (const k of ["profile_ref", "expected_profile_ref"]) {
    if (!(k in b)) return bad(k);
    const v = b[k] as Record<string, unknown> | null;
    if (v !== null && (typeof v !== "object" || Array.isArray(v))) return bad(k);
    for (const sub of ["profile_id", "profile_version"])
      if (v !== null && (typeof v[sub] !== "string" || !v[sub])) return bad(k + "." + sub);
    refs[k] = v && { profile_id: String(v.profile_id), profile_version: String(v.profile_version) };
  }
  return { profile_ref: refs.profile_ref, expected_profile_ref: refs.expected_profile_ref };
}
function pointerResult(result: ReturnType<typeof movePointer>) {
  if (result === "NOT_FOUND")
    return failure("NOT_FOUND", "고른 양식 설정을 찾을 수 없습니다.", "profile_ref");
  if (result === "INVALID") return bad("expected_profile_ref");
  if (result === "STALE")
    return failure(
      "STALE_WRITE",
      "그 사이 다른 화면에서 설정이 바뀌었습니다. 새로 불러온 뒤 다시 해주세요.",
      "expected_profile_ref",
    );
  return HttpResponse.json(result);
}
/** 목업의 「내 원」은 그 계정 저장소의 첫 원이다(`/api/auth/me` 와 같은 규칙, 보안 규칙이 아니다). */
const myCenter = (id: number) => !!findCenter(id) && id === currentCenterId();
const centerMissing = () => failure("NOT_FOUND", "원을 찾을 수 없습니다.", "center_id");
/** 목업에는 로그인 사용자가 없다 — 첫 원을 「내 원」으로 본다 (data/centers.ts). */
const myClass = (id: number) => {
  const klass = findClass(id);
  return klass && klass.center_id === currentCenterId() ? klass : undefined;
};
const myMonthly = (id: number) => {
  const plan = findMonthly(id);
  return plan && myClass(plan.class_id) ? plan : undefined;
};
const annualMissing = () => failure("NOT_FOUND", "계획안을 찾을 수 없습니다.", "id");
const classMissing = () => failure("NOT_FOUND", "반을 찾을 수 없습니다.", "class_id");
const planMissing = () => failure("NOT_FOUND", "월간계획안을 찾을 수 없습니다.", "id");
const stale = () =>
  failure(
    "STALE_WRITE",
    "그 사이 다른 화면에서 계획안이 바뀌었습니다. 새로 불러온 뒤 다시 해주세요.",
    "expected_revision",
  );
/** 문자열 "3" · true 는 거절한다 (§9-3). */
const badRevision = (b: Record<string, unknown>) =>
  !integer(b.expected_revision) || b.expected_revision < 1;
/** 칸 편집 · 재생성 공통. 서버와 같은 순서로 본다: 입력 → 소유 → 확정 → revision → 칸. */
async function cellWrite(request: Request, id: string, itemId: string, needsValue: boolean) {
  const b = await body(request);
  if (!b) return bad("body");
  if (needsValue && typeof b.value !== "string") return bad("value");
  if (badRevision(b)) return bad("expected_revision");
  const plan = myMonthly(Number(id));
  if (!plan) return planMissing();
  if (plan.status === "CONFIRMED")
    return failure("ALREADY_CONFIRMED", "확정된 계획안은 수정할 수 없습니다.");
  if (plan.revision !== b.expected_revision) return stale();
  const found = findCell(plan, decodeURIComponent(itemId));
  return found
    ? { b, plan, ...found }
    : failure("NOT_FOUND", "그 칸을 찾을 수 없습니다.", "item_id");
}
