"use client";

import { useState } from "react";
import { createDocument, downloadDocumentBundle, type DocumentSummary } from "@/lib/api/documents";
import { errorCode } from "@/lib/api/client";
import type { ServerObservation } from "@/lib/api/observations";
import { useUnsavedWarning } from "@/lib/hooks/use-unsaved-warning";
import { Message, ws } from "./WorkspaceUI";
import oj from "./ObservationJournal.module.css";

/** 서버와 같은 근거 상한 (backend documents/schemas.py `MAX_SOURCES`). 넘으면 부르지 않는다. */
const MAX_SOURCES = 60;

export interface Kid {
  id: string;
  name: string;
}
export interface DraftRow {
  kid: Kid;
  /** 이 기간 이 아이 기록. 날짜순. */
  records: ServerObservation[];
  /** 이 기간 AI 관찰일지. 초안이 있으면 초안, 없으면 확정본. */
  doc?: DocumentSummary;
  /** 초안을 만든 뒤에 적은 기록 수. */
  fresh: number;
}
/** 반 전체를 도는 동안 아이마다 생긴 일. 문서가 생기면 문서가 상태를 정한다. */
export type Run = { state: "making" } | { state: "failed" | "ask"; note: string };

export type Status =
  "확정" | "초안" | "만드는 중" | "못 만듦" | "물어볼 것" | "검토 못 함" | "기록 없음" | "";

const at = (iso: string) => new Date(iso).getTime();

/** 반 아이 순서 그대로. 같은 아이 · 같은 기간 문서만 본다 — 서버가 초안을 하나로 지키는 단위다. */
export function rowsFor(
  kids: Kid[],
  records: ServerObservation[],
  docs: DocumentSummary[],
  start: string,
  end: string,
): DraftRow[] {
  return kids.map((kid) => {
    const mine = records
      .filter((r) => r.childId === kid.id && r.date >= start && r.date <= end)
      .sort((a, b) => a.date.localeCompare(b.date));
    const same = docs.filter(
      (d) => d.childId === kid.id && d.start === start && d.end === end && d.origin === "ai",
    );
    const doc = same.find((d) => d.status === "draft") ?? same[0];
    const fresh =
      doc?.status === "draft" ? mine.filter((r) => at(r.createdAt) > at(doc.createdAt)).length : 0;
    return { kid, records: mine, doc, fresh };
  });
}

export function statusOf(row: DraftRow, run?: Run): Status {
  if (run?.state === "making") return "만드는 중";
  const { doc } = row;
  if (doc?.status === "confirmed") return "확정";
  if (doc && row.fresh) return "물어볼 것";
  // mock 이거나 검토가 실패했으면 통과처럼 보이지 않게 한다 (ADR-071 결정 7).
  if (doc && (doc.aiReviewState === "mock" || doc.aiReviewState === "failed")) return "검토 못 함";
  if (doc) return "초안";
  if (run?.state === "failed") return "못 만듦";
  if (run?.state === "ask") return "물어볼 것";
  return row.records.length ? "" : "기록 없음";
}

/** 만들 수 있는 아이 — 기록이 있고 이 기간 문서가 아직 없다. */
const makeable = (row: DraftRow) => !row.doc && row.records.length > 0;
/** 기록이 1개뿐이면 체크를 끈 채로 — 한 장면을 기간 일지로 읽게 되기 쉽다. */
const pickedByDefault = (row: DraftRow) => row.records.length >= 2;

/**
 * 반 전체 초안 — 한 번 눌러 기록 있는 아이 전부 (ADR-083).
 *
 * 화면이 아이마다 차례로 부른다. 떠나려 하면 브라우저가 한 번 묻는다. 한도 초과면 남은 아이를
 * 부르지 않는다 — 키가 지워져 다음 호출도 실패한다.
 */
