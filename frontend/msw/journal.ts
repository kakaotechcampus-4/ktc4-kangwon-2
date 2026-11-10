/**
 * 보육일지 하루 화면 목업 — 일과 기록 · 날씨 · 임시본 · 반 기본 일과표 (api-spec §10-1, ADR-089 · 084 · 085).
 *
 * 줄 · 임시본은 이 탭이 열려 있는 동안만 남는다.
 *
 * **보여 주기용 자료(`msw.demo=journal`)** — sessionStorage 에 그 값이 있을 때만 그날 관찰 · 어제 확정 일지 ·
 * 주간계획안 · 지난주 같은 요일 깔 줄이 나온다. 평소 목업은 전처럼 비어 있다. 이름은 지어낸 가명이다.
 */
import { http, HttpResponse } from "msw";
import type { DayWeather, DraftRow, RoutineDayDraft, Sky, TemplateRow } from "../lib/api/routines";

const MOCK_SKIES = ["맑음", "구름많음", "흐림", "비", "눈", "비나 눈"];
const weatherChoice = new Map<string, string>();
const drafts = new Map<string, RoutineDayDraft>();
const templates = new Map<number, TemplateRow[]>();
interface MockRoutine {
  id: number;
  class_id: number;
  class_name: string;
  date: string;
  position: number;
  start: string | null;
  end: string | null;
  name: string;
  plan: string;
  execution: string;
  reflected: boolean;
  activities: string[];
  created_at: string;
}
let routines: MockRoutine[] = [];
let nextId = 7000;

const demo = () =>
  typeof sessionStorage !== "undefined" &&
  (sessionStorage.getItem("msw.demo") ?? "").startsWith("journal");
/** `journal-noweekly` — 주간 일지를 아직 안 만든 주를 보여 준다. */
const noWeekly = () => sessionStorage.getItem("msw.demo") === "journal-noweekly";

// 그날 날씨 목업 (ADR-089). 자동 값은 비 · 보통 — 대체놀이 칩이 뜨는 쪽을 보여 준다.
function mockWeather(date: string, chosen?: string): DayWeather {
  const sky = (chosen ?? "비") as Sky;
  return {
    date,
    sky,
    dust: demo() ? "나쁨" : "보통",
    source: chosen ? "teacher" : "auto",
    indoor_hint: ["비", "눈", "비나 눈"].includes(sky) ? "rain" : null,
  };
}

const shift = (date: string, days: number) => {
  const at = new Date(`${date}T00:00:00Z`);
  at.setUTCDate(at.getUTCDate() + days);
  return at.toISOString().slice(0, 10);
};
const time = (v: string | null) => (v && v.length === 5 ? `${v}:00` : v);
const ofDay = (classId: number, date: string) =>
  routines
    .filter((r) => r.class_id === classId && r.date === date)
    .sort((a, b) => a.position - b.position || a.id - b.id);
const filled = (r: DraftRow) =>
  (r.touched || r.id !== null) &&
  Boolean(r.start || r.end || r.name.trim() || r.plan.trim() || r.execution.trim());

function preset(classId: number, date: string) {
  const template = templates.get(classId);
  const weekday = (new Date(`${date}T00:00:00Z`).getUTCDay() + 6) % 7;
  if (template?.length)
    return {
      source: "template",
      from_date: null,
      rows: template
        .filter((r) => r.weekday == null || r.weekday === weekday)
        .map((r) => ({ name: r.name, start: time(r.start), end: time(r.end) })),
    };
  if (!demo()) return null;
  return {
    source: "last_week",
    from_date: shift(date, -7),
    rows: [
      ["등원 및 통합보육", "07:30", "09:00"],
      ["오전 실내놀이", "09:20", "10:40"],
      ["활동", "10:40", "11:00"],
      ["바깥놀이", "11:00", "12:20"],
      ["점심식사", "12:20", "13:20"],
      ["특별활동(체육)", "15:40", "16:00"],
    ].map(([name, start, end]) => ({ name, start: `${start}:00`, end: `${end}:00` })),
  };
}

const bad = (field: string) =>
  HttpResponse.json(
    { error: { code: "VALIDATION_FAILED", message: "입력값을 확인해주세요.", fields: [field] } },
    { status: 422 },
  );

