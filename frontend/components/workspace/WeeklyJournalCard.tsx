"use client";

import { useEffect, useState } from "react";
import { createDocument, listDocuments, type DocumentSummary } from "@/lib/api/documents";
import { routineLocalId, type ApiRoutine } from "@/lib/api/routines";
import { classServerId } from "@/lib/api/onboarding";
import { Message } from "./WorkspaceUI";
import { Icon } from "@/components/app/icons";
import DocumentEditor from "./DocumentEditor";
import { useServerDocument } from "./use-server-document";

type From = "dailyLog" | "routine";

const LABEL: Record<From, string> = {
  dailyLog: "확정한 일일 보육일지",
  routine: "일과 기록",
};

/** 그 주에 든 문서. 주간 일지는 월~일 또는 월~금으로 만들어 시작일로 본다. */
const inWeek = (doc: DocumentSummary, start: string, end: string) =>
  doc.start >= start && doc.start <= end;

/**
 * 이번 주 주간 보육일지 — 주간 기록 화면 안에서 만들고 연다.
 *
 * 주간 일지의 단위는 한 주다. 그 주를 펴 놓은 화면이 이 일지의 주인이고, 문서 보관함은
 * 만든 뒤 쌓이는 곳이다. 그래서 여기서 근거 종류를 고르고 초안까지 만든다.
 *
 * **근거는 관찰 기록이 아니다**(api-spec §11). 확정한 일일 보육일지가 기본이고,
 * 일일을 쓰지 않는 원만 그 주 일과 기록을 바로 받는다. 둘 중 하나지 섞지 않는다.
 */
/**
 * 칸과 화면 머리의 단추가 **같은 상태**를 본다. 단추는 제목 옆에 있어야 하고(WorkspacePage 의
 * `action`), 근거 고르기와 상태는 칸에 있어야 해서 둘로 나뉘었다.
 */
export function useWeeklyJournal({
  classId,
  weekStart,
  weekEnd,
  routines,
}: {
  classId: string;
  weekStart: string;
  weekEnd: string;
  /** 그 주 일과 기록. 주간 기록 화면이 이미 받아 둔 것을 그대로 쓴다. */
  routines: ApiRoutine[];
}) {
  const [journal, setJournal] = useState<DocumentSummary | null | undefined>(undefined);
  const [dailyLogs, setDailyLogs] = useState<DocumentSummary[]>([]);
  const [from, setFrom] = useState<From>("dailyLog");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  // 펴 놓은 일지. 만들면 바로 펴고, 교사가 접으면 주간 띠가 다시 올라온다.
  const [openId, setOpenId] = useState("");

  const serverClass = classServerId(classId);

  useEffect(() => {
    if (!weekStart || serverClass === null) return;
    let live = true;
    Promise.all([
      listDocuments({ kind: "weeklyLog", class_id: serverClass }),
      listDocuments({ kind: "dailyLog", class_id: serverClass, status: "CONFIRMED" }),
    ])
      .then(([weeklies, dailies]) => {
        if (!live) return;
        setJournal(weeklies.find((d) => inWeek(d, weekStart, weekEnd)) ?? null);
        setDailyLogs(dailies.filter((d) => inWeek(d, weekStart, weekEnd)));
        setError("");
      })
      .catch((e) => {
        if (!live) return;
        setJournal(null);
        setError(e instanceof Error ? e.message : "주간 일지를 불러오지 못했습니다.");
      });
    return () => {
      live = false;
    };
  }, [serverClass, weekStart, weekEnd, reload]);

  // 활동실행이 빈 일과는 서버가 근거로 받지 않는다 (§11).
  const routineSources = routines.filter((r) => r.execution).map((r) => routineLocalId(r.id));
  const sources = from === "routine" ? routineSources : dailyLogs.map((d) => d.id);

  async function make() {
    if (busy || !sources.length) return;
    setBusy(true);
    setError("");
    try {
      const made = await createDocument({
        kind: "weeklyLog",
        classId,
        childId: "",
        start: weekStart,
        end: weekEnd,
        sourceIds: sources,
        sourceKind: from,
      });
      setOpenId(made.id);
      setReload((n) => n + 1);
      setBusy(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "초안을 만들지 못했습니다.");
      setBusy(false);
    }
  }

  return {
    /** 그 주 일지. `undefined` 는 아직 불러오는 중, `null` 은 없다. */
    doc: journal,
    from,
    setFrom,
    dailyLogs,
    routineSources,
    sources,
    busy,
    error,
    make,
    openId,
    open: (id: string) => setOpenId(id),
    close: () => setOpenId(""),
    retry: () => setReload((n) => n + 1),
    /** 반을 서버에서 못 찾으면 이 화면에서 할 수 있는 일이 없다. */
    off: serverClass === null || !weekStart,
  };
}

