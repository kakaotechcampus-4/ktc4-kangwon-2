/** 일지 계열 문서 API (docs/api-spec.md §11). id 변환을 여기서 끝내고 화면에는 화면 id 만 준다. */
import { apiRequest, errorCode } from "./client";
import { downloadHwpx, type ExportFormat } from "./export";
import {
  CLASS_PREFIX,
  CHILD_PREFIX,
  classLocalId,
  childLocalId,
  classServerId,
  childServerId,
} from "./onboarding";
import { observationLocalId, observationServerId } from "./observations";
import { routineLocalId, routineServerId } from "./routines";
import type { DocumentKind, SavedDocument, Section, Source } from "../workspace/model";

/** 서버가 다루는 네 종류. 계획안(annual·monthly·weekly·daily)은 이 API 가 아니다. */
export const RECORD_KINDS = ["dailyLog", "weeklyLog", "observation", "assessment"] as const;
export type RecordKind = (typeof RECORD_KINDS)[number];
export const isRecordKind = (kind: string): kind is RecordKind =>
  (RECORD_KINDS as readonly string[]).includes(kind);

// 서버 id 는 테이블마다 1 부터 센다. 화면 id 와 섞이지 않게 접두사를 붙인다.
const DOCUMENT_PREFIX = "document:";
// 접두사는 onboarding.ts 가 정한다 — 세 군데서 따로 들면 어긋나는 순간 id 가 갈린다.
// 안전한 양의 정수 id 만 받는다.
const SERVER_ID = /^[1-9][0-9]*$/;

export const documentLocalId = (serverId: number) => DOCUMENT_PREFIX + serverId;

/** 화면 id 에서 서버 id 를 되찾는다. 서버에서 온 id 가 아니면 `null`. */
export function documentServerId(localId: string): number | null {
  if (!localId.startsWith(DOCUMENT_PREFIX)) return null;
  const raw = localId.slice(DOCUMENT_PREFIX.length);
  if (!SERVER_ID.test(raw)) return null;
  const id = Number(raw);
  return Number.isSafeInteger(id) ? id : null;
}

type SourceKind = NonNullable<Source["kind"]>;
const SOURCE_KINDS: readonly SourceKind[] = ["observation", "document", "routine"];
/**
 * 근거 id 가 가리키는 것은 종류마다 다르다 (§11).
 * 서버가 `source_kind` 를 주면 그것을 따른다 — 주간 보육일지는 일일 문서이거나 일과 기록이다.
 * 안 주는 서버(옛 응답)면 문서 종류로 짐작한다: 주간은 문서, 일일은 일과 기록(ADR-025),
 * 나머지는 관찰 기록.
 */
function sourceKindOf(docKind: string, given?: string | null): SourceKind {
  if (given && (SOURCE_KINDS as readonly string[]).includes(given)) return given as SourceKind;
  if (docKind === "weeklyLog") return "document";
  if (docKind === "dailyLog") return "routine";
  return "observation";
}
function sourceLocalId(kind: SourceKind, id: number) {
  if (kind === "document") return documentLocalId(id);
  if (kind === "routine") return routineLocalId(id);
  return observationLocalId(id);
}
function sourceServerId(kind: string, localId: string) {
  // 주간은 근거가 두 종류다. 화면 id 의 접두사가 종류를 들고 있다.
  if (kind === "weeklyLog") return documentServerId(localId) ?? routineServerId(localId);
  if (kind === "dailyLog") return routineServerId(localId);
  return observationServerId(localId);
}

export interface ApiDocumentGeneration {
  method: string | null;
  rule_id: string | null;
  rule_version: string | null;
  /** 초안을 못 만들어 사실만 채운 초안이다 (ADR-093). 해석 · 지원은 빈 칸으로 왔다. */
  fallback?: { reason: string; at: string } | null;
}

/** 사실만 채운 초안(ADR-093) 위에 띄우는 말. 일지 편집기 둘이 같이 쓴다. */
export const FALLBACK_DRAFT =
  "AI 가 이번에는 초안을 쓰지 못했어요. 사실은 그대로 담았으니 해석 · 지원을 직접 써 주세요.";
