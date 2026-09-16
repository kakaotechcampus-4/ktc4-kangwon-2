import { read, commit } from "./store";
// TODO(BE): 실제 더미 이름 풀/중복 규칙 미확정. 실명에서 파생하지 않는 mock 전용 코드.
const codes = ["가람", "보람", "다솔", "나봄", "여름", "새봄"];
export const listChildren = (id: number) => read().children.filter((c) => c.class_id === id);
export const hasChild = (id: number) => read().children.some((c) => c.id === id);
export const addChild = (id: number, name: string) =>
  commit((db) => {
    const child = {
      id: db.next++,
      class_id: id,
      name,
      code: codes[db.children.length % codes.length],
      created_at: new Date().toISOString(),
    };
    db.children.push(child);
    return child;
  });
export const removeChild = (id: number) =>
  commit((db) => {
    db.children = db.children.filter((c) => c.id !== id);
    return null;
  });
