import { ageRangePayload } from "./age-adapter";
import { API_STORAGE_CONTEXT } from "./storage-context";
import { accountStorageKey, readAccountStorageKey } from "../auth/demo-session";
import { isApiNotFound } from "./client";
import { getMe } from "./auth";
import { createCenter, joinCenter } from "./centers";
import { createClass, getClasses } from "./classes";
import { createChild, getChildren, deleteChild } from "./children";
import { normalizeProvince } from "../onboarding/regions";
import type { ClassSettings, ClassroomEntry, ChildEntry } from "../onboarding/types";
/** 서버에서 받아온 연결이라는 표시. 화면이 그 내용을 들고 있지 않아 서명을 만들 수 없다. */
const ADOPTED = "adopted";

interface Binding {
  id: number;
  signature: string;
}
interface Links {
  center?: Binding;
  classes: Record<string, Binding>;
  children: Record<string, number>;
  /**
   * 버려진 서버 반 id.
   *
   * 반 정보를 고치면 `syncClassOnce` 가 **반을 새로 만든다** — 서버에 수정 API 가
   * 없어서다(P0). 그래서 고친 횟수만큼 옛 행이 서버에 남는다. 이걸 적어두지 않으면
   * `adoptServerClasses` 가 옛 행을 「서버에만 있는 반」으로 보고 다시 들인다.
   */
  retired?: number[];
}
const LINKS_KEY = "saessak.apiLinks.v1:" + API_STORAGE_CONTEXT;
function readLinks(): Links {
  const raw = localStorage.getItem(accountStorageKey(LINKS_KEY));
  if (!raw) return { classes: {}, children: {} };
  const v = JSON.parse(raw);
  if (!v || !v.classes || !v.children) throw new Error("API 연결 정보를 읽지 못했습니다.");
  return Array.isArray(v.retired) ? v : { ...v, retired: undefined };
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

/**
 * 연결이 없는 서버 id 를 화면용 id 로 쓸 때의 접두사.
 *
 * `documents.ts` · `observations.ts` 가 기록을 화면 모양으로 바꿀 때 쓰고,
 * `adoptServerClasses` 가 반을 들일 때도 **같은 규칙**을 쓴다. 한쪽만 다르면
 * 같은 반이 `server-class:7` 과 `api-class-7` 두 개로 갈려서, 기록이 먼저 도착한
 * 화면에서는 그 반을 골라도 기록이 하나도 안 보인다.
 */
export const CLASS_PREFIX = "server-class:";
export const CHILD_PREFIX = "server-child:";

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
  // **서버에서 받아온 원은 그대로 쓴다.** 초대받았거나 기기를 바꾼 교사는 원 정보를
  // 화면에 들고 있지 않아 서명이 영영 안 맞는다. 그때마다 원을 새로 만들면 원이 쌓이고
  // (서버가 거절하기도 한다) links.classes 까지 비워서 방금 들인 반이 날아간다.
  // 그 교사의 원 정보 수정은 서버에 반영되지 않는다 — 원 수정 API 가 생겨야 풀린다.
  if (links.center?.signature === ADOPTED) return links.center.id;
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
  // 화면이 지역을 정식 이름으로 바꿔 쓴다(「강원」 → 「강원특별자치도」). 서명도 같은 값으로 만든다.
  const data = {
    name: center.name,
    director_name: center.director_name,
    region_sido: normalizeProvince(center.region_sido).trim(),
    region_sigungu: center.region_sigungu.trim(),
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
    regionProvince: data.region_sido,
    regionDistrict: data.region_sigungu,
  };
}
async function syncClassOnce(settings: ClassSettings, c: ClassroomEntry) {
  const center = await syncCenter(settings),
    links = readLinks();
  const data = classPayload(c),
    signature = JSON.stringify(data);
  if (links.classes[c.id]?.signature === signature) return links.classes[c.id].id;
  // 새 반을 만들어 갈아끼우므로 옛 행은 버려진다. 적어두지 않으면 다음 방문에
  // adoptServerClasses 가 그걸 「서버에만 있는 반」으로 보고 다시 들인다.
  const replaced = links.classes[c.id]?.id;
  if (replaced) links.retired = [...(links.retired ?? []), replaced];
  for (const child of c.children) delete links.children[child.id];
  const created = await createClass(center, data);
  links.classes[c.id] = { id: created.id, signature };
  saveLinks(links);
  return created.id;
}
/** 반 하나를 서버에 보낼 모양. **서명도 이 값으로 만든다** — 두 군데서 다르게
 *  계산하면 어긋나는 순간 같은 반이 하나 더 만들어진다. */