export interface ApiDocumentListItem {
  id: number;
  kind: string;
  title: string;
  class_id: number;
  class_name: string;
  child_id: number | null;
  child_name: string | null;
  start: string;
  end: string;
  status: string;
  origin: string;
  stale: boolean;
  generation: ApiDocumentGeneration;
  sources_count: number;
  /** 지금 글에 붙은 AI 검토 상태 (ADR-083). 없거나 글이 바뀌었으면 null. */
  ai_review_state?: AiReviewState | null;
  created_at: string;
  updated_at: string;
}
export interface ApiRelatedDocumentsResponse {
  items: ApiDocumentListItem[];
  expected_kinds: string[];
}
export interface ApiDocumentSection {
  heading: string;
  body: string;
  source_ids: number[];
}
export interface ApiDocumentSource {
  id: number;
  date: string | null;
  text: string;
  /** 관찰일지 근거에만 있다. 양식의 영역 행을 이것으로 나눈다 (§11). */
  domain?: string | null;
  /** 관찰 기록의 상황 사본 (ADR-088). 옛 문서 · 그 밖의 근거는 null 이다. */
  context?: string | null;
  /** 근거 종류. 아직 상세 응답에 없는 서버가 있어 비어 있을 수 있다. */
  source_kind?: string | null;
  class_id: number;
  child_id: number | null;
}
export interface ApiDocumentDetail extends Omit<ApiDocumentListItem, "sources_count"> {
  sections: ApiDocumentSection[];
  sources: ApiDocumentSource[];
  review_note: string;
  class_note: string;
  /** 관찰일지를 만들 때 찍은 영역 축 (ADR-088). 옛 문서 · 그 밖의 문서는 null 이다. */
  observation_axis?: string | null;
  ai_review?: { state: AiReviewState; issues: ApiVerifyIssue[]; message: string } | null;
}

/**
 * 예전 mock 초안은 본문 앞에 `[mock] ` 을 달고 저장됐다. 제출 문서에 시스템 글자가 남는다.
 *
 * **맨 앞에 한 번만** 떼어낸다. 교사가 쓴 문장 안의 `[mock]` 은 건드리지 않는다 — 전역
 * 치환으로 지우면 교사 글을 말없이 고치는 셈이다.
 */
const MOCK_PREFIX = /^\[mock\]\s*/;

/** 목록 항목. `sections` · `sources` 가 없으므로 문서 전체인 척하지 않는다. */
export interface DocumentSummary {
  id: string;
  serverId: number;
  kind: DocumentKind;
  title: string;
  classId: string;
  className: string;
  childId: string;
  childName: string;
  start: string;
  end: string;
  status: SavedDocument["status"];
  origin: SavedDocument["origin"];
  stale: boolean;
  sourcesCount: number;
  /** 목록에서만 온다 (ADR-083). */
  aiReviewState?: AiReviewState | null;
  createdAt: string;
  updatedAt: string;
}
export interface RelatedDocuments {
  items: DocumentSummary[];
  expectedKinds: RecordKind[];
}
/** 단건. 화면 model 에 서버에만 있는 값을 더한다. */
export interface ServerDocument extends SavedDocument {
  serverId: number;
  stale: boolean;
  /** 확정 취소 응답에서만 온다. 이 문서를 직접 근거로 쓴 문서 중 이번에 새로 stale 이 된 수. */
  newlyStaleCount?: number;
  /** 지금 글을 검토한 결과 (ADR-083). 검토한 적 없거나 글이 바뀌었으면 null. */
  aiReview: AiReview | null;
}

const STATUS: Record<string, SavedDocument["status"]> = { DRAFT: "draft", CONFIRMED: "confirmed" };
const ORIGIN: Record<string, SavedDocument["origin"]> = {
  AI: "ai",
  TEACHER: "teacher",
  TEMPLATE: "template",
  IMPORT: "import",
};

/** 매핑이 없으면 서버 접두사를 그대로 둔다 — 화면 id 를 지어내지 않는다. */
const localClass = (id: number) => classLocalId(id) ?? CLASS_PREFIX + id;
const localChild = (id: number | null) =>
  id === null ? "" : (childLocalId(id) ?? CHILD_PREFIX + id);