/** 보여 주기용 — 어제 확정 일지 · 이번 주 주간 초안 · 오늘 일일 초안. */
function demoDocuments(classId: number, today: string) {
  const doc = (id: number, kind: string, start: string, end: string, status: string) => ({
    id,
    kind,
    title: kind === "dailyLog" ? `햇살반 보육일지 (${start})` : "햇살반 주간 보육일지",
    class_id: classId,
    class_name: "햇살반",
    child_id: null,
    child_name: null,
    start,
    end,
    status,
    origin: "AI",
    stale: false,
    generation: { method: "RULE_LLM", rule_id: "draft", rule_version: "v1" },
    sources_count: 1,
    created_at: `${start}T08:00:00Z`,
    updated_at: `${start}T08:00:00Z`,
  });
  const monday = shift(today, -((new Date(`${today}T00:00:00Z`).getUTCDay() + 6) % 7));
  return [
    doc(9101, "dailyLog", shift(today, -1), shift(today, -1), "CONFIRMED"),
    // 주간 일지가 없는 주를 보일 때는 오늘 일일 초안 하나 — 「여기서 확정」을 보여 준다.
    ...(noWeekly() ? [doc(9102, "dailyLog", today, today, "DRAFT")] : []),
    ...made.map((m) => doc(m.id, "dailyLog", m.start, m.start, m.status)),
    ...(noWeekly() ? [] : [doc(9201, "weeklyLog", monday, shift(monday, 6), "DRAFT")]),
  ];
}
/**
 * 문서 보관함은 반을 빼고 문서를 다 묻는다(`listDocuments()`). 그때 반 번호 0 으로 만들면
 * 보관함이 제 반 문서가 아니라고 걸러 날짜 칸이 다 비었다 — 마지막으로 본 반 번호를 쓴다.
 */
let seenClass = 0;
/** 보여 주기 중에 「오늘 일지 만들기」로 만든 초안. 근거는 그날 일과 기록 사본이다 (§11). */
interface MadeDaily {
  id: number;
  start: string;
  status: "DRAFT" | "CONFIRMED";
  classNote: string;
  sourceIds: number[];
  sources: {
    id: number;
    source_kind: "routine";
    date: string;
    text: string;
    class_id: number;
    child_id: null;
  }[];
}
const made: MadeDaily[] = [];
const DEMO_SECTIONS: Record<number, [string, string][]> = {
  // 사실은 서버처럼 일과마다 빈 줄로 잇는다(join_facts). 한 일과 안에서 교사가 줄을 바꾼 것도 있다.
  9101: [
    [
      "사실",
      "[등원 및 자유놀이 09:00~09:30] 친구에게 같이 만들자고 말하며 블록을 나눠 주었다.\n" +
        "블록 세 개를 쌓은 뒤 “더 높이 만들래”라고 말했다.\n\n" +
        "[바깥놀이 10:40~11:40] 모래에 물길을 파고 물이 어디로 가는지 따라가며 보았다.\n\n" +
        "[점심 및 휴식 11:40~13:00] 숟가락을 스스로 들고 먹은 뒤 그릇을 정리대에 가져다 놓았다.",
    ],
    ["해석", "모래와 물이 만나는 곳에 관심을 보이며 둑의 높이를 서로 견주었다."],
    ["지원", "모래놀이에 물길 재료를 더 준비한다."],
  ],
  9102: [
    ["사실", "[오전 실내놀이 09:20~10:40] 블록으로 다리를 만들었다."],
    ["해석", "블록을 길게 이으며 무게를 나누는 방법을 시험했다."],
    ["지원", "긴 블록과 받침을 함께 둔다."],
  ],
  9201: [
    ["사실", "[바깥놀이] 모래 놀이터에서 둑을 쌓았다."],
    ["해석", ""],
    ["지원", ""],
  ],
};

