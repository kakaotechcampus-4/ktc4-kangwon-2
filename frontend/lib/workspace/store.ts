"use client";
import { useEffect, useState } from "react";
import {
  EMPTY_WORKSPACE,
  isSavedDocument,
  validDate,
  type SavedDocument,
  type Workspace,
} from "./model";
import { importDocument, isRecordKind } from "../api/documents";
import { accountStorageKey } from "../auth/demo-session";
import { withoutDocumentBodies } from "../privacy/browser-storage";
const KEY = "saessak.workspace.v1";
const EVENT = "saessak-workspace-change";

function object(v: unknown): v is Record<string, unknown> {
  return !!v && typeof v === "object" && !Array.isArray(v);
}
function strings(v: Record<string, unknown>, keys: string[]) {
  return keys.every((k) => typeof v[k] === "string");
}
export function parseWorkspace(raw: string | null): Workspace {
  if (!raw) return structuredClone(EMPTY_WORKSPACE);
  const data: unknown = JSON.parse(raw);
  if (!object(data) || data.version !== 1)
    throw new Error("저장 데이터 형식을 읽을 수 없어요. 기존 데이터는 유지됩니다.");
  for (const key of ["observations", "documents", "templates", "criteria"])
    if (!Array.isArray(data[key]))
      throw new Error("저장 데이터가 손상되었어요. 기존 데이터는 유지됩니다.");
  const observations = (data.observations as unknown[]).every(
    (v) =>
      object(v) &&
      strings(v, [
        "id",
        "classId",
        "className",
        "childId",
        "childName",
        "date",
        "domain",
        "context",
        "fact",
        "createdAt",
      ]) &&
      !!v.id &&
      validDate(v.date as string),
  );
  const documents = (data.documents as unknown[]).every(isSavedDocument);
  const templates = (data.templates as unknown[]).every(
    (v) =>
      object(v) &&
      strings(v, ["id", "name", "text", "style", "summary", "createdAt"]) &&
      Array.isArray(v.headings) &&
      v.headings.every((h) => typeof h === "string"),
  );
  const criteria = (data.criteria as unknown[]).every(
    (v) => object(v) && strings(v, ["id", "label", "terms", "source"]),
  );
  if (!observations || !documents || !templates || !criteria)
    throw new Error("일부 저장 항목을 읽을 수 없어요. 덮어쓰지 않고 중단했습니다.");
  const ids = [
    ...(data.observations as { id: string }[]),
    ...(data.documents as { id: string }[]),
  ].map((v) => v.id);
  if (new Set(ids).size !== ids.length)
    throw new Error("기록·문서 ID가 중복되어 저장을 중단했어요.");
  return data as unknown as Workspace;
}
/**
 * 읽을 때도 쓸 때도 본문을 뺀다 (ADR-013). 예전에는 아동 칸 이름만 지우고 제목 · 사실 · 본문 ·
 * 근거를 그대로 다시 저장했다. 남는 것은 계획안 서버 ID 와 설정뿐이다.
 */
export function readWorkspace() {
  const key = accountStorageKey(KEY);
  const raw = window.localStorage.getItem(key);
  const data = withoutDocumentBodies(parseWorkspace(raw));
  if (raw !== null && raw !== JSON.stringify(data))
    window.localStorage.setItem(key, JSON.stringify(data));
  return data;
}
export function updateWorkspace(update: (data: Workspace) => Workspace) {
  const next = withoutDocumentBodies(update(readWorkspace()));
  const serialized = JSON.stringify(next);
  parseWorkspace(serialized);
  window.localStorage.setItem(accountStorageKey(KEY), serialized);
  window.dispatchEvent(new Event(EVENT));
}
/** 옮기지 못하고 지운 예전 증빙 건수. 숫자만 둔다 — 사람을 식별하지 않는다. 보관함이 한 번 알린다. */
export const DROPPED_IMPORTS = "saessak.legacyImportsDropped";

/** 예전 증빙 하나를 지금의 등록(§11 「증빙 등록」)으로 보낸다. 그때도 교사가 원문 확인을 눌렀다. */
function importLegacy(doc: SavedDocument) {
  if (!isSavedDocument(doc) || !isRecordKind(doc.kind)) throw new Error("옮길 수 없는 문서");
  return importDocument({
    kind: doc.kind,
    classId: doc.classId,
    // 일일 · 주간 보육일지는 반 단위 문서다 — 서버가 아동을 받지 않는다.
    childId: doc.kind === "dailyLog" || doc.kind === "weeklyLog" ? "" : doc.childId,
    start: doc.start,
    end: doc.end,
    title: doc.title.slice(0, 200),
    body: doc.sections.map((s) => s.body).join("\n\n"),
  });
}

/**
 * 예전에 이 브라우저에만 저장했던 증빙(IMPORT)을 서버로 옮긴다 (ADR-013).
 *
 * 로그인 · 원 복구 뒤에 한 번 부른다 — 반 · 아동 서버 번호가 그때 있다. 한 건씩 올리고 그때마다
 * 지운다. 중간에 끊겨도 다음 로그인에 같은 문서를 두 번 올리지 않는다. 못 올린 것도 지우고
 * 건수만 남긴다 — 실명이 든 본문을 브라우저에 계속 둘 수는 없다. 교사는 원본 파일로 다시 올린다.
 */
export async function moveLegacyImports() {
  const key = accountStorageKey(KEY);
  let pending: SavedDocument[] = [];
  try {
    pending = JSON.parse(window.localStorage.getItem(key) ?? "{}").documents.filter(
      (d: SavedDocument) => d?.origin === "import",
    );
  } catch {}
  let dropped = 0;
  for (const doc of pending) {
    try {
      await importLegacy(doc);
    } catch {
      dropped += 1;
    }
    const data = JSON.parse(window.localStorage.getItem(key) ?? "{}");
    const documents = Array.isArray(data?.documents)
      ? data.documents.filter((d: SavedDocument) => d?.id !== doc.id)
      : [];
    window.localStorage.setItem(
      key,
      JSON.stringify(withoutDocumentBodies({ ...data, documents }, true)),
    );
  }
  if (dropped) window.sessionStorage.setItem(DROPPED_IMPORTS, String(dropped));
}

export function useWorkspace() {
  const [data, setData] = useState<Workspace>(EMPTY_WORKSPACE);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [saveError, setSaveError] = useState("");
  useEffect(() => {
    const sync = () => {
      try {
        setData(readWorkspace());
        setError("");
      } catch (e) {
        setError(e instanceof Error ? e.message : "저장소를 읽을 수 없어요.");
      } finally {
        setReady(true);
      }
    };
    sync();
    window.addEventListener(EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);
  function save(update: (data: Workspace) => Workspace) {
    try {
      updateWorkspace(update);
      setSaveError("");
      return true;
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "저장 공간이 부족하거나 저장이 차단되었어요.");
      return false;
    }
  }
  return { data, ready, error: error || saveError, blocked: !!error, save };
}
