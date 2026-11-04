"use client";

import { useEffect, useState } from "react";
import { createDocument, listDocuments, type DocumentSummary } from "@/lib/api/documents";
import { classServerId } from "@/lib/api/onboarding";
import { loadClassSettings } from "@/lib/onboarding/settings";
import { Message, ws } from "./WorkspaceUI";
import DocumentEditor from "./DocumentEditor";
import { useServerDocument } from "./use-server-document";

const NO_CLASS = "반을 서버에서 찾지 못했어요. 페이지를 새로고침해주세요.";

/**
 * 그날의 일일 보육일지 — **일과를 적은 이 화면에서** 만들고 끝까지 쓴다.
 *
 * 전에는 「오늘 일지 만들기」가 문서 보관함으로 보냈다. 보관함은 다 쓴 문서가 쌓이는
 * 곳이지 쓰는 곳이 아니고, 교사는 방금 적은 일과를 눈앞에 두고 일지를 손봐야 한다.
 * 주간 기록 화면이 주간 일지를 그 자리에서 쓰는 것과 같은 짜임이다.
 *
 * 근거는 그날 일과 기록이다 (api-spec §11) — 관찰 기록이 아니다.
 */
export function useDailyJournal({ classId, date }: { classId: number | null; date: string }) {
  const [journal, setJournal] = useState<DocumentSummary | null | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  // 펴 놓은 일지. 만들면 바로 펴고, 교사가 접으면 칠판만 남는다.
  const [openId, setOpenId] = useState("");

  useEffect(() => {
    if (classId === null || !date) return;
    let live = true;
    listDocuments({ kind: "dailyLog", class_id: classId })
      .then((items) => {
        if (!live) return;
        setJournal(items.find((doc) => doc.start === date) ?? null);
        setError("");
      })
      .catch((e) => {
        if (!live) return;
        setJournal(null);
        setError(e instanceof Error ? e.message : "오늘 일지를 불러오지 못했습니다.");
      });
    return () => {
      live = false;
    };
  }, [classId, date, reload]);

  /** 방금 저장한 일과를 근거로 초안을 만든다. `sourceIds` 는 `routine:31` 모양이다. */
  async function make(sourceIds: string[]) {
    if (busy || classId === null || !sourceIds.length) return;
    // `createDocument` 는 화면 반 id 를 받는다. 이 화면이 든 것은 서버 번호라 되짚는다.
    const local = loadClassSettings()?.classes.find((c) => classServerId(c.id) === classId)?.id;
    if (!local) {
      setError(NO_CLASS);
      return;
    }
    setBusy(true);
    setError("");
    try {
      const made = await createDocument({
        kind: "dailyLog",
        classId: local,
        childId: "",
        start: date,
        end: date,
        sourceIds,
      });
      setOpenId(made.id);
      setReload((n) => n + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "초안을 만들지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }

  return {
    /** 그날 일지. `undefined` 는 아직 불러오는 중, `null` 은 없다. */
    doc: journal,
    busy,
    error,
    make,
    openId,
    open: (id: string) => setOpenId(id),
    close: () => setOpenId(""),
    retry: () => setReload((n) => n + 1),
    off: classId === null || !date,
  };
}

export type DailyJournal = ReturnType<typeof useDailyJournal>;

export default function DailyJournalCard({ state, day }: { state: DailyJournal; day: string }) {
  const edit = useServerDocument(state.openId, {
    onChanged: state.retry,
    // 지운 문서를 편집기에 남겨 두면 저장할 수 없는 칸만 보인다.
    onRemoved: state.close,
  });
  if (state.off) return null;
  const journal = state.doc;
  const open = !!state.openId;

  return (
    <section className={`${ws.card} ${ws.journalCard}`}>
      <div className={ws.journalHead}>
        <h2 className={ws.journalTitle}>{day} 보육일지</h2>
        {journal ? (
          <button
            type="button"
            className={ws.secondary}
            onClick={() => (open ? state.close() : state.open(journal.id))}
          >
            {open ? "접기" : journal.status === "confirmed" ? "일지 보기" : "이어서 쓰기"}
          </button>
        ) : null}
      </div>
      <p className={ws.hint}>
        {journal === undefined
          ? "불러오는 중…"
          : journal
            ? `${journal.status === "confirmed" ? "확정했습니다." : "초안까지 만들었습니다."}${
                journal.stale ? " 근거가 바뀌어 다시 볼 것이 있습니다." : ""
              }`
            : "아직 만들지 않았습니다. 실제로 한 것을 적고 위의 「오늘 일지 만들기」를 누르세요."}
      </p>

      {(state.error || edit.status === "error") && (
        <div className={ws.stack}>
          <Message error>{state.error || edit.error}</Message>
          <button type="button" className={ws.rowTool} onClick={state.retry}>
            다시 불러오기
          </button>
        </div>
      )}

      {open && (
        <div className={ws.journalBody}>
          {edit.status === "loading" && <p className={ws.hint}>일지를 불러오는 중…</p>}
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
