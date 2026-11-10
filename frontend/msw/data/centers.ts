import { read, commit } from "./store";
import type { CenterInput, PlanConfig } from "../../lib/api/types";
import type { Greetings, ReflectMark } from "../../lib/api/centers";
import { DEFAULT_CHARACTER_MESSAGES, MONTH_ORDER } from "../../lib/onboarding/types";
export const findCenter = (id: number) => read().centers.find((c) => c.id === id);
export const currentCenterId = () => read().centers[0]?.id ?? null;
const defaultGreetings = (): Greetings => ({
  enabled: false,
  items: MONTH_ORDER.map((month) => ({ month, text: DEFAULT_CHARACTER_MESSAGES[month] })),
});
export const findGreetings = (id: number): Greetings => read().greetings[id] ?? defaultGreetings();
export const putGreetings = (id: number, data: Greetings) =>
  commit((db) => {
    const previous = db.greetings[id] ?? defaultGreetings();
    const next = data.enabled ? data : { ...previous, enabled: false };
    db.greetings[id] = next;
    return next;
  });
/** 트렌드봇 설정. **계정마다 따로 두고 새로고침해도 남는다** — 모듈 전역에 들면
 *  다른 계정이 만든 1번 원이 남의 설정을 물려받는다. */
/**
 * 토요일(`weekly_saturday_enabled`)은 칸이 없으면 꺼진 것이다 — 주간 기본은 월~금 (§3-2).
 * 관찰 축(`observation_axis`)의 기본은 누리과정 5영역이다 (observations/models.py AXES).
 */
const SETTINGS_DEFAULT = {
  trends_enabled: false,
  weekly_saturday_enabled: false,
  observation_axis: "NURI_5" as const,
  reflect_mark: "(반영)" as ReflectMark,
};
/** 목업 계정은 늘 그 원을 만든 교사다 — 원 설정을 바꿀 수 있다 (ADR-087). 저장하지 않는 값이다. */
export const findCenterSettings = (id: number) => ({
  ...SETTINGS_DEFAULT,
  ...read().centerSettings[id],
  can_edit: true,
});
export const putCenterSettings = (
  id: number,
  patch: {
    trends_enabled?: boolean;
    weekly_saturday_enabled?: boolean;
    observation_axis?: "NURI_5" | "DAILY_PLAY_2";
    reflect_mark?: ReflectMark;
  },
) =>
  commit((db) => {
    const next = { ...SETTINGS_DEFAULT, ...db.centerSettings[id], ...patch };
    db.centerSettings[id] = next;
    return { ...next, can_edit: true };
  });
/**
 * 목업 어린이집 목록 (§1 「어린이집 찾기」). 어느 지역을 골라도 같은 일곱 곳이 나온다 —
 * 결과 상자에 다 안 들어가 스크롤되는 모습까지 로컬에서 본다.
 * 진짜 목록은 서버 사본(backend/resources/daycares)이다 — 여기 이름은 지어낸 것이다.
 */
export const mockDaycares = (sido: string, sigungu: string) =>
  [
    "햇살어린이집",
    "달님어린이집",
    "새싹어린이집",
    "별빛어린이집",
    "솔숲어린이집",
    "푸른숲어린이집",
    "꿈나무어린이집",
  ].map((name, i) => ({
    key: [sido, sigungu, name, `${sido} ${sigungu} 목업로 ${i + 1}`].join("|"),
    name,
    kind: i === 0 ? "국공립" : "민간",
    status: "정상",
    address: `${sido} ${sigungu} 목업로 ${i + 1}`,
  }));
/** 원을 만든다. 목록에서 고른 원이면 이름 · 지역을 목록 값으로 둔다 (ADR-068). */
export const addCenter = (data: CenterInput) =>
  commit((db) => {
    const [sido, sigungu, name, address] = data.registry_key?.split("|") ?? [];
    const c = {
      ...data,
      // 화면은 새 원이면 원장 이름을 늘 보낸다 — handlers 가 빈 값을 400 으로 막는다.
      director_name: data.director_name ?? "",
      ...(data.registry_key ? { name, region_sido: sido, region_sigungu: sigungu } : {}),
      registry_key: data.registry_key ?? null,
      kind: data.registry_key ? "민간" : null,
      address: data.registry_key ? address : null,
      teacher_count: 1,
      id: db.next++,
      created_at: new Date().toISOString(),
    };
    db.centers.push(c);
    return c;
  });
export const putConfig = (id: number, data: PlanConfig) =>
  commit((db) => {
    db.configs[id] = data;
    return data;
  });
