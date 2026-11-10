import { http, HttpResponse } from "msw";
import { failure } from "./scenarios";
import { findClass } from "./data/classes";
import { listChildren } from "./data/children";
import { findCenterSettings } from "./data/centers";
import { AXES } from "../lib/workspace/observation-axis";
import type { ApiObservation } from "../lib/api/types";

/**
 * 관찰 기록 목업 (api-spec §10 · ADR-082). 화면을 띄워 보는 용도라 **메모리에만** 둔다 —
 * 새로고침하면 사라진다. 기록 본문은 브라우저 저장소에 남기지 않는다(ADR-013).
 *
 * jev 도움(영역 추천 · 빠진 것)은 서버 mock 과 같이 **기본은 아무것도 안 한다.**
 * 화면 주소에 `?mswJev=1` 을 붙이면 그럴듯한 답을 준다. 「친구」가 들어간 글이면 사회관계를
 * 제안하고, 말(“ ”)이 없으면 「반응」이 빠졌다고 한다.
 * `?mswRoutines=1` 이면 오늘 일과 네 줄, `?mswImpact=1` 이면 고치기 · 지우기에 「다시 검토」 1건.
 */
const records: ApiObservation[] = [];
let next = 1;

const page = (key: string) =>
  typeof window !== "undefined" && new URLSearchParams(window.location.search).get(key) === "1";
const bad = (field: string) => failure("VALIDATION_FAILED", "입력값을 확인해주세요.", field);
const text = (v: unknown) => (typeof v === "string" ? v.trim() : "");
async function body(request: Request): Promise<Record<string, unknown> | null> {
  try {
    const b = await request.json();
    return b && typeof b === "object" && !Array.isArray(b) ? b : null;
  } catch {
    return null;
  }
}
const impact = () =>
  page("mswImpact")
    ? { affected_document_ids: [101], newly_stale_document_ids: [101] }
    : { affected_document_ids: [], newly_stale_document_ids: [] };

const today = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const ROUTINE_DAY = [
  ["등원", "09:00:00", null],
  ["실내놀이", "10:00:00", "11:30:00"],
  ["점심", "11:30:00", "12:30:00"],
  ["바깥놀이", "14:00:00", "15:00:00"],
] as const;

