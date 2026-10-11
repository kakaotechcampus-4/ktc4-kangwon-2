/** 일지 계열 문서 API (docs/api-spec.md §11). id 변환을 여기서 끝내고 화면에는 화면 id 만 준다. */
import { apiRequest, ApiError } from "./client";
import { classLocalId, childLocalId, classServerId, childServerId } from "./onboarding";
import { observationLocalId, observationServerId } from "./observations";
import type { DocumentKind, SavedDocument, Section, Source } from "../workspace/model";

/** 서버가 다루는 네 종류. 계획안(annual·monthly·weekly·daily)은 이 API 가 아니다. */
export const RECORD_KINDS = ["dailyLog", "weeklyLog", "observation", "assessment"] as const;
export type RecordKind = (typeof RECORD_KINDS)[number];
export const isRecordKind = (kind: string): kind is RecordKind =>
  (RECORD_KINDS as readonly string[]).includes(kind);

/**
 * 아직 화면에서 만들 수 없는 종류.
 *
 * 일일 보육일지의 근거는 관찰 기록이 아니라 「일과 기록」이다 (ADR-025 · §10-1).
 * 일과 기록을 적는 화면이 아직 없어서, 지금 만들기를 누르면 서버가 422 로 돌려보낸다.
 * 고를 수 있는데 아무것도 안 되는 것보다 잠가 두는 쪽이 낫다 — 그 화면이 들어오면 푼다.
 */
export const BLOCKED_RECORD_KINDS: readonly RecordKind[] = ["dailyLog"];

// 서버 id 는 테이블마다 1 부터 센다. 화면 id 와 섞이지 않게 접두사를 붙인다.
const DOCUMENT_PREFIX = "document:";
const CLASS_PREFIX = "server-class:";
const CHILD_PREFIX = "server-child:";
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

/** 근거 id 가 가리키는 것은 종류마다 다르다 — 주간 보육일지만 문서, 나머지는 관찰 기록 (§11). */
const sourceLocalId = (kind: string, id: number) =>
  kind === "weeklyLog" ? documentLocalId(id) : observationLocalId(id);
const sourceServerId = (kind: string, localId: string) =>
  kind === "weeklyLog" ? documentServerId(localId) : observationServerId(localId);

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
}

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
  const sections: Section[] = dto.sections.map((s) => ({
    heading: s.heading,
    body: s.body,
    sourceIds: s.source_ids.map((id) => sourceLocalId(dto.kind, id)),
  }));
  return {
    ...summary({ ...dto, sources_count: dto.sources.length }),
    sections,
    sources,
    reviewNote: dto.review_note,
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
}

export async function createDocument(input: DocumentCreateInput): Promise<ServerDocument> {
  const class_id = classServerId(input.classId);
  const child_id = input.childId ? childServerId(input.childId) : null;
  const source_ids = input.sourceIds.map((id) => sourceServerId(input.kind, id));
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
    }),
  });
  return toDocument(dto);
}

/** 세 칸만 보낸다. 상태·반·아동·기간은 서버가 지킨다 (§11). */
export async function updateDocument(
  localId: string,
  input: { kind: string; sections: Section[]; reviewNote: string; updatedAt: string },
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

/** 확정을 되돌린다 (§11). 이미 초안이면 서버가 그대로 200 으로 돌려준다. */
export async function unconfirmDocument(localId: string): Promise<ServerDocument> {
  const id = documentServerId(localId);
  if (id === null) throw new Error(UNMAPPED);
  const dto = await apiRequest<ApiDocumentDetail>("/api/documents/" + id + "/unconfirm", {
    method: "POST",
  });
  return toDocument(dto);
}

/**
 * 바뀐 상위 근거를 다시 떠서 `사실` 을 잇고 stale 을 푼다 (§11).
 *
 * `해석`·`지원` 은 서버가 그대로 둔다. 확정본은 `ALREADY_CONFIRMED` 409 라 초안에서만 부른다.
 */
export async function refreshDocument(localId: string): Promise<ServerDocument> {
  const id = documentServerId(localId);
  if (id === null) throw new Error(UNMAPPED);
  const dto = await apiRequest<ApiDocumentDetail>("/api/documents/" + id + "/refresh", {
    method: "POST",
  });
  return toDocument(dto);
}

export async function deleteDocument(localId: string): Promise<void> {
  const id = documentServerId(localId);
  if (id === null) throw new Error(UNMAPPED);
  await apiRequest<void>("/api/documents/" + id, { method: "DELETE" });
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
