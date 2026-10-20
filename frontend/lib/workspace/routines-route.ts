/** S-J1 canonical route `/routines?date=&class_id=` 의 양쪽 — 읽는 쪽과 만드는 쪽. */
import { classServerId } from "@/lib/api/onboarding";
import { validDate } from "./model";

/** 고른 반을 서버에서 못 찾았다. 다른 반으로 보내는 대신 이유를 보여준다 (FR-405). */
export const ROUTINES_UNMAPPED =
  "이 반의 서버 정보를 확인할 수 없어 일과 기록으로 갈 수 없어요. 반·아동 관리에서 다시 저장해주세요.";

/** 주소가 가리키는 반·날짜. 반은 **서버 번호**다. 모르는 값은 버린다 — 짐작해서 채우지 않는다. */
export function routinesScope(search: string): { date: string; classId: number | null } {
  const query = new URLSearchParams(search);
  const date = query.get("date") ?? "";
  const asked = Number(query.get("class_id"));
  return {
    date: validDate(date) ? date : "",
    classId: Number.isSafeInteger(asked) && asked > 0 ? asked : null,
  };
}

/**
 * 보고 있던 반·날짜를 들고 S-J1 으로 가는 주소. **고른 반을 서버 번호로 못 바꾸면 `null`** 이다.
 *
 * 「반을 안 골랐다」와 「B 반을 골랐는데 지금 그 반의 서버 번호를 모른다」는 다른 상태다.
 * 번호만 빼고 보내면 S-J1 이 앞의 것으로 읽어 **주 반(A)** 을 연다 — 교사는 B 를 눌렀는데
 * A 가 열린다. 그래서 주소를 아예 만들지 않고, 부르는 쪽이 왜 못 가는지 알린다 (FR-405).
 *
 * 반을 고르지 않았으면(`classLocalId` 가 빈 값) 날짜만 들고 간다 — 그건 정상이다.
 */
export function routinesPath(classLocalId: string, date: string): string | null {
  let serverId: number | null = null;
  if (classLocalId) {
    serverId = classServerId(classLocalId);
    if (serverId === null) return null;
  }
  return `/routines${routinesQuery(serverId, date)}`;
}

/**
 * 서버 번호를 이미 아는 쪽(S-J1 자신)이 쓰는 질의 문자열. 앞에 `?` 가 붙고, 빌 수도 있다.
 *
 * `routinesPath` 와 **같은 순서**로 써야 한다 — 다른 화면이 들려보낸 주소를 S-J1 이
 * 글자만 다르다는 이유로 다시 쓰면 history 가 공연히 한 칸 움직인 것처럼 보인다.
 */
export function routinesQuery(classId: number | null, date: string): string {
  const query = new URLSearchParams();
  if (validDate(date)) query.set("date", date);
  if (classId !== null) query.set("class_id", String(classId));
  const text = query.toString();
  return text ? `?${text}` : "";
}