export const observationHandlers = [
  http.get("*/api/observations", ({ request }) => {
    const classId = Number(new URL(request.url).searchParams.get("class_id"));
    const items = records
      .filter((r) => !classId || r.class_id === classId)
      .sort((a, b) => b.date.localeCompare(a.date) || b.id - a.id);
    // 이 화면에서 적은 것이 없으면 다음 목업(관찰일지 · 보육일지 시연 자료)으로 넘긴다 (browser.ts).
    if (!items.length) return;
    // 아이별 기록 화면은 child_id 로 한 아이만 묻는다 — 거르지 않으면 반 기록이 다 섞여 나왔다.
    const childId = Number(new URL(request.url).searchParams.get("child_id"));
    return HttpResponse.json({ items: items.filter((r) => !childId || r.child_id === childId) });
  }),
  http.post("*/api/observations/domain-suggest", async ({ request }) => {
    const b = await body(request);
    if (!b || !text(b.fact)) return bad("fact");
    if (!page("mswJev")) return HttpResponse.json({ domain: null, confidence: null });
    return HttpResponse.json(
      text(b.fact).includes("친구")
        ? { domain: "사회관계", confidence: 0.86 }
        : { domain: null, confidence: 0.62 },
    );
  }),
  http.post("*/api/observations/:id/missing", ({ params }) => {
    const record = records.find((r) => r.id === Number(params.id));
    if (!record) return failure("NOT_FOUND", "관찰 기록을 찾을 수 없습니다.", "id");
    if (!page("mswJev")) return HttpResponse.json({ missing: [] });
    return HttpResponse.json({ missing: /[“"]/.test(record.fact) ? [] : ["반응"] });
  }),
  http.post("*/api/observations", async ({ request }) => {
    const b = await body(request);
    if (!b) return bad("body");
    const room = findClass(Number(b.class_id));
    const child = room && listChildren(room.id).find((c) => c.id === Number(b.child_id));
    if (!room || !child) return failure("NOT_FOUND", "반 · 아이를 찾을 수 없습니다.", "child_id");
    if (!text(b.fact)) return bad("fact");
    if (!text(b.domain)) return bad("domain");
    const record: ApiObservation = {
      id: next++,
      class_id: room.id,
      class_name: room.name,
      child_id: child.id,
      child_name: child.name,
      child_code: child.code,
      date: String(b.date),
      domain: text(b.domain),
      context: text(b.context).slice(0, 50),
      fact: text(b.fact),
      created_at: new Date().toISOString(),
    };
    records.push(record);
    return HttpResponse.json(record, { status: 201 });
  }),
  http.put("*/api/observations/:id", async ({ request, params }) => {
    const record = records.find((r) => r.id === Number(params.id));
    if (!record) return failure("NOT_FOUND", "관찰 기록을 찾을 수 없습니다.", "id");
    const b = await body(request);
    if (!b || !text(b.fact)) return bad("fact");
    Object.assign(record, {
      date: String(b.date),
      domain: text(b.domain),
      context: text(b.context).slice(0, 50),
      fact: text(b.fact),
    });
    const withImpact = new URL(request.url).searchParams.get("include_impact") === "true";
    return HttpResponse.json(withImpact ? { ...record, review_impact: impact() } : record);
  }),
  http.delete("*/api/observations/:id", ({ request, params }) => {
    const at = records.findIndex((r) => r.id === Number(params.id));
    if (at < 0) return failure("NOT_FOUND", "관찰 기록을 찾을 수 없습니다.", "id");
    records.splice(at, 1);
    if (new URL(request.url).searchParams.get("include_impact") !== "true")
      return new HttpResponse(null, { status: 204 });
    return HttpResponse.json({ review_impact: impact() });
  }),
  // 아이별 기록 수 (api-spec §2-1 「발달 추적」). 이 화면에서 적은 기록을 센다 — 없으면 모두 0.
  // 원이 쓰는 영역 축은 0 이어도 다 담고, 다른 축 영역은 1건 이상일 때만 붙인다.
  http.get("*/api/classes/:classId/children/tracking", ({ params }) => {
    const room = findClass(Number(params.classId));
    if (!room) return failure("NOT_FOUND", "반을 찾을 수 없습니다.", "class_id");
    const axis = AXES[findCenterSettings(room.center_id).observation_axis];
    const items = listChildren(room.id).map((child) => {
      const mine = records.filter((r) => r.class_id === room.id && r.child_id === child.id);
      const by_domain: Record<string, number> = Object.fromEntries(axis.map((d) => [d, 0]));
      for (const r of mine) by_domain[r.domain] = (by_domain[r.domain] ?? 0) + 1;
      const last = mine.reduce<string | null>((at, r) => (at && at > r.date ? at : r.date), null);
      return {
        child_id: child.id,
        name: child.name,
        code: child.code,
        total: mine.length,
        last_date: last,
        by_domain,
      };
    });
    return HttpResponse.json({ items });
  }),
  // 오늘 일과 — `?mswRoutines=1` 일 때만. 아니면 아무것도 안 돌려 handlers.ts 의 목업으로 넘긴다.
  http.get("*/api/routines", ({ request }) => {
    const q = new URL(request.url).searchParams;
    if (!page("mswRoutines") || q.get("from") !== today()) return;
    const class_id = Number(q.get("class_id"));
    return HttpResponse.json({
      items: ROUTINE_DAY.map(([name, start, end], i) => ({
        id: 900 + i,
        class_id,
        class_name: findClass(class_id)?.name ?? "",
        date: today(),
        position: i,
        start,
        end,
        name,
        plan: "",
        execution: "",
        created_at: new Date().toISOString(),
      })),
      weather: null,
    });
  }),
];
