"use client";

import { useEffect, useState } from "react";
import {
  createDocument,
  getDocument,
  listDocuments,
  type DocumentSummary,
} from "@/lib/api/documents";
import type { DayWeather } from "@/lib/api/routines";
import { indoorNote } from "@/lib/workspace/journal-day";
import { classServerId } from "@/lib/api/onboarding";
import { loadClassSettings } from "@/lib/onboarding/settings";
import { Posty } from "@/components/app/Posty";
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
  /**
   * 이 반 · 이 날짜. 조회 결과 · 펴 놓은 일지 · 오류를 모두 이 열쇠에 묶는다 — 날짜를
   * 옮기면 이전 날 일지가 새 날 제목을 달고 남아, 교사가 엉뚱한 날을 저장 · 확정했다.
   */
  const at = `${classId}|${date}`;
  const [loaded, setLoaded] = useState<{ at: string; doc: DocumentSummary | null } | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<{ at: string; text: string } | null>(null);
  const [reload, setReload] = useState(0);
  // 펴 놓은 일지. 만들면 바로 펴고, 교사가 접으면 칠판만 남는다.
  const [opened, setOpened] = useState<{ at: string; id: string } | null>(null);
  // 펴 놓은 편집기에 저장 안 한 글이 있나. 편집기가 알려 준다.
  const [dirty, setDirty] = useState(false);
  // 확정한 전날(지난 기록일) 일지의 지원. 반영할 줄을 고르는 쪽지에 쓴다 (ADR-086).
  const [yesterday, setYesterday] = useState<{ key: string; support: string } | null>(null);

  useEffect(() => {
    if (classId === null || !date) return;
    let live = true;
    const here = `${classId}|${date}`;
    listDocuments({ kind: "dailyLog", class_id: classId })
      .then((items) => {
        if (!live) return;
        setLoaded({ at: here, doc: items.find((doc) => doc.start === date) ?? null });
        setFailed(null);
        // 지난 기록일 일지가 **확정**이어야 그 지원을 잇는다. 초안 지원은 고쳐지거나 지워질 수 있다.
        const before = items
          .filter((doc) => doc.start < date)
          .sort((a, b) => (a.start < b.start ? 1 : -1))[0];
        if (before?.status !== "confirmed") return setYesterday(null);
        return getDocument(before.id).then(
          (doc) => {
            const support = doc.sections.find((s) => s.heading === "지원")?.body.trim() ?? "";
            if (live) setYesterday(support ? { key: `${classId}|${date}`, support } : null);
          },
          () => live && setYesterday(null),
        );
      })
      .catch((e) => {
        if (!live) return;
        setLoaded({ at: here, doc: null });
        setFailed({
          at: here,
          text: e instanceof Error ? e.message : "일지를 불러오지 못했습니다.",
        });
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
      setFailed({ at, text: NO_CLASS });
      return;
    }
    setBusy(true);
    setFailed(null);
    // 이 렌더의 `at`(만들기를 누른 날)에 묶는다. 응답이 늦게 와서 그 사이 날짜를 옮겼으면
    // 새 날에는 열지 않는다.
    try {
      const made = await createDocument({
        kind: "dailyLog",
        classId: local,
        childId: "",
        start: date,
        end: date,
        sourceIds,
      });
      setOpened({ at, id: made.id });
      setReload((n) => n + 1);
    } catch (e) {
      setFailed({ at, text: e instanceof Error ? e.message : "초안을 만들지 못했습니다." });
    } finally {
      setBusy(false);
    }
  }

  return {
    /** 그날 일지. `undefined` 는 아직 불러오는 중, `null` 은 없다. */
    doc: loaded?.at === at ? loaded.doc : undefined,
    /** 확정한 전날 일지의 지원. 없으면 null — 반영 쪽지를 안 띄운다. */
    yesterday: yesterday?.key === `${classId}|${date}` ? yesterday.support : null,
    busy,
    error: failed?.at === at ? failed.text : "",
    make,
    openId: opened?.at === at ? opened.id : "",
    open: (id: string) => setOpened({ at, id }),
    close: () => setOpened(null),
    retry: () => setReload((n) => n + 1),
    off: classId === null || !date,
    dirty,
    setDirty,
    /** 날짜를 옮기거나 접기 전에 부른다. 저장 안 한 일지 글이 있으면 묻고, 옮겨도 되면 true. */
    leave: () => !dirty || window.confirm(LEAVE_JOURNAL),
  };
}

/** 펴 놓은 일지에 저장 안 한 글이 있을 때 날짜 · 주를 옮기거나 접기 전에 묻는 말. */
export const LEAVE_JOURNAL = "저장하지 않은 일지 글이 사라져요. 옮길까요?";

export type DailyJournal = ReturnType<typeof useDailyJournal>;

/** 일지가 어디까지 됐나 — 포스티의 자세 · 얼굴 · 색이 곧 그 상태다. 주간 일지 칸도 같이 쓴다. */
export function journalMood(journal: DocumentSummary | null | undefined) {
  if (journal === undefined) return { pose: "think", face: "think", tone: "shell" } as const;
  // 앉아서 「비었어요」 하던 자리. 교사가 할 일이 남은 칸이라, 일어서서 손을 흔들어 부른다.
  if (!journal) return { pose: "wave", face: "oh", tone: "note" } as const;
  if (journal.stale) return { pose: "point", face: "fix", tone: "caution" } as const;
  if (journal.status === "confirmed") return { pose: "cheer", face: "done", tone: "sage" } as const;
  return { pose: "hand", face: "base", tone: "lilac" } as const;
}

export default function DailyJournalCard({
  state,
  day,
  makeLabel = "오늘 일지 만들기 →",
}: {
  state: DailyJournal;
  day: string;
  /** 머리줄 만들기 단추의 글자. 지난 날이면 「이날 일지 만들기 →」다. */
  makeLabel?: string;
}) {
  if (state.off) return null;
  const journal = state.doc;
  const open = !!state.openId;
  const mood = journalMood(journal);
  const say =
    journal === undefined
      ? "일지를 찾고 있어요."
      : journal
        ? journal.stale
          ? "근거가 바뀌었어요. 다시 볼 것이 있어요."
          : journal.status === "confirmed"
            ? "확정까지 끝냈어요."
            : "초안까지 만들어 두었어요."
        : "아직 만들지 않았어요.";

  return (
    <section className={`${ws.card} ${ws.journalCard}`} data-tour="routines-journal">
      <h2 className={ws.journalTitle}>{day} 보육일지</h2>
      {/* 머리와 몸을 가르는 선. 달력 밑에 바로 붙어 있어 선이 없으면 한 덩어리로 읽힌다. */}
      <hr className={ws.journalRule} />

      <div className={ws.journalSay}>
        <Posty
          pose={mood.pose}
          face={mood.face}
          tone={mood.tone}
          size={64}
          wave={journal === null}
          label={null}
        />
        <div>
          <p className={ws.journalWord}>{say}</p>
          {!journal && journal !== undefined && (
            <p className={ws.journalLead}>화면 맨 위 「{makeLabel}」를 누르세요.</p>
          )}
        </div>
      </div>

      {journal ? (
        <button
          type="button"
          className={ws.journalOpen}
          onClick={() => (open ? state.leave() && state.close() : state.open(journal.id))}
        >
          {open ? "접기" : journal.status === "confirmed" ? "일지 보기" : "이어서 쓰기"}
        </button>
      ) : null}

      {state.error && (
        <div className={ws.stack}>
          <Message error>{state.error}</Message>
          <button type="button" className={ws.rowTool} onClick={state.retry}>
            다시 불러오기
          </button>
        </div>
      )}
    </section>
  );
}

/**
 * 펴 놓은 일지 — **오른쪽 칠판 밑**에 선다.
 *
 * 요약 칸은 날짜와 같이 봐야 해서 달력 밑에 있지만, 그 칸은 좁다. 일지는 문단을 쓰는
 * 글이라 읽을 수 있는 너비가 필요하고, 방금 적은 일과가 바로 위에 있어야 한다.
 */
export function DailyJournalEditor({
  state,
  day,
  weather = null,
}: {
  state: DailyJournal;
  day: string;
  /** 비 · 눈 · 미세먼지 날이면 특이사항에 칩 하나를 띄운다. */
  weather?: DayWeather | null;
}) {
  const edit = useServerDocument(state.openId, {
    onChanged: state.retry,
    // 지운 문서를 편집기에 남겨 두면 저장할 수 없는 칸만 보인다.
    onRemoved: state.close,
  });
  if (state.off || !state.openId) return null;

  return (
    <section className={`${ws.card} ${ws.journalCard}`} aria-label={`${day} 보육일지`}>
      {edit.status === "loading" && <p className={ws.hint}>일지를 불러오는 중…</p>}
      {edit.status === "error" && <Message error>{edit.error}</Message>}
      {edit.doc && (
        <DocumentEditor
          key={edit.doc.id}
          initial={edit.doc}
          server={edit.server}
          /* 서버 문서는 편집기가 서버에 바로 쓴다. 브라우저 저장소로 가는 길은 쓰지 않는다. */
          onSave={() => true}
          onDirty={state.setDirty}
          noteChips={[indoorNote(weather)].filter((v): v is string => !!v)}
        />
      )}
    </section>
  );
}
