import workspace from "@/components/workspace/Workspace.module.css";
import type { PlayMonthlyAuditEvent } from "@/lib/api/types";

const SECTION: Record<string, string> = { together: "함께 하는 활동", free_play: "자유놀이" };
const short = (text: string) => {
  const t = text.trim();
  if (!t) return "(빈 칸)";
  return "「" + (t.length > 30 ? t.slice(0, 30) + "…" : t) + "」";
};
/** 이벤트 하나의 한 줄. 모르는 `type` 은 null 이다 — 건너뛴다. */
function describe(e: PlayMonthlyAuditEvent): string | null {
  const v = e.value_change;
  const change = v ? ` ${short(v.before)} → ${short(v.after)}` : "";
  switch (e.type) {
    case "CREATED":
      return e.scope === "PLAN" ? "계획안을 만들었어요" : "칸을 만들었어요";
    case "TEACHER_EDITED":
      return (e.link_change && !v ? "누리과정 연결을 고쳤어요" : "고쳤어요") + change;
    case "ARRANGEMENT_CHANGED": {
      const a = e.arrangement_change;
      if (!a) return "배치가 바뀌었어요";
      const week = /-W(\d+)$/.exec(a.scope)?.[1];
      return SECTION[a.scope]
        ? `배치가 바뀌었어요 · ${SECTION[a.scope]} ${a.before.length}개 → ${a.after.length}개`
        : `배치가 바뀌었어요 · ${week ? week + "주 " : ""}안전교육`;
    }
    case "CANDIDATE_COPIED":
      return "훈련 후보를 복사했어요" + change;
    case "CONFIRMED":
      return "확정했어요";
    default:
      return null;
  }
}
const when = (at: string) =>
  new Date(at).toLocaleString("ko-KR", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

/**
 * 변경 이력을 시간순으로 보인다(서버가 시간순으로 준다). 만들 때 칸마다 남는 `CREATED` 는 수십 개라 한 줄로 접는다.
 * 시각은 UTC 로 오므로 `new Date` 로 현지로 바꾼다.
 */
export default function PlayMonthlyAuditPanel({ events }: { events: PlayMonthlyAuditEvent[] }) {
  const known = events.filter((e) => describe(e) !== null);
  const cells = known.filter((e) => e.type === "CREATED" && e.scope === "CELL" && !e.actor);
  const rows = known.filter((e) => !cells.includes(e) || e === cells[0]);
  return (
    <ol aria-label="변경 이력">
      {rows.map((e, i) => (
        <li key={i}>
          <time dateTime={e.occurred_at}>{when(e.occurred_at)}</time>{" "}
          {e === cells[0] ? `처음 만들어진 칸 ${cells.length}개` : describe(e)}
        </li>
      ))}
      {!rows.length && <li className={workspace.muted}>아직 이력이 없어요</li>}
    </ol>
  );
}
