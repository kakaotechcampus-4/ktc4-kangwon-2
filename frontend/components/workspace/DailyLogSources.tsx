"use client";
import Link from "next/link";
import type { RoutineSource as Routine } from "@/lib/api/routine-sources";
import { Empty, ws } from "./WorkspaceUI";
import { WorkspaceViewState, type ViewStatus } from "./WorkspaceViewState";

/**
 * 일일 보육일지의 근거 고르기 (docs/screen-spec.md S-J2 · 시안 A).
 *
 * **고른 순서가 그대로 「사실」의 순서다.** 그래서 고른 줄마다 몇 번째인지 붙인다.
 * **활동실행이 빈 줄은 숨기지 않는다** — 숨기면 교사가 「내가 적은 줄이 왜 없지」 한다.
 * 회색으로 두고 이유와 적으러 가는 길을 옆에 둔다.
 */
export default function DailyLogSources({
  status,
  error,
  routines,
  selected,
  busy,
  writeHref,
  onToggle,
  onSelectAll,
}: {
  status: ViewStatus;
  error: string;
  routines: Routine[];
  selected: string[];
  busy: boolean;
  /** 일과 기록(S-J1)으로 가는 주소. 날짜 · 반이 같이 넘어간다. */
  writeHref: string | null;
  onToggle: (id: string, checked: boolean) => void;
  /** 다 골랐으면 모두 풀고, 아니면 활동실행이 있는 줄을 모두 고른다. */
  onSelectAll: () => void;
}) {
  const usable = routines.filter((r) => r.execution);
  return (
    <section className={ws.card}>
      <div className={ws.between}>
        <h2>문서에 사용할 일과</h2>
        <span className={ws.badge}>{selected.length}줄 선택</span>
      </div>
      <p className={ws.hint}>선택한 순서대로 「사실」 칸에 들어가요. 입력한 글은 그대로 옮겨요.</p>
      <WorkspaceViewState
        status={status}
        error={error}
        loading="그날 일과를 불러오고 있어요."
        empty={!usable.length && <NothingToPick total={routines.length} writeHref={writeHref} />}
      >
        {busy && (
          <div className={ws.loading} role="status" aria-busy="true">
            <span>🌱</span>
            <p>보육일지 초안을 작성하고 있어요. 30초쯤 걸려요.</p>
          </div>
        )}
        <button type="button" disabled={busy} className={ws.secondary} onClick={onSelectAll}>
          {selected.length === usable.length ? "선택 해제" : "모두 선택"}
        </button>
        <div role="group" aria-label="문서에 사용할 일과" className={ws.scroll}>
          {routines.map((r) => (
            <RoutineRow
              key={r.id}
              routine={r}
              order={selected.indexOf(r.id) + 1}
              busy={busy}
              writeHref={writeHref}
              onToggle={onToggle}
            />
          ))}
        </div>
      </WorkspaceViewState>
    </section>
  );
}

/** 고를 수 있는 일과가 0개. 줄이 아예 없을 때와 활동실행이 전부 비었을 때 둘 다다. */
function NothingToPick({ total, writeHref }: { total: number; writeHref: string | null }) {
  return (
    <Empty title="선택할 수 있는 일과가 없어요">
      {total
        ? `일과 ${total}줄이 있지만 활동실행이 모두 비어 있어요. `
        : "이 날 입력한 일과가 없어요. "}
      {writeHref && <Link href={writeHref}>일과 기록 입력 →</Link>}
    </Empty>
  );
}

function RoutineRow({
  routine,
  order,
  busy,
  writeHref,
  onToggle,
}: {
  routine: Routine;
  /** 고른 순서. 안 골랐으면 0. */
  order: number;
  busy: boolean;
  writeHref: string | null;
  onToggle: (id: string, checked: boolean) => void;
}) {
  const heading = [routine.time, routine.name].filter(Boolean).join("  ");
  if (!routine.execution)
    return (
      <div className={ws.check}>
        <input
          type="checkbox"
          disabled
          aria-label={`${routine.name} — 활동실행이 비어 있어 선택할 수 없어요`}
        />
        <span>
          <b>{heading}</b>
          <small>
            활동실행이 비어 있어요{" "}
            {writeHref && (
              <>
                · <Link href={writeHref}>입력하기</Link>
              </>
            )}
          </small>
        </span>
      </div>
    );
  return (
    <label className={`${ws.check} ${order ? ws.selected : ""}`}>
      <input
        type="checkbox"
        disabled={busy}
        checked={order > 0}
        onChange={(e) => onToggle(routine.id, e.target.checked)}
      />
      <span>
        <b>
          {heading} {order > 0 && <span className={ws.badge}>{order}번째</span>}
        </b>
        <small>{routine.execution}</small>
      </span>
    </label>
  );
}