/** 보여 주기용 — 그날이 든 주의 주간계획안. 대·소집단 활동 · 특별활동은 요일 칸이다(ADR-051). */
function demoPlan(classId: number, today: string) {
  const monday = shift(today, -((new Date(`${today}T00:00:00Z`).getUTCDay() + 6) % 7));
  const days = ["MON", "TUE", "WED", "THU", "FRI"];
  const group = ["낙엽 모자이크", "솔방울 굴리기", "가을 소리 찾기", "낙엽 왕관", "도토리 세기"];
  const cell = (item_id: string, value: string, day: string | null) => ({
    item_id,
    value,
    day,
    state: "FILLED",
    evidence: [],
    generation: null,
    parent_snapshots: [],
    teacher_input: false,
  });
  return {
    id: 9001,
    class_id: classId,
    school_year: Number(today.slice(0, 4)),
    week_id: `${today.slice(0, 7)}-W2`,
    target_month: today.slice(0, 7),
    status: "CONFIRMED",
    revision: 1,
    week_period: { label: "", start_date: monday, end_date: shift(monday, 4) },
    operating_days: days,
    display_end_date: shift(monday, 4),
    sections: [
      {
        section_key: "group_activity",
        label: "대·소집단 활동",
        role: "",
        visible: true,
        order: 1,
        semantic_variant: null,
        repeat_by: "DAY",
        cells: days.map((d, i) => cell(`g${i}`, group[i], d)),
      },
      {
        section_key: "special_program",
        label: "특별활동",
        role: "",
        visible: true,
        order: 2,
        semantic_variant: null,
        repeat_by: "DAY",
        cells: days.map((d, i) => cell(`s${i}`, i % 2 ? "" : "체육", d)),
      },
      {
        section_key: "indoor_play",
        label: "실내 자유놀이",
        role: "",
        visible: true,
        order: 3,
        semantic_variant: null,
        repeat_by: "NONE",
        cells: [cell("i1", "쌓기: 낙엽 길 만들기", null), cell("i2", "미술: 나뭇잎 찍기", null)],
      },
    ],
  };
}

const today = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

const madeDaily = (id: string | readonly string[] | undefined) =>
  demo() ? made.find((m) => m.id === Number(id)) : undefined;
/** 보여 주기 문서 상세. 오늘 만든 초안은 근거 사본 · 반 특이사항을 들고 있다. */
function dailyDetail(id: number) {
  const m = made.find((d) => d.id === id);
  const summary = demoDocuments(seenClass, today()).find((d) => d.id === id)!;
  const ids = m?.sourceIds ?? [];
  return {
    ...summary,
    sources_count: ids.length,
    sections: DEMO_SECTIONS[id].map(([heading, body]) => ({
      heading,
      body,
      source_ids: heading === "사실" ? ids : [],
    })),
    sources: m?.sources ?? [],
    review_note: "",
    class_note: m?.classNote ?? "",
  };
}

