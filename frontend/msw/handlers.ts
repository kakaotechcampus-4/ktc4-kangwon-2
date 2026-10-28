import { http, HttpResponse } from "msw";
import { failure, scenario } from "./scenarios";
import {
  findCenter,
  addCenter,
  patchCenter,
  putConfig,
  currentCenterId,
  findGreetings,
  putGreetings,
  findCenterSettings,
  putCenterSettings,
} from "./data/centers";
import type { Greetings } from "../lib/api/centers";
import { findClass, listClasses, addClass } from "./data/classes";
import { hasChild, listChildren, addChild, removeChild } from "./data/children";
import {
  findPlan,
  listPlans,
  addPlan,
  putMonth,
  putPlaySelection,
  putPlayCell,
  editablePlayCell,
  samePlayCellValue,
  confirmPlan,
  confirmPlayPlan,
  listAnnualAudit,
  safetyCategories,
} from "./data/annual-plans";
import {
  copyPlayMonthlyDrill,
  editPlayMonthlyCell,
  findPlayMonthly,
  findPlayMonthlyFor,
  listPlayMonthly,
  placePlayMonthlySafety,
  playCells,
  removePlayMonthly,
  removePlayMonthlyActivity,
} from "./data/play-monthly";
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
  REGENERATABLE as WEEKLY_REGENERATABLE,
  TEACHER_INPUT,
  addWeekly,
  confirmWeekly,
  editWeeklyCellValue,
  findWeekly,
  findWeeklyCell,
  findWeeklyFor,
  listWeekly,
  regenerateWeeklyCellValue,
  removeWeekly,
} from "./data/weekly-plans";
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
const MOCK_INVITE = "MOCK234567";
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
  // §1. 원 정보 고치기. 서버처럼 보낸 칸만 바꾸고, 지역은 두 칸을 함께 받는다.
  http.patch("*/api/centers/:centerId", async ({ request, params }) => {
    const id = Number(params.centerId);
    if (!findCenter(id) || id !== currentCenterId()) return missing();
    const b = await body(request);
    if (!b) return bad("body");
    for (const k of ["name", "director_name", "region_sido", "region_sigungu"])
      if (k in b && !text(b[k])) return bad(k);
    if ("region_sido" in b !== "region_sigungu" in b) return bad("region_sido");
    return HttpResponse.json(patchCenter(id, b as Partial<CenterInput>));
  }),
  // 초대 코드 (§1-1). 목업은 계정이 하나라 코드를 하나로 고정한다.
  http.post("*/api/centers/:centerId/invites", ({ params }) => {
    const id = Number(params.centerId);
    if (!findCenter(id) || id !== currentCenterId()) return missing();
    const expires_at = new Date(Date.now() + 7 * 24 * 3600 * 1000).toISOString();
    return HttpResponse.json({ code: MOCK_INVITE, expires_at }, { status: 201 });
  }),
  http.post("*/api/centers/join", async ({ request }) => {
    const b = await body(request);
    if (!b || !text(b.code)) return bad("code");
    // 실제 서버와 같은 순서다 — 이미 원이 있으면 409, 코드가 틀리면 404.
    if (currentCenterId() !== null) return failure("ALREADY_EXISTS", "이미 등록한 원이 있습니다.");
    if (b.code.trim().toUpperCase() !== MOCK_INVITE)
      return failure("NOT_FOUND", "초대 코드가 없거나 만료됐습니다.", "code");
    // 목업은 계정이 하나라 초대한 원이 없다. 들어갈 원을 그 자리에서 만든다.
    return HttpResponse.json(
      addCenter({
        name: "초대받은 어린이집",
        director_name: "김원장",
        region_sido: "강원특별자치도",
        region_sigungu: "춘천시",
      }),
    );
  }),
  // §3-2. 주 1회 모은 자료. 목업에서는 한 건만 둔다 — 화면이 비어 보이면 안 된다.
  http.get("*/api/trends", async ({ request }) => {
    const s = await scenario(request, "trends");
    if (s) return s;
    const id = currentCenterId();
    if (id === null) return missing();
    if (!findCenterSettings(id).trends_enabled)
      return failure("TRENDS_DISABLED", "트렌드봇이 꺼져 있어요. 설정에서 켜면 쓸 수 있어요.");
    return HttpResponse.json({
      week: "2026-W42",
      items: [
        {
          source: "youtube",
          title: "영유아놀이｜가을 놀이｜낙엽이 변신해요!",
          summary: "낙엽을 모아 모양을 만들고 붙여 보는 가을 놀이 세 가지예요.",
          url: "https://www.youtube.com/watch?v=example",
          published_at: "2026-10-02",
          origin: "꼬미쌤TV",
        },
      ],
    });
  }),
  // §3-1. 기본은 꺼짐. 설정한 적 없어도 기본값을 채워 준다 — 빈 객체를 주지 않는다.
  http.get("*/api/centers/:centerId/settings", async ({ request, params }) => {
    const s = await scenario(request, "center-settings");
    if (s) return s;
    const id = Number(params.centerId);
    if (!findCenter(id) || id !== currentCenterId()) return missing();
    return HttpResponse.json(findCenterSettings(id));
  }),
  http.put("*/api/centers/:centerId/settings", async ({ request, params }) => {
    const s = await scenario(request, "center-settings-save");
    if (s) return s;
    const id = Number(params.centerId);
    if (!findCenter(id) || id !== currentCenterId()) return missing();
    const b = await body(request);
    if (!b) return bad("body");
    const SETTING_KEYS = ["trends_enabled", "weekly_saturday_enabled", "observation_axis"];
    if (Object.keys(b).some((key) => !SETTING_KEYS.includes(key))) return bad("body");
    // **보낸 칸만 바꾼다.** 빈 요청은 아무것도 바꾸지 않는다.
    const patch: Parameters<typeof putCenterSettings>[1] = {};
    for (const key of ["trends_enabled", "weekly_saturday_enabled"] as const) {
      if (b[key] === undefined) continue;
      if (typeof b[key] !== "boolean") return bad(key);
      patch[key] = b[key];
    }
    if (b.observation_axis !== undefined) {
      if (b.observation_axis !== "NURI_5" && b.observation_axis !== "DAILY_PLAY_2")
        return bad("observation_axis");
      patch.observation_axis = b.observation_axis;
    }
    if (!Object.keys(patch).length) return HttpResponse.json(findCenterSettings(id));
    return HttpResponse.json(putCenterSettings(id, patch));
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
    // 서버 순서: 형식 422(format → form_id) → 반 404 → 중복 409.
    if (b.format !== "MONTHLY_THEME" && b.format !== "PLAY_PROJECT") return bad("format");
    if (b.form_id != null && !integer(b.form_id)) return bad("form_id");
    if (b.format === "PLAY_PROJECT" && b.form_id != null) return bad("form_id");
    // 연간 목업은 「지금 원」 소유 검사를 하지 않는다(서버는 남의 원 반이면 404) — 화면 목업 흐름 유지.
    const klass = findClass(Number(b.class_id));
    if (!klass) return classMissing();
    // 서버처럼 반 하나에 연간 하나다.
    if (annualFor(klass.id))
      return failure("ALREADY_EXISTS", "이 반의 연간계획안이 이미 있습니다.", "class_id");
    if (request.signal.aborted) return HttpResponse.error();
    // 실제 서버는 교육과정 참고자료 승인 전까지 503을 반환하지만, 화면 작업용 목업은 승인 뒤 응답 모양을 만든다.
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
    const extra = Object.keys(b).find(
      (k) => k !== "theme" && k !== "sub_themes" && k !== "safety_education",
    );
    if (extra) return bad(extra);
    if (typeof b.theme !== "string" || !b.theme) return bad("theme");
    if (!Array.isArray(b.sub_themes) || !b.sub_themes.every((v) => typeof v === "string"))
      return bad("sub_themes");
    if (b.safety_education !== undefined && b.safety_education !== null) {
      const allowed = new Set(safetyCategories.map((category) => category.category_id));
      if (
        !Array.isArray(b.safety_education) ||
        b.safety_education.some((v) => typeof v !== "string" || !allowed.has(v)) ||
        new Set(b.safety_education).size !== b.safety_education.length
      )
        return bad("safety_education");
    }
    const id = Number(params.id),
      month = Number(params.month),
      plan = findPlan(id);
    if (!plan) return annualMissing();
    if (plan.format === "PLAY_PROJECT")
      return failure("GATE_BLOCKED", "놀이 프로젝트형은 칸 편집으로 고칩니다.");
    if (!plan.months.some((m) => m.month === month))
      return failure("NOT_FOUND", "그 달이 없습니다.", "month");
    if (plan.status === "CONFIRMED")
      return failure("ALREADY_CONFIRMED", "확정된 계획안은 수정할 수 없습니다.");
    // 공백만 있는 주제는 Core 가 거절한다 — 서버도 fields 를 주지 않는다.
    if (!b.theme.trim()) return failure("VALIDATION_FAILED", "입력값을 확인해주세요.");
    return HttpResponse.json(putMonth(id, month, b as unknown as MonthInput));
  }),
  http.put("*/api/plans/annual/:id/selection", async ({ request, params }) => {
    const s = await scenario(request, "annual-selection");
    if (s) return s;
    // 서버 순서: 본문 형식 422 → 계획안 404 → 형식 409 → 확정 409 → revision 409 → 없는 row_key 422 (§6-1).
    const b = await body(request);
    if (!b) return bad("body");
    const wrong = selectionProblems(b.selections);
    if (badRevision(b)) wrong.push("expected_revision");
    if (wrong.length) return failure("VALIDATION_FAILED", "입력값을 확인해주세요.", ...wrong);
    const selections = b.selections as Record<string, string[]>;
    const id = Number(params.id),
      plan = findPlan(id);
    if (!plan) return annualMissing();
    if (plan.format !== "PLAY_PROJECT")
      return failure("GATE_BLOCKED", "월별 주제형은 월별 칸 수정으로 고칩니다.");
    if (plan.status === "CONFIRMED")
      return failure("ALREADY_CONFIRMED", "확정된 계획안은 수정할 수 없습니다.");
    if (plan.revision !== b.expected_revision) return stale();
    const unknown = plan.periods
      .filter((period) =>
        selections[period.period_key].some(
          (key) => !period.candidates.some((candidate) => candidate.row_key === key),
        ),
      )
      .map((period) => "selections." + period.period_key);
    if (unknown.length) return failure("VALIDATION_FAILED", "입력값을 확인해주세요.", ...unknown);
    return HttpResponse.json(putPlaySelection(id, selections));
  }),
  http.put("*/api/plans/annual/:id/cells/:itemId", async ({ request, params }) => {
    const s = await scenario(request, "annual-cell");
    if (s) return s;
    // 서버 순서: 스키마 422 → 계획안 404 → 형식 409 → 확정 409 → revision 409 → 칸 422 → 같은 값 422 (§6-1).
    const b = await body(request);
    if (!b) return bad("body");
    const value = typeof b.value === "string" ? b.value.trim() : "";
    const wrong = [];
    const length = [...value].length; // 서버는 글자(코드포인트) 수로 센다.
    if (length < 1 || length > 600) wrong.push("value");
    if (badRevision(b)) wrong.push("expected_revision");
    if (wrong.length) return failure("VALIDATION_FAILED", "입력값을 확인해주세요.", ...wrong);
    const id = Number(params.id),
      itemId = decodeURIComponent(String(params.itemId)),
      plan = findPlan(id);
    if (!plan) return annualMissing();
    if (plan.format !== "PLAY_PROJECT")
      return failure("GATE_BLOCKED", "월별 주제형은 월별 칸 수정으로 고칩니다.");
    if (plan.status === "CONFIRMED")
      return failure("ALREADY_CONFIRMED", "확정된 계획안은 수정할 수 없습니다.");
    if ((plan.revision ?? 1) !== b.expected_revision) return stale();
    if (!editablePlayCell(id, itemId))
      return failure("VALIDATION_FAILED", "입력값을 확인해주세요.", "item_id");
    if (samePlayCellValue(id, itemId, value))
      return failure("VALIDATION_FAILED", "입력값을 확인해주세요.", "value");
    return HttpResponse.json(putPlayCell(id, itemId, value));
  }),
  http.post("*/api/plans/annual/:id/confirm", async ({ request, params }) => {
    const s = await scenario(request, "confirm");
    if (s) return s;
    const id = Number(params.id),
      plan = findPlan(id);
    if (!plan) return annualMissing();
    if (plan.format === "PLAY_PROJECT") {
      // 서버 순서: 404 → 본문 스키마 422(값이 있는데 정수 1 이상이 아님, 확정본이어도) → 이미 확정이면 200
      // → 본문 없음 422 → revision 409 → 5개 미만 422 (§7). 본문을 읽는 사이 바뀔 수 있어 그 뒤에 다시 본다.
      const b = await body(request);
      const given = b?.expected_revision;
      const present = given !== undefined && given !== null;
      if (present && badRevision(b!)) return bad("expected_revision");
      const now = findPlan(id);
      if (!now || now.format !== "PLAY_PROJECT") return annualMissing();
      if (now.status === "CONFIRMED") return HttpResponse.json(now);
      if (!present) return bad("expected_revision");
      if (now.revision !== given) return stale();
      const lacking = now.periods
        .filter((period) => period.selected.length !== 5)
        .map((period) => period.period_key);
      if (lacking.length) return failure("VALIDATION_FAILED", "입력값을 확인해주세요.", ...lacking);
      return HttpResponse.json(confirmPlayPlan(id));
    }
    // 재호출은 200 · 같은 응답 · 상태 변화 없음(§7). 서버는 빈 소주제로 확정을 막지 않는다.
    return HttpResponse.json(confirmPlan(id));
  }),
  // 실제 서버: 확정본은 200 hwpx(가짜 파일), 미확정은 형식 상관없이 409 — 문구만 형식별 (§9).
  http.get("*/api/plans/:id/export/hwp", async ({ request, params }) => {
    const s = await scenario(request, "annual-export");
    if (s) return s;
    const id = Number(params.id),
      plan = findPlan(id);
    if (!plan) return annualMissing();
    if (plan.status !== "CONFIRMED") {
      return failure(
        "GATE_BLOCKED",
        plan.format === "PLAY_PROJECT"
          ? "놀이 프로젝트형 연간계획안은 확정한 뒤 내려받을 수 있습니다."
          : "확정된 계획안만 내보낼 수 있습니다.",
      );
    }
    const name = `plan-${id}.hwpx`;
    return new HttpResponse("MSW hwpx", {
      headers: {
        "Content-Type": "application/hwp+zip",
        "Content-Disposition": `attachment; filename="${name}"; filename*=UTF-8''${name}`,
      },
    });
  }),
  http.get("*/api/plans/annual/:id/audit", async ({ request, params }) => {
    const s = await scenario(request, "annual-audit");
    if (s) return s;
    const id = Number(params.id),
      plan = findPlan(id);
    if (!plan) return annualMissing();
    return HttpResponse.json({ items: listAnnualAudit(id) });
  }),
  // 놀이 중심 월간 (api-spec §9-7). **`/monthly/:id` 보다 먼저 둔다** — 아니면 `play` 가 id 로 잡힌다.
  // 서버 순서: 스키마 422(경로 · 본문 · 쿼리) → 경로의 item · week 형식 422 → 소유 404 → 기존 월간 409
  // → 확정 409 → revision 409 → 내용 404 · 422. 같은 입력은 200 · 무변경, 바뀌면 revision + 1.
  http.post("*/api/plans/monthly/play", async ({ request }) => {
    const s = await scenario(request, "play-monthly-create");
    if (s) return s;
    const b = await body(request);
    if (!b) return bad("body");
    const keys = b.emphasized_row_keys ?? [];
    const trimmed = Array.isArray(keys)
      ? keys.map((k) => (typeof k === "string" ? k.trim() : ""))
      : [];
    const wrong = [
      ...(integer(b.class_id) ? [] : ["class_id"]),
      ...(integer(b.month) && b.month >= 1 && b.month <= 12 ? [] : ["month"]),
      ...(Array.isArray(keys) &&
      trimmed.length <= 5 &&
      trimmed.every((k) => k.length >= 1 && k.length <= 20) &&
      new Set(trimmed).size === trimmed.length
        ? []
        : ["emphasized_row_keys"]),
    ];
    if (wrong.length) return invalid(wrong);
    const klass = myClass(Number(b.class_id));
    if (!klass) return classMissing();
    const target = targetMonthOf(klass.school_year, Number(b.month));
    if (findMonthlyFor(klass.id, target) || findPlayMonthlyFor(klass.id, target))
      return failure(
        "ALREADY_EXISTS",
        "이 반의 그 달 월간계획안이 이미 있습니다.",
        "class_id",
        "month",
      );
    const annual = annualFor(klass.id);
    const gate = !annual
      ? "연간계획안을 먼저 만들어 확정해주세요."
      : annual.format !== "PLAY_PROJECT"
        ? "월별 주제형 연간계획안으로는 놀이 중심 월간계획안을 만들 수 없습니다."
        : annual.status !== "CONFIRMED"
          ? "연간계획안을 먼저 확정해주세요."
          : null;
    if (gate) return failure("GATE_BLOCKED", gate, "class_id");
    // 서버는 생성 규칙이 아직 없어 게이트 뒤에서 항상 503 이다. 아무것도 저장하지 않는다.
    return failure(
      "DEPENDENCY_UNAVAILABLE",
      "지금은 이 반의 놀이 중심 월간계획안을 만들 수 없습니다. 관리자에게 문의해 주세요.",
    );
  }),
  http.get("*/api/plans/monthly/play", async ({ request }) => {
    const s = await scenario(request, "play-monthly-list");
    if (s) return s;
    const raw = new URL(request.url).searchParams.get("class_id");
    if (raw === null) {
      const center = currentCenterId();
      const ids = center === null ? [] : listClasses(center).map((c) => c.id);
      return HttpResponse.json({ items: listPlayMonthly(ids) });
    }
    if (!/^-?\d+$/.test(raw)) return invalid(["class_id"]);
    const klass = myClass(Number(raw));
    return klass ? HttpResponse.json({ items: listPlayMonthly([klass.id]) }) : classMissing();
  }),
  http.get("*/api/plans/monthly/play/:id", async ({ request, params }) => {
    const s = await scenario(request, "play-monthly-get");
    if (s) return s;
    const plan = playOwn(String(params.id));
    return plan instanceof Response ? plan : HttpResponse.json(plan);
  }),
  http.delete("*/api/plans/monthly/play/:id", async ({ request, params }) => {
    const s = await scenario(request, "play-monthly-delete");
    if (s) return s;
    const plan = playOwn(String(params.id));
    if (plan instanceof Response) return plan;
    if (plan.status === "CONFIRMED")
      return failure("GATE_BLOCKED", "확정된 계획안은 지울 수 없습니다.");
    removePlayMonthly(plan.id);
    return new HttpResponse(null, { status: 204 });
  }),
  http.put("*/api/plans/monthly/play/:id/cells/:itemId", async ({ request, params }) => {
    const s = await scenario(request, "play-monthly-cell");
    if (s) return s;
    const b = await playInput(request, params.id, (b) =>
      typeof b.value === "string" && [...b.value.trim()].length <= 600 ? [] : ["value"],
    );
    if (b instanceof Response) return b;
    const itemId = decodeURIComponent(String(params.itemId));
    if (!itemId.trim()) return invalid(["item_id"]);
    const plan = playGate(params.id, b);
    if (plan instanceof Response) return plan;
    const cell = playCells(plan).find((c) => c.item_id === itemId);
    if (!cell) return failure("NOT_FOUND", "그 칸을 찾을 수 없습니다.", "item_id");
    const value = String(b.value).trim();
    // 같은 값은 422 — 빈 값 → 빈 값(공백만 든 칸 포함)도 같다.
    if (value === cell.value || !(value || cell.value.trim())) return invalid(["value"]);
    return HttpResponse.json(editPlayMonthlyCell(plan.id, itemId, value));
  }),
  http.delete("*/api/plans/monthly/play/:id/activities/:itemId", async ({ request, params }) => {
    const s = await scenario(request, "play-monthly-activity");
    if (s) return s;
    const b = await playInput(request, params.id, () => [], true); // revision 은 쿼리다
    if (b instanceof Response) return b;
    const itemId = decodeURIComponent(String(params.itemId));
    if (!itemId.trim()) return invalid(["item_id"]);
    const plan = playGate(params.id, b);
    if (plan instanceof Response) return plan;
    if (![...plan.together, ...plan.free_play].some((a) => a.activity_id === itemId))
      return failure("NOT_FOUND", "그 행을 찾을 수 없습니다.", "item_id");
    return HttpResponse.json(removePlayMonthlyActivity(plan.id, itemId));
  }),
  http.put("*/api/plans/monthly/play/:id/safety-weeks/:weekId", async ({ request, params }) => {
    const s = await scenario(request, "play-monthly-safety");
    if (s) return s;
    // 키는 필수이고 값만 null 일 수 있다.
    const b = await playInput(request, params.id, (b) =>
      b.candidate_item_id === null || typeof b.candidate_item_id === "string"
        ? []
        : ["candidate_item_id"],
    );
    if (b instanceof Response) return b;
    const weekId = decodeURIComponent(String(params.weekId)),
      candidate = b.candidate_item_id as string | null;
    if (!/^\d{4}-(0[1-9]|1[0-2])-W[1-9]\d?$/.test(weekId)) return invalid(["week_id"]);
    if (candidate !== null && !candidate.trim()) return invalid(["candidate_item_id"]);
    const plan = playGate(params.id, b);
    if (plan instanceof Response) return plan;
    if (!plan.safety_weeks.some((w) => w.week_id === weekId))
      return failure("NOT_FOUND", "그 주를 찾을 수 없습니다.", "week_id");
    if (candidate !== null && !plan.safety_candidates.some((c) => c.cell.item_id === candidate))
      return invalid(["candidate_item_id"]);
    return HttpResponse.json(placePlayMonthlySafety(plan.id, weekId, candidate));
  }),
  http.post(
    "*/api/plans/monthly/play/:id/drill-candidates/:itemId/copy",
    async ({ request, params }) => {
      const s = await scenario(request, "play-monthly-drill");
      if (s) return s;
      const b = await playInput(request, params.id, () => []);
      if (b instanceof Response) return b;
      const itemId = decodeURIComponent(String(params.itemId));
      if (!itemId.trim()) return invalid(["item_id"]);
      const plan = playGate(params.id, b);
      if (plan instanceof Response) return plan;
      const drill = plan.drill_candidates.find((d) => d.cell.item_id === itemId);
      if (!drill) return failure("NOT_FOUND", "그 훈련 후보를 찾을 수 없습니다.", "item_id");
      if (!drill.cell.value.trim()) return invalid(["item_id"]);
      return HttpResponse.json(copyPlayMonthlyDrill(plan.id, itemId));
    },
  ),
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
    if (
      findMonthlyFor(klass.id, targetMonthOf(klass.school_year, b.month)) ||
      findPlayMonthlyFor(klass.id, targetMonthOf(klass.school_year, b.month))
    )
      return failure(
        "ALREADY_EXISTS",
        "이 반의 그 달 월간계획안이 이미 있습니다.",
        "class_id",
        "month",
      );
    const annual = annualFor(klass.id);
    if (!annual)
      return failure("GATE_BLOCKED", "연간계획안을 먼저 만들어 확정해주세요.", "class_id");
    if (annual.format === "PLAY_PROJECT")
      return failure(
        "GATE_BLOCKED",
        "놀이 프로젝트형 연간계획안으로는 기존 월간계획안을 만들 수 없습니다. 놀이 중심 월간계획안으로 만들어 주세요.",
        "class_id",
      );
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
    return plan ? HttpResponse.json(plan) : planMissing(Number(params.id));
  }),
  // 변경 이력 (§9-5). 소유를 먼저 본다 — 남의 계획안이면 item_id 를 보기 전에 404 ["id"].
  http.get("*/api/plans/monthly/:id/audit", async ({ request, params }) => {
    const s = await scenario(request, "monthly-audit");
    if (s) return s;
    const plan = myMonthly(Number(params.id));
    if (!plan) return planMissing(Number(params.id));
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
    if (!plan) return planMissing(Number(params.id));
    // 이미 확정이면 revision 과 상관없이 200 · 저장된 그대로 (D-M5-CONFIRM-01).
    if (plan.status === "CONFIRMED") return HttpResponse.json(plan);
    if (plan.revision !== b.expected_revision) return stale();
    return HttpResponse.json(confirmMonthly(plan.id));
  }),
  // 주간계획안 (docs/weekly-plan-contract.md §13). 월간과 같은 모양 · 같은 공개 오류 코드다.
  http.post("*/api/plans/weekly", async ({ request }) => {
    const s = await scenario(request, "weekly", 1200);
    if (s) return s;
    const b = await body(request);
    if (!b) return bad("body");
    if (!integer(b.class_id)) return bad("class_id");
    if (typeof b.week_id !== "string" || !/^\d{4}-\d{2}-W\d+$/.test(b.week_id))
      return bad("week_id");
    const klass = myClass(b.class_id);
    if (!klass) return classMissing();
    // G5 — 같은 반 · 같은 주가 이미 있으면 DRAFT 든 CONFIRMED 든 거절한다.
    if (findWeeklyFor(klass.id, b.week_id))
      return failure("ALREADY_EXISTS", "이 반의 그 주 주간계획안이 이미 있습니다.", "week_id");
    // G3 — 그 달 월간이 확정돼야 한다. 연간은 직접 보지 않는다 (§4-1).
    const monthly = findMonthlyFor(klass.id, b.week_id.slice(0, 7));
    if (!monthly)
      return failure("GATE_BLOCKED", "그 달 월간계획안을 먼저 만들어 확정해주세요.", "week_id");
    if (monthly.status !== "CONFIRMED")
      return failure("GATE_BLOCKED", "그 달 월간계획안을 먼저 확정해주세요.", "week_id");
    // G4 — 주 주소는 월간이 정한다. 월간에 없거나 쉬는 주면 거절한다 (§3-1).
    const week = monthly.weeks.find((w) => w.week_id === b.week_id);
    if (!week || !week.active) return bad("week_id");
    if (request.signal.aborted) return HttpResponse.error();
    const saturday = !!findCenterSettings(klass.center_id).weekly_saturday_enabled;
    return HttpResponse.json(addWeekly(klass, monthly, b.week_id, saturday), { status: 201 });
  }),
  http.get("*/api/plans/weekly", async ({ request }) => {
    const s = await scenario(request, "weekly-list");
    if (s) return s;
    const query = new URL(request.url).searchParams;
    const raw = query.get("class_id");
    const month = Number(query.get("month"));
    // `month` 는 **달력 달 1~12** 다. 연도는 반의 학년도가 정한다 (월간 생성과 같은 규칙).
    if (raw === null || !/^-?\d+$/.test(raw)) return bad("class_id");
    if (!Number.isInteger(month) || month < 1 || month > 12) return bad("month");
    const klass = myClass(Number(raw));
    if (!klass) return classMissing();
    return HttpResponse.json({
      items: listWeekly([klass.id], targetMonthOf(klass.school_year, month)),
    });
  }),
  http.get("*/api/plans/weekly/:id", async ({ request, params }) => {
    const s = await scenario(request, "weekly-get");
    if (s) return s;
    const plan = myWeekly(Number(params.id));
    return plan ? HttpResponse.json(plan) : weeklyMissing();
  }),
  http.put("*/api/plans/weekly/:id/cells/:itemId", async ({ request, params }) => {
    const s = await scenario(request, "weekly-cell");
    if (s) return s;
    const w = await weeklyCellWrite(request, String(params.id), String(params.itemId), true);
    if (w instanceof Response) return w;
    if (w.cell.value === w.b.value)
      return failure(
        "VALIDATION_FAILED",
        "칸의 값이 바뀌지 않았거나 쓸 수 없는 값입니다.",
        "value",
      );
    return HttpResponse.json(editWeeklyCellValue(w.plan.id, w.cell.item_id, String(w.b.value)));
  }),
  http.post("*/api/plans/weekly/:id/cells/:itemId/regenerate", async ({ request, params }) => {
    const s = await scenario(request, "weekly-regenerate", 1200);
    if (s) return s;
    const w = await weeklyCellWrite(request, String(params.id), String(params.itemId), false);
    if (w instanceof Response) return w;
    // 교사 입력 칸은 만든 적이 없어 다시 만들 것도 없다 (§6-2).
    if (TEACHER_INPUT.includes(w.section.section_key))
      return failure("VALIDATION_FAILED", "교사가 적는 칸이라 다시 만들 수 없습니다.", "item_id");
    if (!WEEKLY_REGENERATABLE.includes(w.section.section_key))
      return failure("VALIDATION_FAILED", "이 칸은 다시 만들 수 없습니다.", "item_id");
    if (request.signal.aborted) return HttpResponse.error();
    const label = w.section.label ?? w.section.section_key;
    return HttpResponse.json(
      regenerateWeeklyCellValue(w.plan.id, w.cell.item_id, label, w.plan.revision + 1),
    );
  }),
  http.post("*/api/plans/weekly/:id/confirm", async ({ request, params }) => {
    const s = await scenario(request, "weekly-confirm");
    if (s) return s;
    const b = await body(request);
    if (!b) return bad("body");
    if (badRevision(b)) return bad("expected_revision");
    const plan = myWeekly(Number(params.id));
    if (!plan) return weeklyMissing();
    // 이미 확정이면 revision 과 상관없이 200 — 재시도 · 더블클릭은 실패가 아니다 (월간과 같다).
    if (plan.status === "CONFIRMED") return HttpResponse.json(plan);
    if (plan.revision !== b.expected_revision) return stale();
    // 놀이 주제가 비면 확정할 수 없다 (§6-2 「확정 필수」).
    const theme = plan.sections.find((s2) => s2.section_key === "theme")?.cells[0];
    if (theme && !theme.value.trim())
      return failure("VALIDATION_FAILED", "놀이 주제를 적어야 확정할 수 있습니다.", "theme");
    return HttpResponse.json(confirmWeekly(plan.id));
  }),
  http.delete("*/api/plans/weekly/:id", async ({ request, params }) => {
    const s = await scenario(request, "weekly-delete");
    if (s) return s;
    const plan = myWeekly(Number(params.id));
    if (!plan) return weeklyMissing();
    if (plan.status === "CONFIRMED")
      return failure("GATE_BLOCKED", "확정된 계획안은 지울 수 없습니다.");
    removeWeekly(plan.id);
    return new HttpResponse(null, { status: 204 });
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
const myWeekly = (id: number) => {
  const plan = findWeekly(id);
  return plan && myClass(plan.class_id) ? plan : undefined;
};
const weeklyMissing = () => failure("NOT_FOUND", "주간계획안을 찾을 수 없습니다.", "id");
/** 주간 칸 편집 · 재생성 공통. 월간 `cellWrite` 와 같은 순서로 본다. */
async function weeklyCellWrite(request: Request, id: string, itemId: string, needsValue: boolean) {
  const b = await body(request);
  if (!b) return bad("body");
  if (needsValue && typeof b.value !== "string") return bad("value");
  if (badRevision(b)) return bad("expected_revision");
  const plan = myWeekly(Number(id));
  if (!plan) return weeklyMissing();
  if (plan.status === "CONFIRMED")
    return failure("ALREADY_CONFIRMED", "확정된 계획안은 수정할 수 없습니다.");
  if (plan.revision !== b.expected_revision) return stale();
  const found = findWeeklyCell(plan, decodeURIComponent(itemId));
  return found
    ? { b, plan, ...found }
    : failure("NOT_FOUND", "그 칸을 찾을 수 없습니다.", "item_id");
}
const annualMissing = () => failure("NOT_FOUND", "계획안을 찾을 수 없습니다.", "id");
const classMissing = () => failure("NOT_FOUND", "반을 찾을 수 없습니다.", "class_id");
/** 기존 월간 경로가 놀이 월간 id 를 받으면 없는 것이 아니라 409 다(서버: 형식 검사). */
const planMissing = (legacyId?: number) =>
  legacyId !== undefined && myPlayMonthly(legacyId)
    ? failure("GATE_BLOCKED", "놀이 중심 월간계획안은 /api/plans/monthly/play 경로로 다룹니다.")
    : failure("NOT_FOUND", "월간계획안을 찾을 수 없습니다.", "id");
const stale = () =>
  failure(
    "STALE_WRITE",
    "그 사이 다른 화면에서 계획안이 바뀌었습니다. 새로 불러온 뒤 다시 해주세요.",
    "expected_revision",
  );
const invalid = (fields: string[]) =>
  failure("VALIDATION_FAILED", "입력값을 확인해주세요.", ...fields);
const myPlayMonthly = (id: number) => {
  const plan = findPlayMonthly(id);
  return plan && myClass(plan.class_id) ? plan : undefined;
};
/** 이 원의 놀이 월간. 경로 id 가 정수가 아니면 422, 없거나 남의 원이면 404, 기존 월간이면 409. */
function playOwn(raw: unknown) {
  if (!/^\d+$/.test(String(raw))) return invalid(["plan_id"]);
  const id = Number(raw);
  return (
    myPlayMonthly(id) ??
    (myMonthly(id)
      ? failure("GATE_BLOCKED", "기존 월간계획안은 /api/plans/monthly 경로로 다룹니다.")
      : planMissing())
  );
}
/** 스키마 검사. 경로 id · 본문(또는 쿼리) revision · `check` 가 모은 칸을 한 번에 422 로 준다. */
async function playInput(
  request: Request,
  rawId: unknown,
  check: (b: Record<string, unknown>) => string[],
  revisionInQuery = false,
) {
  const given = new URL(request.url).searchParams.get("expected_revision");
  const b = revisionInQuery
    ? { expected_revision: given !== null && /^\d+$/.test(given) ? Number(given) : null }
    : await body(request);
  const wrong = [
    ...(/^\d+$/.test(String(rawId)) ? [] : ["plan_id"]),
    ...(b ? [...(badRevision(b) ? ["expected_revision"] : []), ...check(b)] : ["body"]),
  ];
  return wrong.length ? invalid(wrong) : b!;
}
/** 소유 → 형식 → 확정 → revision. 통과하면 계획안을 준다. */
function playGate(rawId: unknown, b: Record<string, unknown>) {
  const plan = playOwn(rawId);
  if (plan instanceof Response) return plan;
  if (plan.status === "CONFIRMED")
    return failure("ALREADY_CONFIRMED", "확정된 계획안은 수정할 수 없습니다.");
  return plan.revision === b.expected_revision ? plan : stale();
}
const PLAY_PERIODS = ["m03_m05", "m06_m08", "m09_m11", "m12_m02"];
/** 네 구간이 전부 있고 구간마다 중복 없는 5개 이하 목록이어야 한다 (§6-1). 문제 있는 칸 이름을 모은다. */
function selectionProblems(selections: unknown): string[] {
  if (!selections || typeof selections !== "object" || Array.isArray(selections))
    return ["selections"];
  const given = selections as Record<string, unknown>;
  const unknownKeys = Object.keys(given).filter((key) => !PLAY_PERIODS.includes(key));
  return [...PLAY_PERIODS, ...unknownKeys]
    .filter((key) => {
      const list = given[key];
      return (
        !Array.isArray(list) ||
        list.length > 5 ||
        !list.every((v) => typeof v === "string") ||
        new Set(list).size !== list.length ||
        unknownKeys.includes(key)
      );
    })
    .map((key) => "selections." + key);
}
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
  if (!plan) return planMissing(Number(id));
  if (plan.status === "CONFIRMED")
    return failure("ALREADY_CONFIRMED", "확정된 계획안은 수정할 수 없습니다.");
  if (plan.revision !== b.expected_revision) return stale();
  const found = findCell(plan, decodeURIComponent(itemId));
  return found
    ? { b, plan, ...found }
    : failure("NOT_FOUND", "그 칸을 찾을 수 없습니다.", "item_id");
}