export type WeeklyJournal = ReturnType<typeof useWeeklyJournal>;

export default function WeeklyJournalCard({
  state,
  className,
  weekStart,
  weekEnd,
}: {
  state: WeeklyJournal;
  className: string;
  weekStart: string;
  weekEnd: string;
}) {
  const { doc: journal, from, setFrom, dailyLogs, routineSources, sources, busy, error } = state;
  // 일지는 이 화면에서 끝까지 쓴다 — 문서 보관함은 다 쓴 문서가 쌓이는 곳이지 쓰는 곳이 아니다.
  const edit = useServerDocument(state.openId, {
    onChanged: state.retry,
    // 지운 문서를 편집기에 남겨 두면 저장할 수 없는 칸만 보인다.
    onRemoved: state.close,
  });
  if (state.off) return null;
  const open = !!state.openId;

  return (
    <section className="mb-6 rounded-sm border border-line bg-paper p-5 shadow-pg-card">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold">
            이번 주 주간 보육일지
            <span className="ml-2 text-xs font-normal text-ink-soft">
              {className} · {weekStart.slice(5).replace("-", "/")} –{" "}
              {weekEnd.slice(5).replace("-", "/")}
            </span>
          </h2>
          {journal === undefined ? (
            <p className="mt-1 text-xs text-ink-soft">불러오는 중…</p>
          ) : journal ? (
            <p className="mt-1 text-xs text-ink-soft">
              {journal.status === "confirmed" ? "확정했습니다." : "초안까지 만들었습니다."}
              {journal.stale && " 근거가 바뀌어 다시 볼 것이 있습니다."}
            </p>
          ) : (
            <p className="mt-1 text-xs text-ink-soft">아직 만들지 않았습니다.</p>
          )}
        </div>

        {journal ? (
          <button
            type="button"
            onClick={() => (open ? state.close() : state.open(journal.id))}
            className="inline-flex min-h-11 items-center gap-2 rounded-md border border-primary-tint-line bg-primary-tint px-3 text-xs font-semibold text-primary-ink"
          >
            <Icon name="doc" className="h-4 w-4" />
            {open ? "접기" : journal.status === "confirmed" ? "일지 보기" : "이어서 쓰기"}
          </button>
        ) : journal === null ? (
          <label className="flex items-center gap-2 text-xs text-ink-soft">
            근거
            <select
              value={from}
              disabled={busy}
              onChange={(e) => setFrom(e.target.value as From)}
              className="min-h-11 rounded-md border border-line bg-paper px-2 text-xs text-ink"
            >
              <option value="dailyLog">
                {LABEL.dailyLog} {dailyLogs.length}건
              </option>
              <option value="routine">
                {LABEL.routine} {routineSources.length}건
              </option>
            </select>
          </label>
        ) : null}
      </div>

      {journal === null && !sources.length && (
        <p className="mt-3 text-xs text-ink-soft">
          {from === "dailyLog"
            ? "이 주에 확정한 일일 보육일지가 없습니다. 일일 보육일지를 쓰지 않는 원이면 근거를 「일과 기록」으로 바꿔 주세요."
            : "이 주 일과 기록에 「실제로 한 것」이 하나도 없습니다. 일과 기록을 먼저 적어 주세요."}
        </p>
      )}
      {error && (
        <div className="mt-3">
          <Message error>{error}</Message>
          <button type="button" className="text-xs font-semibold text-primary" onClick={state.retry}>
            다시 불러오기
          </button>
        </div>
      )}

      {open && (
        <div className="mt-5 border-t border-line pt-5">
          <Message error={edit.status === "error"}>
            {edit.status === "error" ? edit.error : edit.status === "loading" ? "일지를 불러오는 중…" : ""}
          </Message>
          {edit.doc && (
            <DocumentEditor
              key={edit.doc.id}
              initial={edit.doc}
              server={edit.server}
              /* 서버 문서는 편집기가 서버에 바로 쓴다. 브라우저 저장소로 가는 길은 쓰지 않는다. */
              onSave={() => true}
            />
          )}
        </div>
      )}
    </section>
  );
}
