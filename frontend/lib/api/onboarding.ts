import { ageRangePayload } from "./age-adapter";
import { API_STORAGE_CONTEXT } from "./storage-context";
import { accountStorageKey, readAccountStorageKey } from "../auth/demo-session";
import { isApiNotFound } from "./client";
import { createCenter, joinCenter } from "./centers";
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
const LINKS_KEY = "saessak.apiLinks.v1:" + API_STORAGE_CONTEXT;
function readLinks(): Links {
  const raw = localStorage.getItem(accountStorageKey(LINKS_KEY));
  if (!raw) return { classes: {}, children: {} };
  const v = JSON.parse(raw);
  if (!v || !v.classes || !v.children) throw new Error("API 연결 정보를 읽지 못했습니다.");
  return v;
}
function saveLinks(v: Links) {
  localStorage.setItem(accountStorageKey(LINKS_KEY), JSON.stringify(v));
}
/**
 * 저장된 Links 를 읽기만 한다. 저장 내용은 못 믿으므로 모양을 확인하고 쓴다.
 *
 * `accountStorageKey` 를 쓰지 않는다 — 그쪽은 세션이 성치 않으면 로그아웃시킨다.
 * id 를 못 찾은 것뿐인데 로그인이 풀리면 안 된다.
 */
function storedLinks(): { classes?: unknown; children?: unknown } | null {
  try {
    const key = readAccountStorageKey(LINKS_KEY);
    const raw = key && localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
// 매핑은 plain object 여야 한다. 배열·문자열은 엉뚱한 own entry(0 · length)를 내놓는다.
const entries = (table: unknown): [string, unknown][] =>
  typeof table === "object" && table !== null && !Array.isArray(table) ? Object.entries(table) : [];
const valueOf = (table: unknown, key: string) => entries(table).find(([name]) => name === key)?.[1];

// 서버 id 는 1 부터 세는 양의 정수다. 그 밖의 값은 매핑이 깨진 것이라 쓰지 않는다.
const serverId = (v: unknown) =>
  typeof v === "number" && Number.isSafeInteger(v) && v > 0 ? v : null;
// 반은 `{ id, signature }` 로 묶여 있다.
const bindingId = (v: unknown) =>
  typeof v === "object" && v !== null ? serverId((v as { id?: unknown }).id) : null;

export const classServerId = (localId: string) =>
  bindingId(valueOf(storedLinks()?.classes, localId));
export const childServerId = (localId: string) =>
  serverId(valueOf(storedLinks()?.children, localId));

export function classLocalId(id: number): string | null {
  return entries(storedLinks()?.classes).find(([, v]) => bindingId(v) === id)?.[0] ?? null;
}
export function childLocalId(id: number): string | null {
  return entries(storedLinks()?.children).find(([, v]) => serverId(v) === id)?.[0] ?? null;
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
/**
 * 초대 코드로 기존 원에 들어간다 (§1-1). 원 정보는 서버 값으로 채우고, syncCenter 가 같은
 * 서명을 보도록 연결해 둔다 — 서명이 다르면 다음 단계에서 원을 새로 만들려다 409 가 난다.
 */
export async function joinCenterByCode(
  settings: ClassSettings,
  code: string,
): Promise<ClassSettings> {
  const center = await joinCenter(code);
  const data = {
    name: center.name,
    director_name: center.director_name,
    region_sido: center.region_sido,
    region_sigungu: center.region_sigungu,
  };
  saveLinks({
    center: { id: center.id, signature: JSON.stringify(data) },
    classes: {},
    children: {},
  });
  return {
    ...settings,
    orgName: center.name,
    directorName: center.director_name,
    regionProvince: center.region_sido,
    regionDistrict: center.region_sigungu,
  };
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
  const account = accountStorageKey(LINKS_KEY);
  const links = readLinks(),
    id = links.classes[c.id]?.id;
  if (!id) return c;
  let items: Awaited<ReturnType<typeof getChildren>>["items"];
  try {
    ({ items } = await getChildren(id));
  } catch (e) {
    // 실제 API가 준 JSON NOT_FOUND일 때만 오래된 연결 정보로 보고 정리한다.
    // MswTransportError(Next HTML 404 = MSW 미동작)는 데이터 없음이 아니므로 그대로 위로 던진다.
    if (readAccountStorageKey(LINKS_KEY) !== account) throw e;
    if (isApiNotFound(e)) {
      delete links.classes[c.id];
      saveLinks(links);
      return c;
    }
    throw e;
  }
  if (readAccountStorageKey(LINKS_KEY) !== account) throw new Error("계정이 변경되었습니다.");
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
  return { ...c, children, childIds: children.map((child) => child.id) };
}

/** 이름은 서버에서 다시 읽고 React state로만 전달한다. */
export async function hydrateClassChildren(settings: ClassSettings): Promise<ClassroomEntry[]> {
  // loadServerChildren이 ID links를 갱신하므로 병렬 write로 다른 반의 매핑을 잃지 않는다.
  const classes: ClassroomEntry[] = [];
  for (const classroom of settings.classes) classes.push(await loadServerChildren(classroom));
  return classes;
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
