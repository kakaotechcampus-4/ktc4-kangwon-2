import { http, HttpResponse } from "msw";
import { failure } from "./scenarios";
import { findClass } from "./data/classes";
import { listChildren } from "./data/children";

/**
 * 관찰일지 화면 목업 (§10 관찰 기록 읽기 · §11 문서 · ADR-083). 화면 작업 · 캡처용이라 새로고침하면 사라진다.
 *
 * 관찰 기록은 반을 처음 읽을 때 그 반 아이 순서대로 지어낸다(`COUNTS`).
 * 초안의 해석 첫 문장에 「매일」을 넣고 검토가 그 문장을 짚는다. 셋째 아이 초안은 검토를 못 한 것으로 둔다.
 * 판정 · 고쳐 쓰기는 진짜 모델이 아니다 — 서버 계약의 모양만 따른다.
 */
type Json = Record<string, unknown>;
interface Doc {
  id: number;
  kind: string;
  title: string;
  class_id: number;
  class_name: string;
  child_id: number;
  child_name: string;
  start: string;
  end: string;
  status: "DRAFT" | "CONFIRMED";
  origin: "AI";
  stale: boolean;
  sections: { heading: string; body: string; source_ids: number[] }[];
  sources: Json[];
  ai_review: { state: string; issues: Json[]; message: string } | null;
  created_at: string;
  updated_at: string;
}

const FACTS = [
  ["블록 세 개를 쌓고 친구에게 같이 만들자고 말했다.", "쌓기"],
  ["비 오는 소리를 듣고 톡톡 하고 따라 말했다.", "언어"],
  ["모래로 길을 만들고 친구에게 물을 부어 달라고 했다.", "바깥놀이"],
];
const DOMAINS = ["사회관계", "의사소통", "자연탐구"];
/** 반 아이 순서대로 기록 수 — 3 · 2 · 2 · 1, 다섯째부터 없음(기록 1개는 반 전체에서 체크가 꺼진다). */
const COUNTS = [3, 2, 2, 1];
const observations = new Map<number, Json[]>();
const documents: Doc[] = [];
let next = 9000;