function summary(dto: ApiDocumentListItem): DocumentSummary {
  return {
    id: documentLocalId(dto.id),
    serverId: dto.id,
    kind: dto.kind as DocumentKind,
    title: dto.title,
    classId: localClass(dto.class_id),
    className: dto.class_name,
    childId: localChild(dto.child_id),
    childName: dto.child_name ?? "",
    start: dto.start,
    end: dto.end,
    status: STATUS[dto.status] ?? "draft",
    origin: ORIGIN[dto.origin] ?? "teacher",
    stale: dto.stale,
    sourcesCount: dto.sources_count,
    aiReviewState: dto.ai_review_state ?? null,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  };
}

export function toDocument(dto: ApiDocumentDetail): ServerDocument {
  // 한 문서의 근거는 한 종류라 번호가 겹치지 않는다. 칸의 번호도 이 표로 종류를 찾는다.
  const kinds = new Map(dto.sources.map((s) => [s.id, sourceKindOf(dto.kind, s.source_kind)]));
  const localId = (id: number) => sourceLocalId(kinds.get(id) ?? sourceKindOf(dto.kind), id);
  const sources: Source[] = dto.sources.map((s) => ({
    id: localId(s.id),
    kind: kinds.get(s.id),
    date: s.date ?? "",
    text: s.text,
    classId: localClass(s.class_id),
    childId: localChild(s.child_id),
    ...(s.domain ? { domain: s.domain } : {}),
    ...(s.context ? { context: s.context } : {}),
  }));
  const generatedSection = (s: ApiDocumentSection) =>
    dto.origin === "AI" && ["해석", "지원"].includes(s.heading);
  const legacyMock = dto.sections.some((s) => generatedSection(s) && MOCK_PREFIX.test(s.body));
  const sections: Section[] = dto.sections.map((s) => ({
    heading: s.heading,
    body: generatedSection(s) ? s.body.replace(MOCK_PREFIX, "") : s.body,
    sourceIds: s.source_ids.map(localId),
  }));
  return {
    ...summary({ ...dto, sources_count: dto.sources.length }),
    sections,
    sources,
    reviewNote: dto.review_note,
    classNote: dto.class_note ?? "",
    // 새 문서는 서버가 `<규칙버전>-mock` 으로 알리고, 예전 문서는 떼어낸 접두어로 안다.
    mockDraft: legacyMock || /-mock$/.test(dto.generation.rule_version ?? ""),
    fallbackDraft: !!dto.generation.fallback,
    ...(dto.observation_axis ? { observationAxis: dto.observation_axis } : {}),
    aiReview: dto.ai_review
      ? {
          state: dto.ai_review.state,
          issues: dto.ai_review.issues.map(toIssue),
          message: dto.ai_review.message,
        }
      : null,
  };
}

export interface DocumentQuery {
  kind?: RecordKind;
  class_id?: number;
  child_id?: number;
  status?: "DRAFT" | "CONFIRMED";
  stale?: boolean;
}
function query(params: DocumentQuery): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params))
    if (value !== undefined) search.set(key, String(value));
  const text = search.toString();
  return text ? "?" + text : "";
}

export async function listDocuments(params: DocumentQuery = {}): Promise<DocumentSummary[]> {
  const { items } = await apiRequest<{ items: ApiDocumentListItem[] }>(
    "/api/documents" + query(params),
  );
  return items.map(summary);
}

export const UNMAPPED = "연결된 반·아동 또는 근거 정보를 확인할 수 없어요. 다시 불러와주세요.";

/** 목록에는 `sections` · `sources` 가 없다. 문서를 열 때 단건으로 받는다 (§11). */
export async function getDocument(localId: string): Promise<ServerDocument> {
  const id = documentServerId(localId);
  if (id === null) throw new Error(UNMAPPED);
  return toDocument(await apiRequest<ApiDocumentDetail>("/api/documents/" + id));
}

/** Confirmed observation/daily journals use the same authenticated download path as plans.
 *  서버가 같은 hwpx 를 hwp · pdf 로도 바꿔 준다 (`?format=`, ADR-039 · ADR-061). */
