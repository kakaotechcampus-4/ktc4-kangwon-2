export const DOCUMENT_KINDS = {
  annual: "연간 보육계획안", monthly: "월간 보육계획안", weekly: "주간 보육계획안", daily: "일간 보육계획안",
  dailyLog: "일일 보육일지", weeklyLog: "주간 보육일지", observation: "관찰일지", assessment: "영유아 평가",
} as const;
export type DocumentKind = keyof typeof DOCUMENT_KINDS;
export type Observation = { id: string; classId: string; className: string; childId: string; childName: string; date: string; domain: string; context: string; fact: string; createdAt: string };
export type Source = { id: string; date: string; text: string; childId: string; classId: string };
export type Section = { heading: string; body: string; sourceIds: string[] };
export type SavedDocument = {
 annualPlanId?:number;
 annualApiSource?:string;
  id: string; title: string; kind: DocumentKind; classId: string; className: string; childId: string; childName: string;
  start: string; end: string; sections: Section[]; sources: Source[]; status: "draft" | "confirmed";
  origin: "teacher" | "ai" | "template" | "import"; createdAt: string; updatedAt: string; reviewNote: string;
};
export type Template = { id: string; name: string; text: string; headings: string[]; style: string; summary: string; createdAt: string };
export type Criterion = { id: string; label: string; terms: string; source: string };
export type Workspace = { version: 1; observations: Observation[]; documents: SavedDocument[]; templates: Template[]; criteria: Criterion[] };
export const EMPTY_WORKSPACE: Workspace = { version: 1, observations: [], documents: [], templates: [], criteria: [] };
export const DOMAINS = ["신체운동·건강", "의사소통", "사회관계", "예술경험", "자연탐구"];
export function today() { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`; }
export function validDate(value: string) { return /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value)) && new Date(value).toISOString().slice(0,10) === value; }
export function validPeriod(start: string, end: string) { return validDate(start) && validDate(end) && start <= end; }
export function validateDocument(doc: Pick<SavedDocument, "sections" | "sources" | "start" | "end" | "kind" | "classId" | "childId" | "origin">): string[] {
  const issues: string[] = [];
  if (!validPeriod(doc.start, doc.end)) issues.push("작성 기간을 확인해주세요.");
  if (!doc.classId) issues.push("담당 반을 지정해주세요.");
  if ((doc.kind === "observation" || doc.kind === "assessment") && !doc.childId) issues.push("아동별 문서에는 대상 아동을 지정해주세요.");
  if (doc.kind === "dailyLog" && doc.start !== doc.end) issues.push("일일 보육일지의 시작일과 종료일은 같아야 해요.");
  if (doc.sections.length === 0 || doc.sections.some(s => !s.body.trim())) issues.push("비어 있는 문서 항목을 작성해주세요.");
  if (doc.origin === "import") {
    if (doc.sources.length || doc.sections.length !== 1 || doc.sections[0]?.heading !== "첨부 원문") issues.push("등록 증빙의 원문 구조를 확인해주세요.");
    return issues;
  }
  if (!["dailyLog", "weeklyLog", "observation", "assessment"].includes(doc.kind)) return issues;
  if (!doc.sources.length) issues.push("교사가 입력한 원본 기록이 필요해요.");
  if (new Set(doc.sources.map(s=>s.id)).size !== doc.sources.length) issues.push("같은 원본 기록이 중복 연결되었어요.");
  if (doc.sources.some(s=>!s.text.trim() || s.classId!==doc.classId || (!!doc.childId && s.childId!==doc.childId))) issues.push("문서와 원본의 반·아동 또는 관찰 내용을 확인해주세요.");
  const facts = doc.sections.filter(s => s.heading === "사실");
  const expectedFacts = doc.sources.map(s => s.text).join("\n\n");
  if (facts.length !== 1 || facts[0].body !== expectedFacts) issues.push("사실은 선택한 원본 기록과 정확히 일치해야 해요.");
  if(facts.length===1 && (facts[0].sourceIds.length!==doc.sources.length||new Set(facts[0].sourceIds).size!==doc.sources.length||facts[0].sourceIds.some(id=>!doc.sources.some(s=>s.id===id))))issues.push("사실 항목의 근거 기록 연결을 확인해주세요.");
  if (doc.sources.some(s => !validDate(s.date) || s.date < doc.start || s.date > doc.end)) issues.push("원본 기록의 날짜가 작성 기간 밖에 있어요.");
  const sourceIds = new Set(doc.sources.map(s => s.id));
  for (const heading of ["해석", "지원"]) {
    if (doc.sections.filter(s=>s.heading===heading).length > 1) issues.push(`${heading} 항목이 중복되었어요.`);
    const section = doc.sections.find(s => s.heading === heading);
    if (!section?.body.trim()) { issues.push(`${heading} 내용을 작성해주세요.`); continue; }
    if (!section.sourceIds.length || section.sourceIds.some(id => !sourceIds.has(id))) issues.push(`${heading}의 근거 기록을 연결해주세요.`);
    if (section.body.trim().length < 20 || /^(잘|적절히|지속적으로)?\s*(지원|지도|관찰)(하겠|한|합|할|해)/.test(section.body.trim())) issues.push(`${heading}을 구체적으로 작성해주세요. 활동·방법·후속 관찰 내용을 포함해주세요.`);
  }
  if(doc.sections.some(s=>!["사실","해석","지원"].includes(s.heading))) issues.push("기록 문서는 사실·해석·지원 항목으로 작성해주세요.");
  return issues;
}

export function assertDocumentUnchanged(latest: SavedDocument | undefined, expected: SavedDocument) {
  if (!latest || JSON.stringify(latest) !== JSON.stringify(expected)) throw new Error("다른 작업에서 문서가 변경되었어요. 최신 문서를 불러온 뒤 다시 수정해주세요.");
}
export function isObject(value: unknown): value is Record<string,unknown> { return value !== null && typeof value === "object" && !Array.isArray(value); }
export function hasStrings(value: Record<string,unknown>, keys: string[]) { return keys.every(key=>typeof value[key] === "string"); }
export function isSource(value: unknown): value is Source { return isObject(value) && hasStrings(value,["id","date","text","classId","childId"]) && !!value.id && validDate(value.date as string); }
export function isSection(value: unknown): value is Section { return isObject(value) && hasStrings(value,["heading","body"]) && Array.isArray(value.sourceIds) && value.sourceIds.every(id=>typeof id==="string"); }
export function isSavedDocument(value: unknown): value is SavedDocument {
  return isObject(value) && hasStrings(value,["id","title","kind","classId","className","childId","childName","start","end","status","origin","createdAt","updatedAt","reviewNote"])
    && !!value.id && Object.hasOwn(DOCUMENT_KINDS,value.kind as string) && ["draft","confirmed"].includes(value.status as string) && ["ai","teacher","template","import"].includes(value.origin as string)
    && validPeriod(value.start as string,value.end as string) && Array.isArray(value.sources) && value.sources.every(isSource) && Array.isArray(value.sections) && value.sections.every(isSection);
}

export function compareEvidence(doc: SavedDocument, documents: SavedDocument[], observations: Observation[]) {
  const matches = documents.filter(other => other.id !== doc.id && other.status === "confirmed" && other.classId === doc.classId && (!doc.childId || other.childId === doc.childId || !other.childId) && other.start <= doc.end && other.end >= doc.start);
  const linked = doc.sources.map(source => {
    const observation = observations.find(r => r.id === source.id);
    const document = documents.find(d => d.id === source.id);
    if (!observation && !document) return { source, state: "원본 없음" };
    if (observation && (observation.fact !== source.text || observation.date !== source.date || observation.classId !== source.classId || observation.childId !== source.childId)) return { source, state: "원본 변경 · 재검토" };
    if (document && (document.status !== "confirmed" || document.sections.filter(s=>s.heading==="사실").map(s=>s.body).join("\n\n") !== source.text || document.classId!==source.classId || document.childId!==source.childId || document.start!==source.date)) return { source, state: "문서 변경 · 재검토" };
    return { source, state: "일치" };
  });
  const required: DocumentKind[] = doc.kind === "weeklyLog" ? ["dailyLog"] : doc.kind === "assessment" ? ["observation", "dailyLog"] : ["dailyLog", "observation"];
  return { matches, linked, required: required.map(kind => ({ kind, documents: matches.filter(d => d.kind === kind) })) };
}

export function invalidateDependents(documents: SavedDocument[], changedId: string): SavedDocument[] {
  const affected = new Set([changedId]);
  let added = true;
  while (added) { added = false; for (const doc of documents) if (!affected.has(doc.id) && doc.sources.some(s=>affected.has(s.id))) { affected.add(doc.id); added = true; } }
  return documents.map(doc=>doc.id!==changedId && affected.has(doc.id) ? {...doc,status:"draft",reviewNote:"원본 또는 근거 문서 변경 · 다시 생성하고 검토해주세요."} : doc);
}

export function analyzeText(text: string) {
  const clean = text.replace(/\r/g, "").trim();
  const lines = clean.split("\n").map(l => l.trim()).filter(Boolean);
  const headings = [...new Set(lines.filter(l => l.length <= 45 && (/[:：]$|^\d+[.)]|^#+|계획|목표|활동|평가|지원|관찰|일시|대상|준비물|주제|내용/.test(l))).map(l => l.replace(/^#+\s*/, "").replace(/[:：]$/, "")))].slice(0, 20);
  return { headings: headings.length ? headings : ["내용"], style: /[│|\t]/.test(clean) ? "표·항목 중심" : lines.filter(l => /[다요]\.?$/.test(l)).length > 2 ? "서술형 기록 중심" : "짧은 항목 중심", summary: `${lines.length}개 문단 · ${clean.length.toLocaleString()}자. ${headings.length}개의 제목 후보를 찾았어요. 적용 전 항목명을 확인해주세요.` };
}

export function downloadText(name: string, text: string) {
  const url = URL.createObjectURL(new Blob(["\uFEFF", text], { type: "text/plain;charset=utf-8" }));
  const a = document.createElement("a"); a.href = url; a.download = name.replace(/[<>:"/\\|?*]/g, "_") + ".txt"; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