const day = (back: number) => {
  const d = new Date(Date.now() - back * 86_400_000);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const now = () => new Date().toISOString();

function recordsFor(classId: number): Json[] {
  if (observations.has(classId)) return observations.get(classId)!;
  const room = findClass(classId);
  const rows = listChildren(classId).flatMap((child, i) =>
    Array.from({ length: COUNTS[i] ?? 0 }, (_, k) => ({
      id: next++,
      class_id: classId,
      class_name: room?.name ?? "",
      child_id: child.id,
      child_name: child.name,
      child_code: child.code,
      date: day(k),
      domain: DOMAINS[k % DOMAINS.length],
      context: FACTS[k % FACTS.length][1],
      fact: FACTS[k % FACTS.length][0],
      created_at: new Date(Date.now() - 86_400_000 * 3).toISOString(),
    })),
  );
  observations.set(classId, rows);
  return rows;
}

const flagged = (body: string) =>
  body
    .split(/(?<=[.!?])\s+/)
    .filter((s) => s.includes("매일"))
    .map((sentence) => ({
      heading: "해석",
      sentence,
      code: "UNSUPPORTED_FACT",
      source_id: null,
      source_text: null,
      reason: "「매일」은 기록에 없어요. 기록은 이 기간에 한두 번이에요.",
      fix: "직접 보았다면 관찰 기록에 먼저 적어 주세요.",
    }));
const body = (d: Doc, heading: string) => d.sections.find((s) => s.heading === heading)?.body ?? "";
const summary = (d: Doc) => {
  const { sources, ai_review, ...rest } = d;
  return {
    ...rest,
    sections: undefined,
    generation: { method: "RULE_LLM", rule_id: "observation-draft", rule_version: "v5" },
    sources_count: sources.length,
    ai_review_state: ai_review?.state ?? null,
  };
};
const detail = (d: Doc) => ({
  ...summary(d),
  sections: d.sections,
  sources: d.sources,
  review_note: "",
  class_note: "",
  observation_axis: "NURI_5",
  ai_review: d.ai_review,
});
const find = (id: string | readonly string[] | undefined) =>
  documents.find((d) => d.id === Number(id));
const missing = () => failure("NOT_FOUND", "문서를 찾을 수 없습니다.", "document_id");

export const journalHandlers = [
  http.get("*/api/observations", ({ request }) => {
    const q = new URL(request.url).searchParams;
    const classId = Number(q.get("class_id"));
    return HttpResponse.json({ items: classId ? recordsFor(classId) : [] });
  }),
  http.get("*/api/documents", ({ request }) => {
    const q = new URL(request.url).searchParams;
    const items = documents
      .filter((d) => !q.get("kind") || d.kind === q.get("kind"))
      .filter((d) => !q.get("class_id") || d.class_id === Number(q.get("class_id")))
      .filter((d) => !q.get("status") || d.status === q.get("status"))
      .filter((d) => !q.get("stale") || String(d.stale) === q.get("stale"))
      .toReversed();
    return HttpResponse.json({ items: items.map(summary) });
  }),
  http.get("*/api/documents/export/bundle", () =>
    HttpResponse.arrayBuffer(new Uint8Array([80, 75, 5, 6, ...new Array(18).fill(0)]).buffer, {
      headers: {
        "Content-Type": "application/zip",
        "Content-Disposition": `attachment; filename="documents.zip"; filename*=UTF-8''${encodeURIComponent("일지 묶음.zip")}`,
      },
    }),
  ),
  http.get("*/api/documents/:id", ({ params }) => {
    const d = find(params.id);
    return d ? HttpResponse.json(detail(d)) : missing();
  }),
  http.post("*/api/documents", async ({ request }) => {
    const b = (await request.json()) as Json;
    const records = recordsFor(Number(b.class_id));
    const same = documents.find(
      (d) =>
        d.child_id === b.child_id && d.start === b.start && d.end === b.end && d.status === "DRAFT",
    );
    if (same && !b.replace_draft) return HttpResponse.json(detail(same));
    if (same) documents.splice(documents.indexOf(same), 1);
    const picked = (b.source_ids as number[]).map((id) => records.find((r) => r.id === id)!);
    const child = listChildren(Number(b.class_id)).find((c) => c.id === b.child_id);
    const ids = picked.map((r) => r.id as number);
    const order = listChildren(Number(b.class_id)).findIndex((c) => c.id === b.child_id);
    await new Promise((r) => setTimeout(r, 600));
    const interpretation = `친구에게 먼저 말을 건네며 매일 놀이를 넓혀 간다. 함께 만드는 즐거움을 경험한다.`;
    const doc: Doc = {
      id: next++,
      kind: "observation",
      title: `${child?.name ?? ""} 관찰일지`,
      class_id: Number(b.class_id),
      class_name: findClass(Number(b.class_id))?.name ?? "",
      child_id: Number(b.child_id),
      child_name: child?.name ?? "",
      start: String(b.start),
      end: String(b.end),
      status: "DRAFT",
      origin: "AI",
      stale: false,
      sections: [
        { heading: "사실", body: picked.map((r) => r.fact).join("\n\n"), source_ids: ids },
        { heading: "해석", body: interpretation, source_ids: ids },
        {
          heading: "지원",
          body: "다음 쌓기 놀이에서 블록을 더 놓아 주면 좋을 것 같다.",
          source_ids: ids,
        },
      ],
      sources: picked.map((r) => ({
        id: r.id,
        source_kind: "observation",
        date: r.date,
        domain: r.domain,
        context: r.context,
        text: r.fact,
        class_id: r.class_id,
        child_id: r.child_id,
      })),
      ai_review:
        order === 2
          ? { state: "failed", issues: [], message: "AI 검토를 하지 못했어요. 다시 검토해 주세요." }
          : { state: "done", issues: flagged(interpretation), message: "" },
      created_at: now(),
      updated_at: now(),
    };
    documents.push(doc);
    return HttpResponse.json(detail(doc), { status: 201 });
  }),
  http.put("*/api/documents/:id", async ({ params, request }) => {
    const d = find(params.id);
    if (!d) return missing();
    const b = (await request.json()) as Json;
    d.sections = b.sections as Doc["sections"];
    d.updated_at = now();
    if (d.ai_review && flagged(body(d, "해석")).length !== d.ai_review.issues.length)
      d.ai_review = null;
    return HttpResponse.json(detail(d));
  }),
  http.post("*/api/documents/:id/verify", async ({ params, request }) => {
    const d = find(params.id);
    if (!d) return missing();
    const b = (await request.json()) as { sections?: Doc["sections"] };
    const text = b.sections?.find((s) => s.heading === "해석")?.body ?? body(d, "해석");
    const issues = flagged(text);
    d.ai_review = { state: "done", issues, message: "" };
    return HttpResponse.json({ issues, judge: "jev" });
  }),
  http.post("*/api/documents/:id/rewrite", async ({ request }) => {
    const b = (await request.json()) as { sentence: string; style: string };
    await new Promise((r) => setTimeout(r, 400));
    const sentence =
      b.style === "shorter"
        ? b.sentence.replace("매일 ", "").replace(/며 .*$/, "며 놀이를 넓혀 간다.")
        : b.style === "concrete"
          ? "다음 쌓기 놀이에서 블록 바구니를 두 개 놓고 함께 쌓는 순서를 정해 보게 하겠다."
          : b.sentence.replace("매일 ", "");
    return HttpResponse.json({ sentence, blocked: [], issues: [], judge: "jev" });
  }),
  http.post("*/api/documents/:id/confirm", ({ params }) => {
    const d = find(params.id);
    if (!d) return missing();
    d.status = "CONFIRMED";
    d.updated_at = now();
    return HttpResponse.json(detail(d));
  }),
  http.post("*/api/documents/:id/unconfirm", ({ params }) => {
    const d = find(params.id);
    if (!d) return missing();
    d.status = "DRAFT";
    d.updated_at = now();
    return HttpResponse.json(detail(d));
  }),
  http.delete("*/api/documents/:id", ({ params }) => {
    const d = find(params.id);
    if (d) documents.splice(documents.indexOf(d), 1);
    return new HttpResponse(null, { status: 204 });
  }),
];