export async function downloadDocumentHwpx(
  localId: string,
  format: ExportFormat = "hwpx",
): Promise<void> {
  const id = documentServerId(localId);
  if (id === null) throw new Error(UNMAPPED);
  const query = format === "hwpx" ? "" : `?format=${format}`;
  return downloadHwpx(`/api/documents/${id}/export/hwp${query}`, `일지.${format}`);
}

/** 겹치는 확정 문서와 기대하는 종류. 관련 여부와 반환 순서는 서버가 결정한다 (§11). */
export async function getRelatedDocuments(localId: string): Promise<RelatedDocuments> {
  const id = documentServerId(localId);
  if (id === null) throw new Error(UNMAPPED);
  const dto = await apiRequest<ApiRelatedDocumentsResponse>("/api/documents/" + id + "/related");
  return {
    items: dto.items.map(summary),
    expectedKinds: dto.expected_kinds as RecordKind[],
  };
}

/** 반·아동·근거를 서버 id 로 옮기지 못하면 요청을 보내지 않는다. */
export interface DocumentCreateInput {
  kind: RecordKind;
  classId: string;
  childId: string;
  start: string;
  end: string;
  sourceIds: string[];
  /**
   * 주간 보육일지의 근거가 어디서 오나 (§11). 생략하면 확정한 일일 보육일지다.
   * `"routine"` 은 일일 보육일지를 쓰지 않는 원 — 그 주 일과 기록을 바로 받는다.
   */
  sourceKind?: "dailyLog" | "routine";
  /**
   * 관찰일지 「넣어서 다시」. 같은 아이 · 같은 기간 초안이 있으면 서버는 그것을 돌려주는데(ADR-083),
   * 이걸 켜면 새로 만들고 옛 초안을 지운다.
   */
  replaceDraft?: boolean;
}

export async function createDocument(input: DocumentCreateInput): Promise<ServerDocument> {
  const class_id = classServerId(input.classId);
  const child_id = input.childId ? childServerId(input.childId) : null;
  // 주간은 고른 종류의 id 만 받는다 — 일과 근거면 일과 표, 아니면 문서 표의 번호다.
  const source_ids = input.sourceIds.map((id) =>
    input.kind !== "weeklyLog"
      ? sourceServerId(input.kind, id)
      : input.sourceKind === "routine"
        ? routineServerId(id)
        : documentServerId(id),
  );
  if (
    class_id === null ||
    (input.childId && child_id === null) ||
    source_ids.some((id) => id === null)
  )
    throw new Error(UNMAPPED);
  const dto = await apiRequest<ApiDocumentDetail>("/api/documents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      kind: input.kind,
      class_id,
      child_id,
      start: input.start,
      end: input.end,
      source_ids,
      ...(input.sourceKind ? { source_kind: input.sourceKind } : {}),
      ...(input.replaceDraft ? { replace_draft: true } : {}),
    }),
  });
  return toDocument(dto);
}

/** 교사가 원에서 쓰던 서류를 증빙으로 올린다 (§11 「증빙 등록」). */
export interface DocumentImportInput {
  kind: RecordKind;
  classId: string;
  childId: string;
  start: string;
  end: string;
  /** 파일 이름. 비면 서버가 종류·기간으로 제목을 만든다. */
  title: string;
  /** 원문 텍스트. 파일은 `/api/templates/extract` 가 먼저 글자로 바꾼다. */
  body: string;
}

/** 등록은 됐지만 교사가 알아야 하는 것. 비어 있으면 걸린 것이 없다. */
export interface EvidenceNotice {
  code: string;
  message: string;
}

export interface ImportedDocument {
  document: ServerDocument;
  notices: EvidenceNotice[];
}

/**
 * 증빙 등록. 생성(`createDocument`)과 다른 길이다 — 근거 id 가 없고 AI 를 부르지 않는다.
 *
 * 확인 3개는 화면이 묶어서 한 번에 받는다. 셋 다 켜야 서버가 확정으로 저장하고,
 * 확정이라야 평가제 집계에 들어간다 (§12).
 */
