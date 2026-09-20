"use client";
import { useEffect, useState } from "react";
import { EMPTY_WORKSPACE, isSavedDocument, validDate, type Workspace } from "./model";
import { accountStorageKey } from "../auth/demo-session";
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
export function readWorkspace() {
  return parseWorkspace(window.localStorage.getItem(accountStorageKey(KEY)));
}
export function updateWorkspace(update: (data: Workspace) => Workspace) {
  const next = update(readWorkspace());
  const serialized = JSON.stringify(next);
  parseWorkspace(serialized);
  window.localStorage.setItem(accountStorageKey(KEY), serialized);
  window.dispatchEvent(new Event(EVENT));
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
