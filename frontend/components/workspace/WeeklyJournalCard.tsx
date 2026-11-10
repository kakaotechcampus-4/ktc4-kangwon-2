"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  createDocument,
  getDocument,
  listDocuments,
  type DocumentSummary,
} from "@/lib/api/documents";
import { routineLocalId, type ApiRoutine } from "@/lib/api/routines";
import { classServerId } from "@/lib/api/onboarding";
import { routinesPath } from "@/lib/workspace/routines-route";
import { Posty } from "@/components/app/Posty";
import { Message, ws } from "./WorkspaceUI";
import { journalMood } from "./DailyJournalCard";
import DocumentEditor from "./DocumentEditor";
import { useServerDocument } from "./use-server-document";
import { useJournalEditor } from "./use-journal-editor";
import css from "./RoutineDay.module.css";

type From = "dailyLog" | "routine";

const LABEL: Record<From, string> = {
  dailyLog: "확정한 일일 보육일지",
  routine: "일과 기록",
};

/** 그 주에 든 문서. 주간 일지는 월~일 또는 월~금으로 만들어 시작일로 본다. */
const inWeek = (doc: DocumentSummary, start: string, end: string) =>
  doc.start >= start && doc.start <= end;

/**
 * 서버가 주간 근거로 받지 않는 일일 일지면 그 까닭과 고치러 가는 말. 받으면 `null`.
 *
 * 서버는 확정 · 최신이고 `사실` 칸이 있는 일일만 받는다(api-spec §11). 하나라도 섞어 보내면
 * 같은 주의 멀쩡한 일일까지 함께 거절돼 주간 일지를 못 만든다. 그래서 AI 로 만든 · 확정한 ·
 * 근거가 안 바뀐 일일만 고르고, 나머지는 줄마다 까닭을 보여 준다.
 */
export function dailyBlock(d: DocumentSummary): { why: string; fix: string } | null {
  if (d.origin === "import") return { why: "올린 서류", fix: "그날 일지 쓰러 가기 →" };
  if (d.origin !== "ai") return { why: "AI 초안이 아님", fix: "그날 일지 쓰러 가기 →" };
  if (d.status !== "confirmed") return { why: "초안", fix: "확정하러 가기 →" };
  if (d.stale) return { why: "근거가 바뀜", fix: "바뀐 근거 반영하러 가기 →" };
  return null;
}

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
  /** 이 반 · 이 주. 조회 결과 · 펴 놓은 일지 · 오류를 모두 여기에 묶는다 (일일 칸과 같다). */
  const scope = `${classId}|${weekStart}|${weekEnd}`;
  const [loaded, setLoaded] = useState<{
    scope: string;
    doc: DocumentSummary | null;
    /** 그 주 일일 보육일지 전부. 근거로 못 쓰는 것도 보여 줘야 무엇을 고칠지 안다. */
    dailies: DocumentSummary[];
  }>();
  const [from, setFrom] = useState<From>("dailyLog");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<{ scope: string; text: string } | null>(null);
  const [reload, setReload] = useState(0);
  // 펴 놓은 일지. 만들면 바로 펴고, 교사가 접으면 주간 띠가 다시 올라온다.
  const editor = useJournalEditor(scope, busy);

  const serverClass = classServerId(classId);

  useEffect(() => {
    if (!weekStart || serverClass === null) return;
    let live = true;
    Promise.all([
      listDocuments({ kind: "weeklyLog", class_id: serverClass }),
      listDocuments({ kind: "dailyLog", class_id: serverClass }),
    ])
      .then(([weeklies, dailies]) => {
        if (!live) return;
        setLoaded({
          scope,
          doc: weeklies.find((d) => inWeek(d, weekStart, weekEnd)) ?? null,
          dailies: dailies
            .filter((d) => inWeek(d, weekStart, weekEnd))
            .sort((a, b) => a.start.localeCompare(b.start)),
        });
        setFailed(null);
      })
      .catch((e) => {
        if (!live) return;
        setLoaded({ scope, doc: null, dailies: [] });
        setFailed({
          scope,
          text: e instanceof Error ? e.message : "주간 일지를 불러오지 못했습니다.",
        });
      });
    return () => {
      live = false;
    };
  }, [serverClass, weekStart, weekEnd, scope, reload]);

  const week = loaded?.scope === scope ? loaded : null;
  const weekDailies = week?.dailies ?? [];
  const dailyLogs = weekDailies.filter((d) => !dailyBlock(d));
  /** 근거로 못 쓰는 일일 일지. 줄마다 까닭과 고치러 가는 길을 준다(멘토 12주차 리뷰). */
  const blockedDailies = weekDailies.filter((d) => dailyBlock(d));
  // 활동실행이 빈 일과는 서버가 근거로 받지 않는다 (§11).
  const routineSources = routines.filter((r) => r.execution).map((r) => routineLocalId(r.id));
  const sources = from === "routine" ? routineSources : dailyLogs.map((d) => d.id);

  async function make() {
    if (busy || !sources.length) return;
    setBusy(true);
    setFailed(null);
    // 이 렌더의 `scope`(만들기를 누른 주)에 묶는다. 늦게 온 응답은 다른 주에 열지 않는다.
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
      editor.open(made.id);
      setReload((n) => n + 1);
      setBusy(false);
    } catch (e) {
      setFailed({ scope, text: e instanceof Error ? e.message : "초안을 만들지 못했습니다." });
      setBusy(false);
    }
  }

  return {
    /** 그 주 일지. `undefined` 는 아직 불러오는 중, `null` 은 없다. */
    doc: week ? week.doc : undefined,
    from,
    setFrom,
    dailyLogs,
    blockedDailies,
    weekDailies,
    classId,
    routineSources,
    sources,
    busy,
    error: failed?.scope === scope ? failed.text : "",
    make,
    // openId · open · close(=leave, 저장 안 한 글이면 묻는다) · pending · dismiss
    ...editor,
    retry: () => setReload((n) => n + 1),
    /** 반을 서버에서 못 찾으면 이 화면에서 할 수 있는 일이 없다. */
    off: serverClass === null || !weekStart,
  };
}

