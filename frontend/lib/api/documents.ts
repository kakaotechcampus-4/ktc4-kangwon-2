/** 일지 계열 문서 API (docs/api-spec.md §11). id 변환을 여기서 끝내고 화면에는 화면 id 만 준다. */
import { apiRequest, ApiError } from "./client";
import { downloadHwpx } from "./export";
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

/**
 * 근거 id 가 가리키는 것은 종류마다 다르다 (§11).
 * 주간 보육일지는 문서, 일일 보육일지는 일과 기록(ADR-025), 나머지는 관찰 기록이다.
 */
function sourceLocalId(kind: string, id: number) {
  if (kind === "weeklyLog") return documentLocalId(id);
  if (kind === "dailyLog") return routineLocalId(id);
  return observationLocalId(id);
}
function sourceServerId(kind: string, localId: string) {
  if (kind === "weeklyLog") return documentServerId(localId);
  if (kind === "dailyLog") return routineServerId(localId);
  return observationServerId(localId);
}

export interface ApiDocumentGeneration {
  method: string | null;
  rule_id: string | null;
  rule_version: string | null;
}
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
  class_id: number;
  child_id: number | null;
}
export interface ApiDocumentDetail extends Omit<ApiDocumentListItem, "sources_count"> {
  sections: ApiDocumentSection[];
  sources: ApiDocumentSource[];
  review_note: string;
  class_note: string;
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
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  };
}

export function toDocument(dto: ApiDocumentDetail): ServerDocument {
  const sources: Source[] = dto.sources.map((s) => ({
    id: sourceLocalId(dto.kind, s.id),
    date: s.date ?? "",
    text: s.text,
    classId: localClass(s.class_id),
    childId: localChild(s.child_id),
  }));
  const generatedSection = (s: ApiDocumentSection) =>
    dto.origin === "AI" && ["해석", "지원"].includes(s.heading);
  const legacyMock = dto.sections.some((s) => generatedSection(s) && MOCK_PREFIX.test(s.body));
  const sections: Section[] = dto.sections.map((s) => ({
    heading: s.heading,
    body: generatedSection(s) ? s.body.replace(MOCK_PREFIX, "") : s.body,
    sourceIds: s.source_ids.map((id) => sourceLocalId(dto.kind, id)),
  }));
  return {
    ...summary({ ...dto, sources_count: dto.sources.length }),
    sections,
    sources,
    reviewNote: dto.review_note,
    classNote: dto.class_note ?? "",
    // 새 문서는 서버가 `<규칙버전>-mock` 으로 알리고, 예전 문서는 떼어낸 접두어로 안다.
    mockDraft: legacyMock || /-mock$/.test(dto.generation.rule_version ?? ""),
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

/** Confirmed observation/daily journals use the same authenticated download path as plans. */
export async function downloadDocumentHwpx(localId: string): Promise<void> {
  const id = documentServerId(localId);
  if (id === null) throw new Error(UNMAPPED);
  return downloadHwpx(`/api/documents/${id}/export/hwp`, "일지.hwpx");
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
}

export async function createDocument(input: DocumentCreateInput): Promise<ServerDocument> {
  const class_id = classServerId(input.classId);
  const child_id = input.childId ? childServerId(input.childId) : null;
  // 일과 기록을 근거로 쓰는 주간은 id 가 일과 표의 것이다 — 문서 접두사로 풀면 안 된다.
  const source_ids = input.sourceIds.map((id) =>
    input.sourceKind === "routine" ? routineServerId(id) : sourceServerId(input.kind, id),
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
function code(error: unknown): string | null {
  if (!(error instanceof ApiError)) return null;
  const body = error.body as { error?: { code?: unknown } } | null;
  return typeof body === "object" && body !== null && typeof body.error?.code === "string"
    ? body.error.code
    : null;
}
export const isGateBlocked = (error: unknown) => code(error) === "GATE_BLOCKED";
export const isAlreadyConfirmed = (error: unknown) => code(error) === "ALREADY_CONFIRMED";
export const isStaleWrite = (error: unknown) => code(error) === "STALE_WRITE";
