import { redirect } from "next/navigation";

/**
 * 옛 주소. canonical 은 `/routines?date=&class_id=` 다 (screen-spec S-J1).
 *
 * 두 주소가 같은 화면을 그리면 어느 쪽이 계약인지 흐려진다. 한 번만 보내고 끝낸다 —
 * 되돌려 보내지 않으므로 고리가 생기지 않는다 (frontend/CLAUDE.md 라우팅).
 */
export default async function LegacyRoutinesPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(await searchParams))
    if (typeof value === "string") query.set(key, value);
  const text = query.toString();
  redirect(text ? `/routines?${text}` : "/routines");
}