export type WeeklyJournal = ReturnType<typeof useWeeklyJournal>;

/**
 * 그 주 확정한 일일 보육일지의 평가(해석) — 주간 총평 옆에 **보여만** 준다.
 *
 * 주간 생성에는 보내지 않는다. 일일 해석을 근거로 쓰면 「해석 위에 해석을 쌓지 않는다」
 * (api-spec 「문서를 근거로 쓸 때」)와 부딪힌다. 어긋남은 교사가 보고 맞춘다 (3차 점검 1-4).
 */
interface Evaluation {
  id: string;
  start: string;
  text: string;
}

function useDailyEvaluations(dailies: DocumentSummary[]) {
  const ids = dailies.map((d) => d.id).join(",");
  const [loaded, setLoaded] = useState<{ ids: string; items: Evaluation[] } | null>(null);
  useEffect(() => {
    if (!ids) return;
    let live = true;
    const days = new Map(dailies.map((d) => [d.id, d.start]));
    Promise.all(
      [...days.keys()].map((id) =>
        getDocument(id).then(
          (doc) => ({
            id,
            start: days.get(id) ?? "",
            text: doc.sections.find((s) => s.heading === "해석")?.body.trim() ?? "",
          }),
          () => null,
        ),
      ),
    ).then((items) => {
      if (live) setLoaded({ ids, items: items.filter((i): i is Evaluation => !!i?.text) });
    });
    return () => {
      live = false;
    };
    // `ids` 가 같으면 같은 일지들이다 — 배열이 새로 만들어졌다고 다시 읽지 않는다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ids]);
  return loaded?.ids === ids && ids ? loaded.items : [];
}

const WEEK = ["일", "월", "화", "수", "목", "금", "토"];
/** `2026-11-03` → `11/3 화` */
function dayLabel(iso: string) {
  const day = new Date(iso + "T00:00:00");
  return `${day.getMonth() + 1}/${day.getDate()} ${WEEK[day.getDay()]}`;
}

/** `2026-11-02` → `11/02` */
const short = (iso: string) => iso.slice(5).replace("-", "/");

/**
 * 이번 주 일지가 어디까지 됐나 — 주 고르기 바로 밑에 선다.
 *
 * 펴 놓은 일지까지 이 칸에 두면 좁은 왼쪽 칸에서 문단을 써야 하고, 그날 기록은
 * 일지 밑으로 밀려 내려간다. 편집기는 `WeeklyJournalEditor` 로 오른쪽에 둔다 (일과 기록과 같다).
 */
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
  const { weekDailies, blockedDailies } = state;
  if (state.off) return null;
  const open = !!state.openId;
  const mood = journalMood(journal);
  const say =
    journal === undefined
      ? "이번 주 일지를 찾고 있어요."
      : journal
        ? journal.stale
          ? "근거가 바뀌었어요. 다시 볼 것이 있어요."
          : journal.status === "confirmed"
            ? "확정까지 끝냈어요."
            : "초안까지 만들어 두었어요."
        : "아직 만들지 않았어요.";

  return (
    <section className={`${ws.card} ${ws.journalCard}`} data-tour="weekly-journal">
      <div>
        <h2 className={ws.journalTitle}>이번 주 보육일지</h2>
        <p className={ws.journalLead}>
          {className} · {short(weekStart)} – {short(weekEnd)}
        </p>
      </div>
      <hr className={ws.journalRule} />

      <div className={ws.journalSay}>
        <Posty
          pose={mood.pose}
          face={mood.face}
          tone={mood.tone}
          size={64}
          wave={journal === null && sources.length > 0}
          label={null}
        />
        <div>
          <p className={ws.journalWord}>{say}</p>
          {journal === null && (
            <p className={ws.journalLead}>
              {sources.length
                ? "화면 맨 위 「주간 일지 만들기」를 누르세요."
                : from === "dailyLog"
                  ? blockedDailies.length
                    ? `이 주 일일 보육일지 ${blockedDailies.length}건은 아직 근거로 쓸 수 없어요. 아래 줄에서 까닭을 보고 고쳐 주세요.`
                    : "이 주에 확정한 일일 보육일지가 없습니다. 일일 보육일지를 쓰지 않는 원이면 근거를 「일과 기록」으로 바꿔 주세요."
                  : "이 주 일과 기록에 「실제로 한 것」이 하나도 없습니다. 일과 기록을 먼저 적어 주세요."}
            </p>
          )}
        </div>
      </div>

      {/* 그 주 일일 일지를 날마다 한 줄로. AI 초안은 그 자리 편집기에서 확정한다 — 그날 화면으로
          옮겨 가면 주간을 쓰던 흐름이 끊긴다. 그 밖에 근거로 못 쓰는 줄은 까닭을 달고 그날 일과
          기록으로 보낸다. */}
      {journal === null && from === "dailyLog" && weekDailies.length > 0 && (
        <ul className={ws.journalDays} aria-label="이 주 일일 보육일지">
          {weekDailies.map((d) => {
            const block = dailyBlock(d);
            const draft = d.origin === "ai" && d.status !== "confirmed";
            const href = block && !draft && routinesPath(state.classId, d.start);
            return (
              // 칠하는 색은 「쓸 수 있나」로 가른다. 확정했어도 근거로 못 쓰면 주황이다.
              <li key={d.id} data-state={block ? "draft" : "confirmed"}>
                <span>{dayLabel(d.start)}</span>
                <b>{block ? block.why : "확정"}</b>
                {draft && (
                  <button
                    type="button"
                    className={css.paperButton}
                    onClick={() => state.open(d.id)}
                  >
                    여기서 확정
                  </button>
                )}
                {href && (
                  <Link href={href} className={ws.link}>
                    {block.fix}
                  </Link>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {journal === null && (
        <label className={ws.journalFrom}>
          무엇으로 쓸까요
          <select value={from} disabled={busy} onChange={(e) => setFrom(e.target.value as From)}>
            <option value="dailyLog">
              {LABEL.dailyLog} {dailyLogs.length}건
            </option>
            <option value="routine">
              {LABEL.routine} {routineSources.length}건
            </option>
          </select>
        </label>
      )}
      {journal && (
        <button
          type="button"
          className={ws.journalOpen}
          onClick={() => (open ? state.close() : state.open(journal.id))}
        >
          {open ? "접기" : journal.status === "confirmed" ? "일지 보기" : "이어서 쓰기"}
        </button>
      )}

      {error && (
        <div className={ws.stack}>
          <Message error>{error}</Message>
          <button type="button" className={ws.rowTool} onClick={state.retry}>
            다시 불러오기
          </button>
        </div>
      )}
    </section>
  );
}

/** 펴 놓은 주간 일지 — 오른쪽 칠판 밑에 선다. 문단을 쓰는 글이라 넓은 칸이 필요하다. */
export function WeeklyJournalEditor({ state }: { state: WeeklyJournal }) {
  // 일지는 이 화면에서 끝까지 쓴다 — 문서 보관함은 다 쓴 문서가 쌓이는 곳이지 쓰는 곳이 아니다.
  const edit = useServerDocument(state.openId, {
    onChanged: state.retry,
    // 지운 문서를 편집기에 남겨 두면 저장할 수 없는 칸만 보인다.
    onRemoved: state.dismiss,
  });
  // 펴 놓은 것이 주간이면 총평 옆에 그 주 일일 평가를 둔다. 일일 초안을 확정하러 편 때는 안 둔다.
  const weekly = !!state.doc && state.doc.id === state.openId;
  const evaluations = useDailyEvaluations(weekly ? state.dailyLogs : []);
  if (state.off || !state.openId) return null;

  return (
    <section
      className={`${ws.card} ${ws.journalCard}`}
      aria-label={weekly ? "이번 주 주간 보육일지" : "일일 보육일지 확정"}
    >
      {evaluations.length > 0 && (
        <aside className={css.evaluations} aria-label="이 주 일일 평가">
          <h3>이 주 일일 평가</h3>
          <p className={ws.hint}>총평과 흐름을 맞출 때 보세요. AI 에는 보내지 않아요.</p>
          <ul>
            {evaluations.map((e) => (
              <li key={e.id}>
                <b>{dayLabel(e.start)}</b> {e.text}
              </li>
            ))}
          </ul>
        </aside>
      )}
      {edit.status === "loading" && <p className={ws.hint}>일지를 불러오는 중…</p>}
      {edit.status === "error" && <Message error>{edit.error}</Message>}
      {edit.doc && (
        <DocumentEditor
          key={edit.doc.id}
          initial={edit.doc}
          server={edit.server}
          onEditStateChange={state.onEditStateChange}
          /* 서버 문서는 편집기가 서버에 바로 쓴다. 브라우저 저장소로 가는 길은 쓰지 않는다. */
          onSave={() => true}
        />
      )}
    </section>
  );
}
