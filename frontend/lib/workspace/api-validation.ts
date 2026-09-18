import {
  DOCUMENT_KINDS,
  hasStrings,
  isObject,
  isSavedDocument,
  isSource,
  validDate,
  validPeriod,
} from "./model";

export class BodyLimitError extends Error {}
export async function readLimitedBody(request: Request, maxBytes: number): Promise<ArrayBuffer> {
  if (Number(request.headers.get("content-length") || 0) > maxBytes) throw new BodyLimitError();
  const reader = request.body?.getReader();
  if (!reader) return new ArrayBuffer(0);
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > maxBytes) {
        await reader.cancel();
        throw new BodyLimitError();
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const result = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    result.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return result.buffer;
}
function text(value: unknown, max = 60000): value is string {
  return typeof value === "string" && value.trim().length > 0 && value.length <= max;
}
function sources(value: unknown) {
  return (
    Array.isArray(value) &&
    value.length > 0 &&
    value.length <= 100 &&
    value.every((v) => isSource(v) && text(v.text)) &&
    new Set(value.map((v) => v.id)).size === value.length
  );
}
/** 계획안 요청의 실제 선택 연령([3,5] 등). 없을 수도 있고, 있으면 3·4·5 중 중복 없는 값만 허용한다. */
function validSelectedAges(value: unknown) {
  return (
    value === undefined ||
    (Array.isArray(value) &&
      value.length > 0 &&
      value.length <= 3 &&
      value.every((age) => age === 3 || age === 4 || age === 5) &&
      new Set(value).size === value.length)
  );
}
export function validAIInput(task: string, payload: unknown): boolean {
  if (!isObject(payload)) return false;
  if (task === "template") return text(payload.text);
  if (task === "trends")
    return (
      text(payload.topic, 500) && typeof payload.today === "string" && validDate(payload.today)
    );
  if (task === "verify") return isSavedDocument(payload);
  if (task === "evaluation")
    return (
      isSavedDocument(payload.document) &&
      Array.isArray(payload.criteria) &&
      payload.criteria.length > 0 &&
      payload.criteria.length <= 50 &&
      payload.criteria.every(
        (c) =>
          isObject(c) &&
          hasStrings(c, ["id", "label", "terms", "source"]) &&
          text(c.id, 100) &&
          text(c.label, 300) &&
          text(c.source, 300),
      )
    );
  if (task === "evidence")
    return (
      isSavedDocument(payload.document) &&
      Array.isArray(payload.evidence) &&
      payload.evidence.length > 0 &&
      payload.evidence.length <= 100 &&
      payload.evidence.every(isSavedDocument)
    );
  if (task === "compare") {
    if (!sources(payload.sources)) return false;
    const list = payload.sources as {
      id: string;
      classId: string;
      childId: string;
      date: string;
    }[];
    return (
      list.length === 2 &&
      !!list[0].classId &&
      !!list[0].childId &&
      list[0].classId === list[1].classId &&
      list[0].childId === list[1].childId &&
      list[0].date <= list[1].date
    );
  }
  if (task === "document") {
    if (
      ![
        DOCUMENT_KINDS.dailyLog,
        DOCUMENT_KINDS.weeklyLog,
        DOCUMENT_KINDS.observation,
        DOCUMENT_KINDS.assessment,
      ].includes(payload.kind as typeof DOCUMENT_KINDS.dailyLog) ||
      typeof payload.start !== "string" ||
      typeof payload.end !== "string" ||
      !validPeriod(payload.start, payload.end) ||
      !sources(payload.sources)
    )
      return false;
    const list = payload.sources as { classId: string; childId: string; date: string }[];
    return (
      !!list[0].classId &&
      list.every(
        (s) =>
          s.classId === list[0].classId &&
          s.date >= String(payload.start) &&
          s.date <= String(payload.end),
      ) &&
      (payload.kind !== DOCUMENT_KINDS.dailyLog || payload.start === payload.end) &&
      (![DOCUMENT_KINDS.observation, DOCUMENT_KINDS.assessment].includes(
        payload.kind as typeof DOCUMENT_KINDS.observation,
      ) ||
        (!!list[0].childId && list.every((s) => s.childId === list[0].childId)))
    );
  }
  if (task === "plan") {
    if (
      !["annual", "monthly", "weekly", "daily"].includes(payload.type as string) ||
      !["3", "4", "5", "mixed"].includes(payload.age as string) ||
      !validSelectedAges(payload.ages) ||
      typeof payload.memo !== "string" ||
      payload.memo.length > 6000 ||
      !isObject(payload.period)
    )
      return false;
    const p = payload.period;
    if (
      !isObject(p.annual) ||
      !Number.isInteger(p.annual.year) ||
      Number(p.annual.year) < 2000 ||
      Number(p.annual.year) > 2100
    )
      return false;
    if (payload.type === "daily")
      return isObject(p.daily) && typeof p.daily.date === "string" && validDate(p.daily.date);
    if (payload.type === "monthly" || payload.type === "weekly") {
      const part = p[payload.type];
      if (
        !isObject(part) ||
        !Number.isInteger(part.month) ||
        Number(part.month) < 1 ||
        Number(part.month) > 12
      )
        return false;
      if (
        payload.type === "weekly" &&
        (!Number.isInteger(part.week) ||
          Number(part.week) < 1 ||
          Number(part.week) >
            Math.ceil(new Date(Number(p.annual.year), Number(part.month), 0).getDate() / 7))
      )
        return false;
    }
    return (
      payload.template === null ||
      payload.template === undefined ||
      (isObject(payload.template) &&
        typeof payload.template.style === "string" &&
        Array.isArray(payload.template.headings) &&
        payload.template.headings.length <= 20 &&
        payload.template.headings.every((h) => text(h, 300)))
    );
  }
  return false;
}

/** Runtime validation also covers model refusals, malformed JSON and schema drift. */
export function matchesSchema(value: unknown, schema: unknown): boolean {
  if (!isObject(schema)) return false;
  if (schema.type === "string")
    return (
      typeof value === "string" && (!Array.isArray(schema.enum) || schema.enum.includes(value))
    );
  if (schema.type === "array")
    return (
      Array.isArray(value) &&
      value.length <= 100 &&
      value.every((v) => matchesSchema(v, schema.items))
    );
  if (schema.type === "object") {
    if (!isObject(value) || !isObject(schema.properties) || !Array.isArray(schema.required))
      return false;
    const properties = schema.properties;
    return (
      schema.required.every((k) => typeof k === "string" && Object.hasOwn(value, k)) &&
      Object.keys(value).every(
        (k) => Object.hasOwn(properties, k) && matchesSchema(value[k], properties[k]),
      )
    );
  }
  return false;
}