export async function importDocument(input: DocumentImportInput): Promise<ImportedDocument> {
  const class_id = classServerId(input.classId);
  const child_id = input.childId ? childServerId(input.childId) : null;
  if (class_id === null || (input.childId && child_id === null)) throw new Error(UNMAPPED);
  const dto = await apiRequest<ApiDocumentDetail & { notices?: EvidenceNotice[] }>(
    "/api/documents/import",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kind: input.kind,
        class_id,
        child_id,
        start: input.start,
        end: input.end,
        title: input.title,
        body: input.body,
        checks: { original: true, meta: true, not_a_pass: true },
      }),
    },
  );
  return { document: toDocument(dto), notices: dto.notices ?? [] };
}

/** 본문 세 칸과 메모를 보낸다. 상태·반·아동·기간은 서버가 지킨다 (§11). */
export async function updateDocument(
  localId: string,
  input: {
    kind: string;
    sections: Section[];
    reviewNote: string;
    updatedAt: string;
    /** 반 운영 특이사항. 안 보내면 서버가 이전 값을 그대로 둔다. */
    classNote?: string;
  },
): Promise<ServerDocument> {
  const id = documentServerId(localId);
  if (id === null) throw new Error(UNMAPPED);
  const sections = input.sections.map((s) => ({
    heading: s.heading,
    body: s.body,
    source_ids: s.sourceIds.map((sid) => sourceServerId(input.kind, sid)),
  }));
  if (sections.some((s) => s.source_ids.some((sid) => sid === null))) throw new Error(UNMAPPED);
  const dto = await apiRequest<ApiDocumentDetail>("/api/documents/" + id, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      sections,
      review_note: input.reviewNote,
      ...(input.classNote === undefined ? {} : { class_note: input.classNote }),
      updated_at: input.updatedAt,
    }),
  });
  return toDocument(dto);
}

export interface VerifyIssue {
  heading: "해석" | "지원";
  sentence: string;
  code: string;
  /** 부딪힌 근거 기록의 원문. 기록과 어긋날 때만 있다. */
  sourceText: string | null;
  reason: string;
  fix: string;
}

/** 붙여 둔 검토 상태 (ADR-083). `mock` · `failed` 의 빈 목록은 「문제없음」이 아니다. */
export type AiReviewState = "done" | "mock" | "failed";
export interface AiReview {
  state: AiReviewState;
  issues: VerifyIssue[];
  /** `failed` 일 때 이유. */
  message: string;
}
interface ApiVerifyIssue {
  heading: "해석" | "지원";
  sentence: string;
  code: string;
  source_text: string | null;
  reason: string;
  fix: string;
}
const toIssue = (i: ApiVerifyIssue): VerifyIssue => ({
  heading: i.heading,
  sentence: i.sentence,
  code: i.code,
  sourceText: i.source_text ?? null,
  reason: i.reason,
  fix: i.fix,
});

export interface VerifyResult {
  issues: VerifyIssue[];
  /** false 면 서버가 판정하지 않았다(mock). 빈 목록을 「문제없음」으로 읽으면 안 된다. */
  judged: boolean;
}

/**
 * 3단 AI 검토 (§11 · ADR-071). 저장 전 글을 보낸다. 서버는 결과를 그 글의 지문과 함께
 * 붙여 두고(ADR-083), 같은 글이 저장돼 있을 때만 상세 응답에 다시 준다.
 * 아이 이름은 서버가 가명으로 바꾼 뒤 판정 모델에 보낸다 — 화면은 이름을 바꾸지 않는다.
 */
export async function verifyDocument(
  localId: string,
  kind: string,
  sections: Section[],
): Promise<VerifyResult> {
  const id = documentServerId(localId);
  if (id === null) throw new Error(UNMAPPED);
  const dto = await apiRequest<{ issues: ApiVerifyIssue[]; judge: "jev" | "mock" }>(
    "/api/documents/" + id + "/verify",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sections: sectionsBody(kind, sections) }),
    },
  );
  return { judged: dto.judge !== "mock", issues: dto.issues.map(toIssue) };
}