function classPayload(c: ClassroomEntry) {
  return {
    name: c.className,
    teacher_name: c.teacherName,
    ...ageRangePayload(c),
    child_count: c.currentChildCount === "" ? null : c.currentChildCount,
    // 동의 체크가 켜져 있을 때만 서버가 consent_confirmed_at 에 시각을 남긴다(§2).
    consent_confirmed: c.guardianConsent,
  };
}
function classSignature(c: ClassroomEntry) {
  return JSON.stringify(classPayload(c));
}

export async function syncClasses(settings: ClassSettings) {
  for (const c of settings.classes) await syncClass(settings, c);
}
/**
 * 서버에만 있는 반을 목록에 들인다 — 저장소가 비어 있어도 반이 보이게 한다.
 *
 * **왜 필요한가.** 지금 반 목록은 브라우저 저장소에서 나온다(`loadClassSettings`).
 * 그래서 아래 두 경우에 반이 하나도 안 보인다. 서버에는 멀쩡히 있는데도.
 *
 *   초대받은 교사   §1-1 로 같은 원에 들어왔지만 그 사람 저장소는 비어 있다
 *   기기를 바꾼 교사  새 노트북 · 캐시 삭제 · 다른 브라우저
 *
 * `loadServerClasses` 는 **이미 로컬에 있는 반**의 내용만 서버 값으로 덮어쓴다.
 * 서버에만 있는 반은 들이지 않는다 — 그 자리를 이 함수가 채운다.
 *
 * **서명을 같이 계산해 넣는다.** 안 넣으면 교사가 나중에 반 정보를 고칠 때
 * `syncClass` 의 서명 비교가 어긋나서 **서버에 같은 반이 하나 더 만들어진다.**
 */
export async function adoptServerClasses(
  known: ClassroomEntry[],
  onRosterError?: (className: string) => void,
): Promise<ClassroomEntry[]> {
  const me = await getMe();
  if (!me.center_id) return [];
  const { items } = await getClasses(me.center_id);
  const links = readLinks();
  const linked = new Set(known.map((c) => links.classes[c.id]?.id).filter(Boolean));
  // 원 연결을 서버 값으로 만들어 둔다. 없으면 syncCenter 가 원을 새로 만들면서
  // links.classes · links.children 을 통째로 비운다.
  if (!links.center) links.center = { id: me.center_id, signature: ADOPTED };
  const retired = new Set(links.retired ?? []);
  const adopted: ClassroomEntry[] = [];
  for (const item of items) {
    if (linked.has(item.id) || retired.has(item.id)) continue;
    // **연결은 있는데 목록에 없는 반은 교사가 지운 것이다.** removeClass 는 로컬 목록만
    // 지우고 연결은 남긴다. 여기서 다시 들이면 지운 반이 되살아난다.
    if (classLocalId(item.id)) continue;
    // 서버는 연령을 범위로만 들고 있다. 「만3·만5」처럼 떨어진 선택은 서버에 없다
    // (age-adapter 참고). 로컬에 아무것도 없는 반이라 범위를 그대로 쓴다.
    const selectedAges = ([3, 4, 5] as const).filter(
      (age) => age >= item.age_min && age <= item.age_max,
    );
    const entry: ClassroomEntry = {
      // 기록 쪽(documents.ts · observations.ts)이 연결 없는 서버 id 를 푸는 규칙과 같아야
      // 한다. 다르면 기록이 먼저 도착한 화면에서 그 반을 골라도 기록이 안 보인다.
      id: CLASS_PREFIX + item.id,
      className: item.name,
      ageGroup: "",
      selectedAges: [...selectedAges],
      currentChildCount: item.child_count ?? "",
      teacherName: item.teacher_name,
      guardianConsent: item.consent_confirmed_at !== null,
      childrenSkipped: false,
      children: [],
    };
    links.classes[entry.id] = { id: item.id, signature: classSignature(entry) };
    adopted.push(entry);
  }
  saveLinks(links); // 들인 반이 없어도 원 연결은 남긴다
  if (!adopted.length) return [];
  // 아동 명단은 links 를 저장한 뒤에 받는다 — loadServerChildren 이 그 연결을 본다.
  // 한 반의 명단을 못 받아도 나머지 반은 보여준다 — 하나가 막아서 전부 사라지면
  // 저장소가 빈 교사에게는 화면이 통째로 빈다 (frontend/CLAUDE.md 오류 표시 규칙).
  const filled: ClassroomEntry[] = [];
  for (const entry of adopted) {
    try {
      filled.push(await loadServerChildren(entry));
    } catch {
      // 명단만 비는 것과 진짜 아이가 없는 것을 교사가 구분할 수 있어야 한다.
      onRosterError?.(entry.className);
      filled.push(entry);
    }
  }
  return filled;
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
      CHILD_PREFIX + child.id,
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
    localId = CHILD_PREFIX + child.id;
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
