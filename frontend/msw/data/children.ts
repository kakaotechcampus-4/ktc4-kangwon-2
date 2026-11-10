import { read, commit } from "./store";
// TODO(BE): 실제 더미 이름 풀/중복 규칙 미확정. 실명에서 파생하지 않는 mock 전용 코드.
const codes = ["가람", "보람", "다솔", "나봄", "여름", "새봄"];
export const listChildren = (id: number) => read().children.filter((c) => c.class_id === id);
export const hasChild = (id: number) => read().children.some((c) => c.id === id);
// 외자 판별은 서버가 한다(backend/app/shared/childCode/names.py). 목업은 흔한 성 몇 개만 본다.
const needsCallName = (name: string) =>
  name.length === 2 && "김이박최정강조장임한".includes(name[0]);
export const addChild = (id: number, name: string, callName: string | null = null) =>
  commit((db) => {
    const child = {
      id: db.next++,
      class_id: id,
      name,
      code: codes[db.children.length % codes.length],
      call_name: callName,
      needs_call_name: needsCallName(name),
      created_at: new Date().toISOString(),
    };
    db.children.push(child);
    return child;
  });
export const setCallName = (id: number, callName: string | null) =>
  commit((db) => {
    const child = db.children.find((c) => c.id === id)!;
    child.call_name = callName;
    return child;
  });
export const removeChild = (id: number) =>
  commit((db) => {
    db.children = db.children.filter((c) => c.id !== id);
    return null;
  });