function sectionsBody(kind: string, sections: Section[]) {
  const body = sections.map((s) => ({
    heading: s.heading,
    body: s.body,
    source_ids: s.sourceIds.map((sid) => sourceServerId(kind, sid)),
  }));
  if (body.some((s) => s.source_ids.some((sid) => sid === null))) throw new Error(UNMAPPED);
  return body;
}

export type RewriteStyle = "fix" | "shorter" | "concrete";
export interface RewriteResult {
  /** 1 · 2단을 지난 고친 문장. 걸렸으면 null — 보여 주지 않는다. */
  sentence: string | null;
  /** 고친 문장에 대한 jev 판정 — 「확인할 곳」. 거르는 데 쓰지 않는다. */
  issues: VerifyIssue[];
  /** false 면 판정하지 않았다(mock · 실패). 빈 목록을 「확인할 곳 없음」으로 읽으면 안 된다. */
  judged: boolean;
}

/** 걸린 문장 하나 고쳐 쓰기 (AI ②, §11 · ADR-083). 서버는 저장하지 않는다. */
export async function rewriteSentence(
  localId: string,
  kind: string,
  input: {
    heading: "해석" | "지원";
    sentence: string;
    style: RewriteStyle;
    reason: string;
    sections: Section[];
  },
): Promise<RewriteResult> {
  const id = documentServerId(localId);
  if (id === null) throw new Error(UNMAPPED);
  const dto = await apiRequest<{
    sentence: string | null;
    issues: ApiVerifyIssue[];
    judge: "jev" | "mock" | "failed";
  }>("/api/documents/" + id + "/rewrite", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      heading: input.heading,
      sentence: input.sentence,
      style: input.style,
      reason: input.reason,
      sections: sectionsBody(kind, input.sections),
    }),
  });
  return { sentence: dto.sentence, issues: dto.issues.map(toIssue), judged: dto.judge === "jev" };
}

/** 확정본 여러 장을 zip 하나로 (§11 「묶음 받기」). 내보낼 수 있는 것만 보낸다 — 하나라도 아니면 409. */
export async function downloadDocumentBundle(localIds: string[]): Promise<void> {
  const ids = localIds.map(documentServerId);
  if (!ids.length || ids.some((id) => id === null)) throw new Error(UNMAPPED);
  const query = ids.map((id) => `ids=${id}`).join("&");
  return downloadHwpx(`/api/documents/export/bundle?${query}`, "일지 묶음.zip");
}

/**
 * 검토 결과를 교사가 읽을 줄로. **한 문장에 걸린 것은 한 줄로 묶는다** — 같은 문장이 이유마다
 * 따로 뜨면 고칠 곳이 여러 개로 보인다. 기록과 어긋나면 그 기록 원문을 같이 보여 준다.
 */
export function verifyLines(result: VerifyResult): string[] {
  const lines = new Map<string, string[]>();
  for (const i of result.issues) {
    const key = `[${i.heading}] 「${i.sentence}」`;
    const record = i.sourceText ? ` 기록에는 「${i.sourceText}」로 적혀 있어요.` : "";
    lines.set(key, [...(lines.get(key) ?? []), `${i.reason}${record} ${i.fix}`]);
  }
  return [...lines].map(([key, notes]) => `${key} — ${notes.join(" / ")}`);
}

/** 교사 확인 세 개. 3단 LLM 검증은 서버가 확정 조건으로 요구하지 않는다 (§11). */
export async function confirmDocument(localId: string): Promise<ServerDocument> {
  const id = documentServerId(localId);
  if (id === null) throw new Error(UNMAPPED);
  const dto = await apiRequest<ApiDocumentDetail>("/api/documents/" + id + "/confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ checks: { fact: true, interpretation: true, support: true } }),
  });
  return toDocument(dto);
}

/**
 * 확정을 되돌린다 (§11). 이미 초안이면 서버가 그대로 200 으로 돌려준다.
 *
 * 영향도 같이 받는다 — 화면이 「이 문서를 근거로 쓴 문서 N건이 다시 검토 대상」을 띄운다.
 */