export const journalHandlers = [
  http.get("*/api/routines", ({ request }) => {
    const q = new URL(request.url).searchParams;
    const classId = Number(q.get("class_id"));
    if (classId) seenClass = classId;
    const day = q.get("from");
    const oneDay = q.get("class_id") && day && day === q.get("to");
    if (!oneDay)
      return HttpResponse.json({
        items: routines.filter(
          (r) =>
            (!q.get("class_id") || r.class_id === classId) &&
            (!day || r.date >= day) &&
            (!q.get("to") || r.date <= q.get("to")!),
        ),
        weather: null,
        draft: null,
        preset: null,
      });
    const items = ofDay(classId, day);
    return HttpResponse.json({
      items,
      weather: mockWeather(day, weatherChoice.get(`${classId}|${day}`)),
      draft: drafts.get(`${classId}|${day}`) ?? null,
      preset: items.length ? null : preset(classId, day),
    });
  }),
  http.put("*/api/routines/weather", async ({ request }) => {
    const b = (await request.json()) as { class_id: number; date: string; sky: string | null };
    if (b.sky !== null && !MOCK_SKIES.includes(b.sky)) return bad("sky");
    const key = `${b.class_id}|${b.date}`;
    if (b.sky === null) weatherChoice.delete(key);
    else weatherChoice.set(key, b.sky);
    return HttpResponse.json(mockWeather(b.date, weatherChoice.get(key)));
  }),
  http.put("*/api/routines/draft", async ({ request }) => {
    const b = (await request.json()) as {
      class_id: number;
      date: string;
      expected_revision: number;
      rows: DraftRow[];
      removed: number[];
      promote: boolean;
    };
    const key = `${b.class_id}|${b.date}`;
    const before = drafts.get(key);
    if ((before?.revision ?? 0) !== b.expected_revision)
      return HttpResponse.json(
        {
          error: {
            code: "STALE_WRITE",
            message: "다른 화면에서 먼저 고쳤습니다. 다시 불러와 주세요.",
            fields: ["expected_revision"],
          },
        },
        { status: 409 },
      );
    const rows = b.rows.map((r) => ({ ...r }));
    if (b.promote) {
      if (rows.some((r) => filled(r) && !r.name.trim())) return bad("rows");
      routines = routines.filter((r) => !b.removed.includes(r.id));
      let position = 0;
      rows.forEach((r, i) => {
        if (!filled(r)) return;
        const values = {
          class_id: b.class_id,
          class_name: "햇살반",
          date: b.date,
          position: position++,
          start: time(r.start),
          end: time(r.end),
          name: r.name,
          plan: r.plan,
          execution: r.execution,
          reflected: r.reflected,
          activities: r.activities,
          created_at: new Date().toISOString(),
        };
        const found = routines.find((x) => x.id === r.id);
        if (found) Object.assign(found, values);
        else {
          rows[i] = { ...r, id: (nextId += 1) };
          routines.push({ ...values, id: nextId });
        }
      });
    }
    const draft: RoutineDayDraft = {
      class_id: b.class_id,
      date: b.date,
      revision: (before?.revision ?? 0) + 1,
      rows,
      removed: b.promote ? [] : b.removed,
      promoted: b.promote,
      updated_at: new Date().toISOString(),
    };
    drafts.set(key, draft);
    return HttpResponse.json({
      draft,
      items: b.promote ? ofDay(b.class_id, b.date) : null,
      review_impact: b.promote ? { affected_document_ids: [], newly_stale_document_ids: [] } : null,
    });
  }),
  http.get("*/api/routines/template", ({ request }) => {
    const classId = Number(new URL(request.url).searchParams.get("class_id"));
    const rows = templates.get(classId);
    return HttpResponse.json(rows ? { class_id: classId, rows, updated_at: "" } : null);
  }),
  http.put("*/api/routines/template", async ({ request }) => {
    const b = (await request.json()) as { class_id: number; rows: TemplateRow[] };
    if (b.rows.some((r) => !r.name?.trim())) return bad("rows");
    templates.set(b.class_id, b.rows);
    return HttpResponse.json({ class_id: b.class_id, rows: b.rows, updated_at: "" });
  }),

  // ── 보여 주기용 자료 — `msw.demo=journal` 일 때만. 아니면 다음 목업으로 넘긴다. ──
  http.get("*/api/observations", ({ request }) => {
    if (!demo()) return;
    const q = new URL(request.url).searchParams;
    const classId = Number(q.get("class_id"));
    const date = q.get("from") ?? today();
    const observation = (id: number, child: string, context: string, fact: string) => ({
      id,
      class_id: classId,
      class_name: "햇살반",
      child_id: id,
      child_name: child,
      child_code: "가나다",
      date,
      domain: "사회관계",
      context,
      fact,
      created_at: `${date}T01:00:00Z`,
    });
    return HttpResponse.json({
      items: [
        observation(
          81,
          "김가람",
          "실내놀이, 쌓기",
          "가람이가 블록 셋을 쌓고 나래에게 같이 만들자고 함",
        ),
        observation(82, "박솔", "실내놀이, 쌓기", "솔이가 블록 색을 번갈아 고름"),
      ],
    });
  }),
  http.get("*/api/documents", ({ request }) => {
    if (!demo()) return;
    const q = new URL(request.url).searchParams;
    const items = demoDocuments(Number(q.get("class_id")) || seenClass, today()).filter(
      (d) => !q.get("kind") || d.kind === q.get("kind"),
    );
    return HttpResponse.json({ items });
  }),
  http.post("*/api/documents", async ({ request }) => {
    if (!demo()) return;
    const b = (await request.json()) as {
      kind: string;
      class_id: number;
      start: string;
      source_ids: number[];
    };
    if (b.kind !== "dailyLog") return;
    const id = 9300 + made.length;
    // 서버와 같은 사실 한 줄 — `[오전 실내놀이 09:20~10:40] 활동실행` (routines/models.py fact_text).
    const picked = b.source_ids
      .map((sid) => routines.find((r) => r.id === sid))
      .filter((r): r is MockRoutine => !!r);
    const line = (r: MockRoutine) => {
      const hm = (v: string | null) => (v ?? "").slice(0, 5);
      const when = r.start || r.end ? ` ${hm(r.start)}~${hm(r.end)}` : "";
      return `[${r.name.trim()}${when}] ${r.execution.trim()}`;
    };
    made.push({
      id,
      start: b.start,
      status: "DRAFT",
      classNote: "",
      sourceIds: picked.map((r) => r.id),
      sources: picked.map((r) => ({
        id: r.id,
        source_kind: "routine",
        date: r.date,
        text: line(r),
        class_id: r.class_id,
        child_id: null,
      })),
    });
    DEMO_SECTIONS[id] = [
      [
        "사실",
        picked.length ? picked.map(line).join("\n") : "[오전 실내놀이 09:20~10:40] 블록 놀이",
      ],
      [
        "해석",
        "친구와 함께 만들기를 제안하며 놀이를 넓혔다. 아이들은 매일 블록으로 길을 이어 간다.",
      ],
      ["지원", "큰 블록을 더 두어 함께 쌓을 자리를 만든다."],
    ];
    return HttpResponse.json(dailyDetail(id), { status: 201 });
  }),
  http.get("*/api/documents/:id", ({ params }) => {
    const id = Number(params.id);
    if (!demo() || !DEMO_SECTIONS[id]) return;
    return HttpResponse.json(dailyDetail(id));
  }),
  http.put("*/api/documents/:id", async ({ params, request }) => {
    const m = madeDaily(params.id);
    if (!m) return;
    const b = (await request.json()) as {
      sections: { heading: string; body: string }[];
      class_note?: string;
    };
    DEMO_SECTIONS[m.id] = b.sections.map((s) => [s.heading, s.body]);
    m.classNote = b.class_note ?? m.classNote;
    return HttpResponse.json(dailyDetail(m.id));
  }),
  // 3단 검토 흉내 — 「매일」처럼 기록에 없는 말을 짚는다(관찰일지 목업과 같은 규칙).
  http.post("*/api/documents/:id/verify", async ({ params, request }) => {
    const m = madeDaily(params.id);
    if (!m) return;
    const b = (await request.json()) as { sections: { heading: string; body: string }[] };
    await new Promise((r) => setTimeout(r, 500));
    const issues = b.sections
      .filter((s) => s.heading === "해석" || s.heading === "지원")
      .flatMap((s) =>
        s.body
          .split(/(?<=[.!?])\s+/)
          .filter((sentence) => sentence.includes("매일"))
          .map((sentence) => ({
            heading: s.heading,
            sentence,
            code: "UNSUPPORTED_FACT",
            source_id: null,
            source_text: null,
            reason: "「매일」은 오늘 일과 기록에 없어요.",
            fix: "오늘 본 것만 적어 주세요.",
          })),
      );
    return HttpResponse.json({ issues, judge: "jev" });
  }),
  http.post("*/api/documents/:id/confirm", ({ params }) => {
    const m = madeDaily(params.id);
    if (!m) return;
    m.status = "CONFIRMED";
    return HttpResponse.json(dailyDetail(m.id));
  }),
  http.post("*/api/documents/:id/unconfirm", ({ params }) => {
    const m = madeDaily(params.id);
    if (!m) return;
    m.status = "DRAFT";
    return HttpResponse.json({
      ...dailyDetail(m.id),
      review_impact: { affected_document_ids: [], newly_stale_document_ids: [] },
    });
  }),
  http.delete("*/api/documents/:id", ({ params }) => {
    const m = madeDaily(params.id);
    if (!m) return;
    made.splice(made.indexOf(m), 1);
    delete DEMO_SECTIONS[m.id];
    return new HttpResponse(null, { status: 204 });
  }),
  http.get("*/api/plans/weekly", ({ request }) => {
    if (!demo()) return;
    const classId = Number(new URL(request.url).searchParams.get("class_id"));
    const { sections, ...summary } = demoPlan(classId, today());
    void sections;
    return HttpResponse.json({ items: [summary] });
  }),
  http.get("*/api/plans/weekly/:id", ({ params }) => {
    if (!demo() || Number(params.id) !== 9001) return;
    return HttpResponse.json(demoPlan(0, today()));
  }),
];
