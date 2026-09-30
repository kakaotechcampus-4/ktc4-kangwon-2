import { ageRangePayload } from "./age-adapter";
import { API_STORAGE_CONTEXT } from "./storage-context";
import { accountStorageKey } from "../auth/demo-session";
import { isApiNotFound } from "./client";
import { createCenter } from "./centers";
import { createClass, getClasses } from "./classes";
import { createChild, getChildren, deleteChild } from "./children";
import type { ClassSettings, ClassroomEntry, ChildEntry } from "../onboarding/types";
interface Binding {
  id: number;
  signature: string;
}
interface Links {
  center?: Binding;
  classes: Record<string, Binding>;
  children: Record<string, number>;
}
function readLinks(): Links {
  const raw = localStorage.getItem(accountStorageKey("saessak.apiLinks.v1:" + API_STORAGE_CONTEXT));
  if (!raw) return { classes: {}, children: {} };
  const v = JSON.parse(raw);
  if (!v || !v.classes || !v.children) throw new Error("API 연결 정보를 읽지 못했습니다.");
  return v;
}
function saveLinks(v: Links) {
  localStorage.setItem(
    accountStorageKey("saessak.apiLinks.v1:" + API_STORAGE_CONTEXT),
    JSON.stringify(v),
  );
}
async function syncCenterOnce(settings: ClassSettings) {
  // 지역은 붙이지 않고 두 칸 그대로 보낸다 — 서버가 region_sido · region_sigungu 로 받는다(§1).
  const data = {
      name: settings.orgName,
      director_name: settings.directorName,
      region_sido: settings.regionProvince.trim(),
      region_sigungu: settings.regionDistrict.trim(),
    },
    signature = JSON.stringify(data),
    links = readLinks();
  if (links.center?.signature === signature) return links.center.id;
  // P0 has no center update endpoint: retain old server objects, create a new snapshot.
  const center = await createCenter(data);
  links.center = { id: center.id, signature };
  links.classes = {};
  links.children = {};
  saveLinks(links);
  return center.id;
}
async function syncClassOnce(settings: ClassSettings, c: ClassroomEntry) {
  const center = await syncCenter(settings),
    links = readLinks();
  const data = {
      name: c.className,
      teacher_name: c.teacherName,
      ...ageRangePayload(c),
      child_count: c.currentChildCount === "" ? null : c.currentChildCount,
      // 동의 체크가 켜져 있을 때만 서버가 consent_confirmed_at 에 시각을 남긴다(§2).
      consent_confirmed: c.guardianConsent,
    },
    signature = JSON.stringify(data);
  if (links.classes[c.id]?.signature === signature) return links.classes[c.id].id;
  for (const child of c.children) delete links.children[child.id];
  const created = await createClass(center, data);
  links.classes[c.id] = { id: created.id, signature };
  saveLinks(links);
  return created.id;
}
export async function syncClasses(settings: ClassSettings) {
  for (const c of settings.classes) await syncClass(settings, c);
}
export async function loadServerClasses(settings: ClassSettings) {
  const links = readLinks();
  if (!links.center) return settings;
  const { items } = await getClasses(links.center.id);
  // Keep local IDs for existing records/documents. Only mapped current snapshots are shown.
  return {
    ...settings,
    classes: settings.classes
      .filter(
        (c) => !links.classes[c.id] || items.some((item) => item.id === links.classes[c.id].id),
      )
      .map((c) => {
        const item = items.find((i) => i.id === links.classes[c.id]?.id);
        return item
          ? {
              ...c,
              className: item.name,
              teacherName: item.teacher_name,
              currentChildCount: item.child_count ?? ("" as const),
              // 동의는 서버의 consent_confirmed_at 이 정한다. 「나중에 입력할래요」로
              // 아동이 0명인 반도 다시 들어왔을 때 체크가 풀리지 않는다 (api-spec §2).
              guardianConsent: item.consent_confirmed_at !== null,
            }
          : c;
      }),
  };
}
export async function loadServerChildren(c: ClassroomEntry): Promise<ClassroomEntry> {
  const links = readLinks(),
    id = links.classes[c.id]?.id;
  if (!id) return c;
  let items: Awaited<ReturnType<typeof getChildren>>["items"];
  try {
    ({ items } = await getChildren(id));
  } catch (e) {
    // 실제 API가 준 JSON NOT_FOUND일 때만 오래된 연결 정보로 보고 정리한다.
    // MswTransportError(Next HTML 404 = MSW 미동작)는 데이터 없음이 아니므로 그대로 위로 던진다.
    if (isApiNotFound(e)) {
      delete links.classes[c.id];
      saveLinks(links);
      return c;
    }
    throw e;
  }
  const children = items.map((child) => ({
    id:
      Object.keys(links.children).find((k) => links.children[k] === child.id) ||
      "api-child-" + child.id,
    name: child.name,
    code: child.code,
  }));
  for (let i = 0; i < items.length; i++) links.children[children[i].id] = items[i].id;
  saveLinks(links);
  // 동의 여부를 아동 수로 추론하지 않는다 — 0명이어도 동의는 유지된다.
  // 서버의 consent_confirmed_at 은 loadServerClasses 가 이미 반영했다.
  return { ...c, children };
}
export async function addServerChild(c: ClassroomEntry, name: string): Promise<ChildEntry> {
  const links = readLinks(),
    id = links.classes[c.id]?.id;
  if (!id) throw new Error("반 정보를 먼저 저장해주세요.");
  const child = await createChild(id, { name }),
    localId = "api-child-" + child.id;
  links.children[localId] = child.id;
  saveLinks(links);
  return { id: localId, name: child.name, code: child.code };
}
export async function removeServerChild(id: string) {
  const links = readLinks(),
    serverId = links.children[id];
  if (serverId) await deleteChild(serverId);
  delete links.children[id];
  saveLinks(links);
}
const consent = new Set<string>();
export function rememberConsent(classes: ClassroomEntry[]) {
  for (const c of classes) {
    if (c.guardianConsent) consent.add(c.id);
    else consent.delete(c.id);
  }
}
export const hasConsent = (id: string) => consent.has(id);
async function migrateChildrenOnce(c: ClassroomEntry) {
  const links = readLinks();
  for (const child of c.children)
    if (!links.children[child.id]) {
      const server = await createChild(links.classes[c.id].id, { name: child.name });
      links.children[child.id] = server.id;
      saveLinks(links);
    }
}

const pending = new Map<string, Promise<unknown>>();
function once<T>(operation: string, input: unknown, run: () => Promise<T>): Promise<T> {
  const key =
    accountStorageKey("saessak.api:" + API_STORAGE_CONTEXT) + operation + JSON.stringify(input);
  const current = pending.get(key);
  if (current) return current as Promise<T>;
  const result = run().finally(() => pending.delete(key));
  pending.set(key, result);
  return result;
}
export function syncCenter(s: ClassSettings) {
  return once("center", [s.orgName, s.directorName, s.regionProvince, s.regionDistrict], () =>
    syncCenterOnce(s),
  );
}
export function syncClass(s: ClassSettings, c: ClassroomEntry) {
  return once(
    "class",
    [
      s.orgName,
      s.directorName,
      s.regionProvince,
      s.regionDistrict,
      c.id,
      c.className,
      c.teacherName,
      c.selectedAges,
      c.ageGroup,
      c.currentChildCount,
      c.guardianConsent,
    ],
    () => syncClassOnce(s, c),
  );
}
export function migrateChildren(c: ClassroomEntry) {
  return once("children", c.id, () => migrateChildrenOnce(c));
}