export async function unconfirmDocument(localId: string): Promise<ServerDocument> {
  const id = documentServerId(localId);
  if (id === null) throw new Error(UNMAPPED);
  // 영향이 없는 응답(이 옵션을 모르는 서버)이어도 확정 취소는 그대로 반영한다. 안내만 빠진다.
  const dto = await apiRequest<
    ApiDocumentDetail & { review_impact?: { newly_stale_document_ids: number[] } }
  >("/api/documents/" + id + "/unconfirm?include_impact=true", { method: "POST" });
  return {
    ...toDocument(dto),
    newlyStaleCount: dto.review_impact?.newly_stale_document_ids.length,
  };
}

/**
 * 바뀐 상위 근거를 다시 떠서 `사실` 을 잇고 stale 을 푼다 (§11).
 *
 * `해석`·`지원` 은 서버가 그대로 둔다. 확정본은 `ALREADY_CONFIRMED` 409 라 초안에서만 부른다.
 */
export async function refreshDocument(
  localId: string,
  resolutions?: SourceResolution[],
): Promise<ServerDocument> {
  const id = documentServerId(localId);
  if (id === null) throw new Error(UNMAPPED);
  // 고른 처리가 없으면 본문 없이 보낸다 — 이 필드를 모르는 서버도 그대로 받는다.
  const dto = await apiRequest<ApiDocumentDetail>("/api/documents/" + id + "/refresh", {
    method: "POST",
    ...(resolutions?.length
      ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify({ resolutions }) }
      : {}),
  });
  return toDocument(dto);
}

export async function deleteDocument(localId: string): Promise<void> {
  const id = documentServerId(localId);
  if (id === null) throw new Error(UNMAPPED);
  await apiRequest<void>("/api/documents/" + id, { method: "DELETE" });
}

export interface SourceComparison {
  document_id: number;
  updated_at: string;
  review_token: string;
  sources: {
    id: number;
    before: string;
    after: string | null;
    state: "changed" | "unchanged" | "missing";
  }[];
  can_reconfirm: boolean;
  /** 사라진 근거를 대신할 같은 반·같은 날의 일과. 이 필드가 없는 서버도 받아 준다. */
  candidates?: { id: number; text: string }[];
}

/** 사라진 근거 하나를 어떻게 할지. 서버 id 를 쓴다 — 비교 응답이 주는 그 번호다. */
export interface SourceResolution {
  source_id: number;
  action: "drop" | "replace";
  replacement_id?: number | null;
}

export async function getSourceComparison(localId: string): Promise<SourceComparison> {
  const id = documentServerId(localId);
  if (id === null) throw new Error(UNMAPPED);
  return apiRequest<SourceComparison>(`/api/documents/${id}/source-comparison`);
}

export interface ReconfirmInput {
  comparison: SourceComparison;
  sections: Section[];
  updatedAt: string;
  /** 비어 있으면 보내지 않는다 — 이 필드를 모르는 서버가 422 로 거절한다. */
  resolutions?: SourceResolution[];
}

export async function reconfirmDocument(
  localId: string,
  input: ReconfirmInput,
): Promise<ServerDocument> {
  const id = documentServerId(localId);
  if (id === null || id !== input.comparison.document_id) throw new Error(UNMAPPED);
  const sections = input.sections.map((s) => ({
    heading: s.heading,
    body: s.body,
    source_ids: s.sourceIds.map((sid) => routineServerId(sid)),
  }));
  if (sections.some((s) => s.source_ids.some((sid) => sid === null))) throw new Error(UNMAPPED);
  return toDocument(
    await apiRequest<ApiDocumentDetail>(`/api/documents/${id}/reconfirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        review_token: input.comparison.review_token,
        updated_at: input.updatedAt,
        sections,
        checks: { fact: true, interpretation: true, support: true },
        ...(input.resolutions?.length ? { resolutions: input.resolutions } : {}),
      }),
    }),
  );
}

/** 409 셋을 갈라 본다 — 같은 status 라도 교사가 할 일이 다르다. */
const code = errorCode;
export const isGateBlocked = (error: unknown) => code(error) === "GATE_BLOCKED";
export const isAlreadyConfirmed = (error: unknown) => code(error) === "ALREADY_CONFIRMED";
export const isStaleWrite = (error: unknown) => code(error) === "STALE_WRITE";
