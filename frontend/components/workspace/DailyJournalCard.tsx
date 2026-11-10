"use client";

import { useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
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
import DailyJournalBoard from "./DailyJournalBoard";
import { useServerDocument } from "./use-server-document";
import { useJournalEditor } from "./use-journal-editor";
import dj from "./DailyJournal.module.css";

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
  const scope = `${classId}|${date}`;
  const [loaded, setLoaded] = useState<{ scope: string; doc: DocumentSummary | null }>();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<{ scope: string; text: string } | null>(null);
  const [reload, setReload] = useState(0);
  // 펴 놓은 일지. 만들면 바로 펴고, 교사가 접으면 칠판만 남는다.
  const editor = useJournalEditor(scope, busy);
  /** 방금 「오늘 일지 만들기」로 만든 초안. 편집기가 그 자리로 내려가 한 번 반짝인다. */
  const [fresh, setFresh] = useState("");
  // 확정한 전날(지난 기록일) 일지의 지원. 반영할 줄을 고르는 쪽지에 쓴다 (ADR-086).
  const [yesterday, setYesterday] = useState<{ key: string; support: string } | null>(null);

  useEffect(() => {
    if (classId === null || !date) return;
    let live = true;
    listDocuments({ kind: "dailyLog", class_id: classId })
      .then((items) => {
        if (!live) return;
        setLoaded({ scope, doc: items.find((doc) => doc.start === date) ?? null });
        setFailed(null);
        // 지난 기록일 일지가 **확정**이어야 그 지원을 잇는다. 초안 지원은 고쳐지거나 지워질 수 있다.
        const before = items
          .filter((doc) => doc.start < date)
          .sort((a, b) => (a.start < b.start ? 1 : -1))[0];
        if (before?.status !== "confirmed") return setYesterday(null);
        return getDocument(before.id).then(
          (doc) => {
            const support = doc.sections.find((s) => s.heading === "지원")?.body.trim() ?? "";
            if (live) setYesterday(support ? { key: scope, support } : null);
          },
          () => live && setYesterday(null),
        );
      })
      .catch((e) => {
        if (!live) return;
        setLoaded({ scope, doc: null });
        setFailed({
          scope,
          text: e instanceof Error ? e.message : "일지를 불러오지 못했습니다.",
        });
      });
    return () => {
      live = false;
    };
  }, [classId, date, scope, reload]);

  /** 방금 저장한 일과를 근거로 초안을 만든다. `sourceIds` 는 `routine:31` 모양이다. */
  async function make(sourceIds: string[]) {
    if (busy || classId === null || !sourceIds.length) return;
    // `createDocument` 는 화면 반 id 를 받는다. 이 화면이 든 것은 서버 번호라 되짚는다.
    const local = loadClassSettings()?.classes.find((c) => classServerId(c.id) === classId)?.id;
    if (!local) {
      setFailed({ scope, text: NO_CLASS });
      return;
    }
    setBusy(true);
    setFailed(null);
    // 이 렌더의 `scope`(만들기를 누른 날)에 묶는다. 응답이 늦게 와서 그 사이 날짜를 옮겼으면
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
      editor.open(made.id);
      setFresh(made.id);
      setReload((n) => n + 1);
    } catch (e) {
      setFailed({ scope, text: e instanceof Error ? e.message : "초안을 만들지 못했습니다." });
    } finally {
      setBusy(false);
    }
  }

  return {
    /** 그날 일지. `undefined` 는 아직 불러오는 중, `null` 은 없다. */
    doc: loaded?.scope === scope ? loaded.doc : undefined,
    /** 확정한 전날 일지의 지원. 없으면 null — 반영 쪽지를 안 띄운다. */
    yesterday: yesterday?.key === scope ? yesterday.support : null,
    busy,
    error: failed?.scope === scope ? failed.text : "",
    make,
    // openId · open · close(=leave, 저장 안 한 글이면 묻는다) · pending · dismiss
    ...editor,
    /** 펴 놓은 일지가 방금 만든 초안인가. 접었다 다시 펴면 아니다. */
    fresh: !!fresh && editor.openId === fresh,
    open: (id: string) => {
      setFresh("");
      editor.open(id);
    },
    retry: () => setReload((n) => n + 1),
    off: classId === null || !date,
  };
}

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
            : state.fresh
              ? "초안을 만들었어요. 칠판 밑 일지에서 다듬어 주세요."
              : "초안까지 만들어 두었어요."
        : "아직 만들지 않았어요.";

  return (
    <section className={`${ws.card} ${ws.journalCard}`} data-tour="routines-journal">
      <div className={ws.journalHead}>
        <h2 className={ws.journalTitle}>{day} 보육일지</h2>
        <JournalMark journal={journal} />
      </div>
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
            <p className={ws.journalLead}>
              {/* 「…」 와 「를」 사이에서 줄이 넘어가 「를」만 아랫줄 첫머리에 남았다. */}
              화면 맨 위 <span className="whitespace-nowrap">「오늘 일지 만들기 →」를</span>{" "}
              누르세요.
            </p>
          )}
        </div>
      </div>

      {journal ? (
        <button
          id={JOURNAL_OPEN_ID}
          type="button"
          className={`${ws.journalOpen} tap44`}
          onClick={() => (open ? state.close() : state.open(journal.id))}
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

/** 일지 칸 제목 옆 도장 — 확정은 빨간 확정 도장, 초안은 점선 「초안」. 없으면 아무것도 안 찍는다. */
function JournalMark({ journal }: { journal: DocumentSummary | null | undefined }) {
  if (!journal) return null;
  if (journal.status === "confirmed") return <span className={dj.doneMark}>확정</span>;
  return <span className={`${dj.draftMark} ${dj.onPaper}`}>초안</span>;
}

/** 일과 칠판으로 화면을 올린다 — 사실은 칠판에서 고친다. */
function scrollToBoard() {
  const reduce = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  document
    .querySelector('[data-tour="routines-board"]')
    ?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
}

/**
 * 펴 놓은 일지 — **오른쪽 칠판 밑**에 선다.
 *
 * 요약 칸은 날짜와 같이 봐야 해서 달력 밑에 있지만, 그 칸은 좁다. 일지는 문단을 쓰는
 * 글이라 읽을 수 있는 너비가 필요하고, 방금 적은 일과가 바로 위에 있어야 한다.
 *
 * 휴대폰(1024px 아래)에서는 칠판 밑에 붙이면 달력 · 칠판을 지나 세 화면 아래에 열렸다.
 * 그래서 화면을 덮는 한 장(`JournalSheet`)으로 연다.
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
    onRemoved: state.dismiss,
  });
  const phone = usePhone();
  /**
   * 막 만든 초안이면 그 자리로 화면을 내리고 커서를 옮긴다 — 만들어도 위에 일과 칠판만 보여
   * 초안이 생긴 줄 몰랐다(PM). 휴대폰은 화면을 덮는 한 장으로 열리니 따로 내리지 않는다.
   */
  const box = useRef<HTMLElement>(null);
  const freshId = state.fresh ? state.openId : "";
  const loadedId = edit.doc?.id ?? "";
  useEffect(() => {
    if (!freshId || loadedId !== freshId || phone) return;
    const reduce = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    box.current?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
    box.current?.focus({ preventScroll: true });
  }, [freshId, loadedId, phone]);
  if (state.off || !state.openId) return null;

  /** 「칠판에서 고치기」. 휴대폰은 한 장을 닫아야 칠판이 보인다 — 저장 안 한 글이 있으면 먼저 묻는다. */
  function editFacts() {
    // leave 는 물어서 괜찮으면 한 장도 닫는다.
    if (phone && !state.leave()) return;
    requestAnimationFrame(scrollToBoard);
  }

  const body = (
    <>
      {edit.status === "loading" && <p className={ws.hint}>일지를 불러오는 중…</p>}
      {edit.status === "error" && <Message error>{edit.error}</Message>}
      {edit.doc && edit.server && (
        <DailyJournalBoard
          key={edit.doc.id}
          initial={edit.doc}
          server={edit.server}
          onEditStateChange={state.onEditStateChange}
          noteChips={[indoorNote(weather)].filter((v): v is string => !!v)}
          onEditFacts={editFacts}
        />
      )}
    </>
  );
  if (phone)
    return (
      <JournalSheet title={`${day} 보육일지`} canLeave={state.leave} onClose={state.dismiss}>
        {body}
      </JournalSheet>
    );
  return (
    <section
      ref={box}
      tabIndex={-1}
      // 글이 다 온 뒤에 반짝인다 — 불러오는 중에 끝나 버리면 안 보인다.
      className={state.fresh && edit.doc ? `${dj.wrap} ${dj.fresh}` : dj.wrap}
      aria-label={`${day} 보육일지`}
    >
      {body}
    </section>
  );
}

/** 요약 칸의 「이어서 쓰기 · 접기」. 한 장을 닫았는데 돌아갈 자리가 없으면 여기로 커서를 둔다. */
const JOURNAL_OPEN_ID = "daily-journal-open";

/** 하단 메뉴가 서는 폭(1024px 아래) — 휴대폰 · 태블릿. */
const PHONE = "(max-width: 1023px)";
const watchPhone = (change: () => void) => {
  const query = globalThis.matchMedia?.(PHONE);
  query?.addEventListener("change", change);
  return () => query?.removeEventListener("change", change);
};
/** 시험의 가짜 창에는 `matchMedia` 가 없다 — 그때는 데스크톱으로 본다. 서버 그림도 데스크톱이다. */
function usePhone() {
  return useSyncExternalStore(
    watchPhone,
    () => globalThis.matchMedia?.(PHONE).matches ?? false,
    () => false,
  );
}

/**
 * 휴대폰에서 일지를 펴는 한 장. 화면을 다 덮고 안쪽만 구른다.
 * 네이티브 모달 `<dialog>` 라서 포커스를 가두고 Esc 로 닫히며, 닫으면 연 단추로 포커스가 돌아간다
 * (RegionSheet · EvaluationDrawer 와 같다). 저장 안 한 글이 있으면 닫기 전에 묻는다.
 */
function JournalSheet({
  title,
  canLeave,
  onClose,
  children,
}: {
  title: string;
  /** 닫아도 되나. 저장 안 한 글이 있으면 묻고, 교사가 그대로 두겠다면 false. */
  canLeave: () => boolean;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
    // 뒤 화면이 같이 구르지 않게 한다(하단 메뉴 「더보기」와 같다).
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, []);

  return (
    <dialog
      ref={ref}
      className={dj.phoneSheet}
      aria-label={title}
      // 안쪽 대화상자(근거 반영 확인)의 cancel · close 도 React 에서는 여기까지 올라온다 — 이 한 장 것만 받는다.
      onCancel={(e) => {
        if (e.target !== e.currentTarget) return;
        if (!canLeave()) e.preventDefault();
      }}
      onClose={(e) => {
        if (e.target !== e.currentTarget) return;
        onClose();
        // 「오늘 일지 만들기」로 열면 그 단추가 만드는 동안 잠겨 커서를 잃는다 — 브라우저가 돌려줄 곳이
        // 없으면 요약 칸 단추로 둔다.
        requestAnimationFrame(() => {
          if (document.activeElement === document.body)
            document.getElementById(JOURNAL_OPEN_ID)?.focus();
        });
      }}
    >
      <div className={dj.phoneSheetHead}>
        <button
          type="button"
          className={`${dj.phoneSheetBack} tap44`}
          onClick={() => canLeave() && ref.current?.close()}
        >
          닫기
        </button>
        <h2>{title}</h2>
      </div>
      {children}
    </dialog>
  );
}