export default function ObservationClassDrafts({
  kids,
  records,
  docs,
  start,
  end,
  classId,
  onOpen,
  onChanged,
  onBusy,
}: {
  kids: Kid[];
  records: ServerObservation[];
  docs: DocumentSummary[];
  start: string;
  end: string;
  classId: string;
  onOpen: (docId: string) => void;
  onChanged: () => void;
  /** 도는 동안 화면이 아이 · 기간 고르기를 잠근다. */
  onBusy?: (on: boolean) => void;
}) {
  const [runs, setRuns] = useState<Record<string, Run>>({});
  const [picks, setPicks] = useState<Record<string, boolean>>({});
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState("");
  useUnsavedWarning(running);
  function hold(on: boolean) {
    setRunning(on);
    onBusy?.(on);
  }

  const rows = rowsFor(kids, records, docs, start, end);
  const picked = (row: DraftRow) => picks[row.kid.id] ?? pickedByDefault(row);
  const queue = rows.filter((row) => makeable(row) && picked(row));
  const confirmed = rows.flatMap((r) => (r.doc?.status === "confirmed" ? [r.doc] : []));
  const ready = confirmed.filter((d) => !d.stale);
  const mark = (id: string, run?: Run) =>
    setRuns((prev) => {
      const next = { ...prev };
      if (run) next[id] = run;
      else delete next[id];
      return next;
    });

  /** 한 아이. 한도 초과면 그 이유를 돌려준다 — 남은 아이를 부르지 않게. */
  async function make(row: DraftRow, replaceDraft = false): Promise<string> {
    if (row.records.length > MAX_SOURCES) {
      mark(row.kid.id, {
        state: "failed",
        note: `기록이 ${MAX_SOURCES}개를 넘어요. 기간을 줄여 주세요.`,
      });
      return "";
    }
    mark(row.kid.id, { state: "making" });
    try {
      await createDocument({
        kind: "observation",
        classId,
        childId: row.kid.id,
        start,
        end,
        sourceIds: row.records.map((r) => r.id),
        replaceDraft,
      });
      mark(row.kid.id);
      onChanged();
      return "";
    } catch (e) {
      const note = e instanceof Error ? e.message : "만들지 못했어요.";
      const code = errorCode(e);
      // 외자 이름처럼 교사가 답해야 풀리는 것 — 다시 눌러도 같다.
      mark(row.kid.id, { state: code === "VALUE_INVALID" ? "ask" : "failed", note });
      return code === "LLM_BUDGET_EXCEEDED" ? note : "";
    }
  }

  async function makeAll() {
    if (running || !queue.length) return;
    hold(true);
    setMessage("");
    let stop = "";
    for (const row of queue) {
      if (stop) mark(row.kid.id, { state: "failed", note: stop });
      else stop = await make(row);
    }
    hold(false);
  }

  async function remake(row: DraftRow) {
    if (running) return;
    hold(true);
    await make(row, true);
    hold(false);
  }

  async function bundle() {
    setMessage("");
    try {
      await downloadDocumentBundle(ready.map((d) => d.id));
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "파일을 받지 못했어요.");
    }
  }

  return (
    <section className={`${ws.card} ${oj.drafts}`} aria-labelledby="oj-class">
      <header className={oj.draftsHead}>
        <h2 id="oj-class">반 전체</h2>
        <div className={oj.draftsActions}>
          <button
            type="button"
            className={ws.primary}
            disabled={running || !queue.length}
            onClick={makeAll}
          >
            {running ? "만드는 중…" : "반 전체 초안 만들기"}
          </button>
          <button
            type="button"
            className={ws.secondary}
            disabled={running || !ready.length}
            onClick={bundle}
          >
            확정 {ready.length}명 한 파일로
          </button>
        </div>
      </header>
      {confirmed.length > ready.length && (
        <p className={oj.draftsNote}>
          {confirmed.length - ready.length}명은 원본 기록이 바뀌어 파일에서 빠져요.
        </p>
      )}
      <Message error>{message}</Message>
      <ul className={oj.draftRows}>
        {rows.map((row) => (
          <ClassDraftRow
            key={row.kid.id}
            row={row}
            run={runs[row.kid.id]}
            picked={picked(row)}
            busy={running}
            onPick={(on) => setPicks((prev) => ({ ...prev, [row.kid.id]: on }))}
            onOpen={onOpen}
            onRemake={() => remake(row)}
          />
        ))}
      </ul>
    </section>
  );
}

function ClassDraftRow({
  row,
  run,
  picked,
  busy,
  onPick,
  onOpen,
  onRemake,
}: {
  row: DraftRow;
  run?: Run;
  picked: boolean;
  busy: boolean;
  onPick: (on: boolean) => void;
  onOpen: (docId: string) => void;
  onRemake: () => void;
}) {
  const status = statusOf(row, run);
  const { doc } = row;
  const note = run && "note" in run ? run.note : "";
  const count = row.records.length;
  return (
    <li className={oj.draftRow} data-status={status || undefined}>
      <label className={oj.draftPick}>
        <input
          type="checkbox"
          aria-label={`${row.kid.name} 초안 만들기`}
          checked={makeable(row) && picked}
          disabled={busy || !makeable(row)}
          onChange={(e) => onPick(e.target.checked)}
        />
      </label>
      {doc ? (
        <button
          type="button"
          className={oj.draftName}
          disabled={busy}
          onClick={() => onOpen(doc.id)}
        >
          {row.kid.name}
        </button>
      ) : (
        <span className={oj.draftName}>{row.kid.name}</span>
      )}
      <small className={oj.draftCount}>{count ? `관찰 ${count}개` : ""}</small>
      <StatusMark status={status} />
      {doc && row.fresh > 0 && (
        <div className={oj.draftAsk}>
          <span>새 기록 {row.fresh}개</span>
          <button type="button" className={ws.link} disabled={busy} onClick={() => onOpen(doc.id)}>
            그대로 열기
          </button>
          <button type="button" className={ws.link} disabled={busy} onClick={onRemake}>
            넣어서 다시
          </button>
        </div>
      )}
      {!doc && note && <p className={oj.draftWhy}>{note}</p>}
    </li>
  );
}

function StatusMark({ status }: { status: Status }) {
  if (!status) return <span className={oj.draftMark} />;
  if (status === "만드는 중")
    return (
      <span className={`${oj.draftMark} ${oj.making}`} role="status">
        <i aria-hidden="true" />
        만드는 중
      </span>
    );
  const stamp = status === "확정" || status === "초안";
  return <span className={`${oj.draftMark} ${stamp ? oj.stamp : oj.tag}`}>{status}</span>;
}
