"use client";

import { useEffect, useRef, useState } from "react";
import type { SavedDocument } from "@/lib/workspace/model";
import {
  FALLBACK_DRAFT,
  downloadDocumentHwpx,
  isStaleWrite,
  type SourceResolution,
  type VerifyIssue,
} from "@/lib/api/documents";
import { invalidFields } from "@/lib/api/client";
import { useHwpxDownload } from "@/lib/hooks/use-hwpx-download";
import { Icon } from "@/components/app/icons";
import { Posty } from "@/components/app/Posty";
import { Message, ws } from "./WorkspaceUI";
import { serverIssues } from "./document-selection";
import { FieldError, fieldErrorProps } from "./WorkspaceViewState";
import type { ServerDocumentActions } from "./DocumentEditor";
import { clockText } from "./RoutineClock";
import SourceReview from "./SourceReview";
import dj from "./DailyJournal.module.css";

const PADS = [
  { heading: "해석", hint: "위 쪽지에서 읽을 수 있는 의미만 적어요." },
  { heading: "지원", hint: "다음 놀이에서 교사가 할 일을 구체적으로 적어요." },
] as const;

/** 서버가 짚는 칸 → 고칠 수 있는 공책 이름. 사실은 여기서 못 고친다. */
const SECTION_FIELDS: Record<string, string> = { "sections.해석": "해석", "sections.지원": "지원" };

/** 근거를 반영하기 전, 저장 안 한 글을 어떻게 할지. */
type RefreshChoice = "save" | "discard" | "cancel";

/** 지금 글에 붙은 AI 검증. `judged` 가 false 면 판정하지 않았다 — 빈 목록을 통과로 읽지 않는다. */
interface Review {
  issues: VerifyIssue[];
  judged: boolean;
}

/** 사실 한 줄 — `[오전 실내놀이 09:20~10:40] 활동실행` (backend routines/models.py `fact_text`). */
export interface FactNote {
  name: string;
  start: string;
  end: string;
  text: string;
}
const FACT_LINE = /^\[(.*?)(?:\s+(\d{2}:\d{2})?~(\d{2}:\d{2})?)?\]\s*(.*)$/;
/** 사실 칸을 일과 쪽지로 나눈다. 모양이 다른 줄은 이름 없이 글만 둔다 — 버리지 않는다. */
export function factNotes(body: string): FactNote[] {
  return body
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const m = FACT_LINE.exec(line);
      if (!m) return { name: "", start: "", end: "", text: line };
      return { name: m[1].trim(), start: m[2] ?? "", end: m[3] ?? "", text: m[4] };
    });
}

/**
 * 일일 보육일지 한 편 — 일과 기록 화면에서 쓰는 모양 (관찰일지 편집기와 같은 칠판 · 쪽지 · 공책).
 *
 * 초안은 **칠판 위에 일과 쪽지**(사실, 읽기 전용) · **공책 두 장**(해석 · 지원) · 반 운영 특이사항,
 * 확정본은 **도장이 찍힌 흰 종이**다. 문서 보관함의 `DocumentEditor` 는 계획안까지 받는 범용이라
 * 이 모양을 줄 수 없다. 서버 동작(저장 · 확정 · 충돌 · 근거 반영)은 같은 `server` 한 벌을 쓴다.
 */
export default function DailyJournalBoard({
  initial,
  server,
  onEditStateChange,
  noteChips = [],
  onEditFacts,
}: {
  initial: SavedDocument;
  server: ServerDocumentActions;
  /** 저장 안 한 글 · 요청 중을 알린다. 날짜를 옮기는 화면이 먼저 묻고 잠근다. */
  onEditStateChange?: (state: { dirty: boolean; pending: boolean }) => void;
  /** 반 운영 특이사항 아래 띄울 칩 — 그날 날씨 대체놀이 (ADR-089 화면). */
  noteChips?: string[];
  /** 「칠판에서 고치기」. 사실은 일과 기록에서만 고친다 (§11). */
  onEditFacts?: () => void;
}) {
  const [baseline, setBaseline] = useState(initial);
  const [doc, setDoc] = useState(initial);
  const [checked, setChecked] = useState(false);
  /** 지금 도는 요청. 검증은 따로 센다 — 단추 글자가 「대조하고 있어요」로 바뀐다. */
  const [busy, setBusy] = useState<"" | "verify" | "work">("");
  const [message, setMessage] = useState("");
  /** 확정 전에 걸린 것(20자 규칙). */
  const [issues, setIssues] = useState<string[]>([]);
  /** 서버가 짚은 공책 (`해석` · `지원`). */
  const [invalid, setInvalid] = useState<string[]>([]);
  const [staleWrite, setStaleWrite] = useState(false);
  const [review, setReview] = useState<Review | null>(null);
  /** 사라진 근거 복구 화면이 떠 있나. 떠 있으면 「변경된 근거 반영하기」를 숨긴다. */
  const [recovering, setRecovering] = useState(false);
  const hwpx = useHwpxDownload(setMessage);
  const working = !!busy || hwpx.exporting || server.pending;
  const editable = doc.status !== "confirmed";

  const body = (heading: string) => doc.sections.find((s) => s.heading === heading)?.body ?? "";
  const dirty =
    editable &&
    (JSON.stringify(doc.sections) !== JSON.stringify(baseline.sections) ||
      (doc.classNote ?? "") !== (baseline.classNote ?? ""));
  useEffect(() => {
    onEditStateChange?.({ dirty, pending: working });
  }, [dirty, working, onEditStateChange]);

  function edit(heading: string, text: string) {
    setDoc((prev) => ({
      ...prev,
      sections: prev.sections.map((s) => (s.heading === heading ? { ...s, body: text } : s)),
    }));
    // 글이 바뀌면 옛 대조 · 검증은 이 글의 것이 아니다.
    setChecked(false);
    setReview(null);
    setIssues([]);
    setInvalid((prev) => prev.filter((name) => name !== heading));
  }

  function adopt(next: SavedDocument, note: string) {
    setBaseline(next);
    setDoc(next);
    setChecked(false);
    setReview(null);
    setIssues([]);
    setInvalid([]);
    setStaleWrite(false);
    setMessage(note);
  }

  /** 서버 요청 하나. 실패하면 고친 글을 그대로 둔다. 성공하면 true. */
  async function run<T extends SavedDocument>(
    call: () => Promise<T | null>,
    note: string | ((next: T) => string),
  ) {
    if (working) return false;
    setBusy("work");
    setMessage("");
    try {
      const next = await call();
      // reload 는 그 사이 다른 문서로 옮기면 null 이다 — 지금 편집기를 바꾸지 않는다.
      if (next) adopt(next, typeof note === "function" ? note(next) : note);
      return true;
    } catch (e) {
      if (isStaleWrite(e)) {
        setStaleWrite(true);
        return false;
      }
      // 서버가 짚은 칸을 버리지 않는다 — 어느 공책을 고칠지 알아야 한다.
      const blocked = invalidFields(e, SECTION_FIELDS);
      setInvalid(blocked);
      setMessage(
        blocked.length
          ? `${blocked.join(", ")} 칸이 원본과 맞지 않아요.`
          : e instanceof Error
            ? e.message
            : "요청을 처리하지 못했어요.",
      );
      return false;
    } finally {
      setBusy("");
    }
  }

  const save = () =>
    run(
      () => server.save(doc.sections, "교사 검토 전", doc.classNote),
      "작성 중인 초안을 저장했어요.",
    );

  async function confirm() {
    const blocking = serverIssues(doc);
    if (blocking.length || !checked) {
      setIssues(blocking);
      setMessage(blocking.length ? "" : "쪽지와 대조했는지 먼저 체크해 주세요.");
      return;
    }
    if (server.stale) {
      setMessage("근거 기록이 바뀌었어요. 반영한 뒤 확정해 주세요.");
      return;
    }
    await run(
      () => server.saveAndConfirm(doc.sections, "교사 사실·해석·지원 검토 완료", doc.classNote),
      "검토한 문서를 확정했어요.",
    );
  }

  const unconfirm = () =>
    run(
      () => server.unconfirm(),
      ({ newlyStaleCount }) =>
        "확정을 취소했어요. 다시 고칠 수 있어요." +
        (newlyStaleCount
          ? ` 이 일지를 근거로 쓴 문서 ${newlyStaleCount}건이 다시 검토 대상이 되었어요.`
          : ""),
    );

  const reload = () =>
    run(() => server.reload(), "최신 일지를 불러왔어요. 내용을 확인한 뒤 다시 고쳐 주세요.");

  /** 3단 AI 검증 — 쪽지(기록)와 어긋나거나 써선 안 되는 표현을 문장마다 짚는다. 저장하지 않는다. */
  async function verify() {
    if (working) return;
    const blocking = serverIssues(doc);
    setIssues(blocking);
    setReview(null);
    if (blocking.length) return;
    setBusy("verify");
    setMessage("");
    try {
      const result = await server.verify(doc.sections);
      setReview({ issues: result.issues, judged: result.judged });
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "AI 검증을 하지 못했어요.");
    } finally {
      setBusy("");
    }
  }

  /**
   * 근거를 반영하면 서버 글로 바뀐다. 저장 안 한 글이 있으면 저장 · 버리기 · 취소를 묻는다.
   * 계속해도 되면 true.
   */
  const refreshAsk = useRef<HTMLDialogElement>(null);
  const answer = useRef<((choice: RefreshChoice) => void) | null>(null);
  async function settleEdits(): Promise<boolean> {
    if (!dirty) return true;
    const choice = await new Promise<RefreshChoice>((resolve) => {
      answer.current = resolve;
      refreshAsk.current?.showModal();
    });
    if (choice === "cancel") return false;
    return choice === "discard" || (await save());
  }
  function reply(choice: RefreshChoice) {
    const resolve = answer.current;
    answer.current = null;
    if (refreshAsk.current?.open) refreshAsk.current.close();
    resolve?.(choice);
  }
  /** 사라진 근거 복구(초안)도 같은 반영이다 — 같이 묻는다. */
  async function refreshWithResolutions(resolutions?: SourceResolution[]) {
    if (!(await settleEdits())) throw new Error("반영을 그만뒀어요. 고친 글은 그대로 있어요.");
    return server.refresh(resolutions);
  }
  async function refreshSources() {
    if (!(await settleEdits())) return;
    await run(() => server.refresh(), "바뀐 근거를 받아 왔어요. 해석과 지원을 다시 봐 주세요.");
  }

  async function removeDoc() {
    if (working) return;
    if (!window.confirm("이 일지를 삭제할까요? 되돌릴 수 없어요.")) return;
    setMessage("");
    try {
      await server.remove();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "삭제하지 못했어요.");
    }
  }

  const facts = factNotes(body("사실"));
  const sourceCount = doc.sources.length || facts.length;

  return (
    <div className={dj.wrap}>
      {server.stale && server.reconfirm && (
        <SourceReview
          key={`${doc.id}:${doc.updatedAt}`}
          doc={doc}
          pending={working}
          reconfirm={server.reconfirm}
          refresh={refreshWithResolutions}
          onRecovery={setRecovering}
          onReload={reload}
          onComplete={adopt}
        />
      )}
      {staleWrite && (
        <div className={dj.alert} role="alert">
          <p>다른 곳에서 이 일지가 고쳐졌어요. 최신 내용을 불러오면 지금 고친 글은 바뀌어요.</p>
          <button type="button" className={ws.secondary} disabled={working} onClick={reload}>
            최신 문서 불러오기
          </button>
        </div>
      )}

      {editable ? (
        <div className={`chalkboard ${dj.board}`}>
          <header className={dj.head}>
            <h2>{doc.title}</h2>
            <span className={dj.draftMark}>초안</span>
            {doc.origin === "ai" && <em>AI 초안</em>}
            {server.stale && <em data-alert>근거가 바뀜</em>}
          </header>
          {doc.fallbackDraft && <Message>{FALLBACK_DRAFT}</Message>}
          {doc.mockDraft && (
            <p className={dj.chalk}>
              테스트 모드(mock)로 만든 초안이에요. 실제 AI 결과가 아니니 다시 써 주세요.
            </p>
          )}

          <section className={dj.part} aria-labelledby="dj-facts">
            <div className={dj.partHead}>
              <h3 id="dj-facts">
                <Icon name="lock" width={18} height={18} />
                오늘 한 일
              </h3>
              <span className={dj.count}>근거 {sourceCount}건</span>
            </div>
            <ol className={dj.facts}>
              {facts.map((fact, index) => (
                <li key={`${index}-${fact.name}`} data-tone={index % 4}>
                  {(fact.name || fact.start || fact.end) && (
                    <div className={dj.factHead}>
                      <b>{fact.name}</b>
                      {(fact.start || fact.end) && <span>{clockText(fact.start, fact.end)}</span>}
                    </div>
                  )}
                  <p>{fact.text}</p>
                </li>
              ))}
            </ol>
            <p className={dj.chalk}>
              쪽지는 일과 기록의 「실제로 한 것」을 그대로 옮겨 왔어요. 여기서는 못 고쳐요.{" "}
              {onEditFacts && (
                <button type="button" className={dj.chalkLink} onClick={onEditFacts}>
                  칠판에서 고치기 ↑
                </button>
              )}
            </p>
          </section>

          {server.stale && !recovering && (
            <div className={dj.alert}>
              <p>
                이 문서의 근거로 사용된 일과 기록이 변경되었습니다. 바뀐 쪽지를 받아 온 뒤 해석과
                지원을 다시 봐 주세요.
              </p>
              <button
                type="button"
                className={ws.secondary}
                disabled={working}
                onClick={refreshSources}
              >
                변경된 근거 반영하기
              </button>
            </div>
          )}

          <div className={dj.pads}>
            {PADS.map(({ heading, hint }) => (
              <div key={heading} className={dj.padSlot}>
                <label className={dj.pad}>
                  <span>{heading}</span>
                  <small>{hint}</small>
                  <textarea
                    aria-label={`${heading} 내용`}
                    maxLength={15000}
                    disabled={working}
                    value={body(heading)}
                    {...fieldErrorProps(heading, invalid)}
                    onChange={(e) => edit(heading, e.target.value)}
                  />
                  <FieldError name={heading} invalid={invalid} />
                </label>
                <Flags heading={heading} body={body(heading)} issues={review?.issues ?? []} />
              </div>
            ))}
          </div>

          {/* 공식 보육일지 양식 5종 전부에 있는 칸이다 (docs/references/보육일지-공식양식.md).
              그날 반에 있었던 일이라 근거에서 나오지 않는다 — 교사가 적는다. */}
          <label className={`${dj.pad} ${dj.notePad}`}>
            <span>반 운영 특이사항</span>
            <small>
              결석, 부모면담, 감염병, 안전사고처럼 그날 반에 있었던 일이에요. 없으면 비워 두세요.
            </small>
            <textarea
              aria-label="반 운영 특이사항"
              maxLength={2000}
              disabled={working}
              value={doc.classNote ?? ""}
              onChange={(e) => setDoc((prev) => ({ ...prev, classNote: e.target.value }))}
            />
          </label>
          <NoteChips
            chips={noteChips.filter((chip) => !(doc.classNote ?? "").includes(chip))}
            disabled={working}
            onPick={(chip) =>
              setDoc((prev) => ({
                ...prev,
                classNote: prev.classNote?.trim() ? `${prev.classNote.trimEnd()}\n${chip}` : chip,
              }))
            }
          />

          <VerifyBox
            review={review}
            issues={issues}
            running={busy === "verify"}
            disabled={working}
            onVerify={verify}
          />

          {message && (
            <p role="status" className={dj.note}>
              {message}
            </p>
          )}
          <footer className={dj.foot}>
            {/* 관찰일지 확인 줄과 같은 분필 타원(ws.ojCheck). 상자는 분필로 그린 네모, 표시는 노란 분필 체크. */}
            <label className={`${ws.ojCheck} ${dj.check}`}>
              <span className={dj.checkBox}>
                <input
                  type="checkbox"
                  checked={checked}
                  disabled={working}
                  onChange={(e) => setChecked(e.target.checked)}
                />
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M4.5 12.8C6.6 14.4 8.4 16.6 9.6 18.8C12.2 12.6 15.6 8.2 20.4 4.6" />
                </svg>
              </span>
              원본 기록과 사실이 일치하고, 해석과 지원이 알맞은지 확인했어요
            </label>
            <button type="button" className={dj.save} disabled={working || !dirty} onClick={save}>
              {busy === "work" ? "저장하는 중…" : dirty ? "초안 저장" : "저장됨"}
            </button>
            <button
              type="button"
              className={dj.stamp}
              disabled={working || !checked}
              onClick={confirm}
            >
              <b>확정</b>
            </button>
          </footer>
          {/* 지우기는 저장 · 확정 줄에서 떨어뜨린다 — 잘못 누르기 쉬운 자리를 피한다(PM). */}
          <button type="button" className={dj.remove} disabled={working} onClick={removeDoc}>
            <Icon name="trash" width={17} height={17} />
            일지 삭제
          </button>
        </div>
      ) : (
        <DoneSheet doc={doc} facts={facts}>
          {server.stale && (
            <Message error>
              근거 기록이 바뀌어 내려받을 수 없어요. 다시 수정을 눌러 반영해 주세요.
            </Message>
          )}
          {message && (
            <p role="status" className={dj.sheetNote}>
              {message}
            </p>
          )}
          <div className={dj.sheetActions}>
            <button
              type="button"
              className={ws.primary}
              disabled={working || server.stale}
              onClick={() => void hwpx.download(() => downloadDocumentHwpx(doc.id))}
            >
              {hwpx.exporting ? "파일 만드는 중…" : "한글 파일로 내려받기"}
            </button>
            <button type="button" className={ws.secondary} disabled={working} onClick={unconfirm}>
              다시 수정
            </button>
          </div>
        </DoneSheet>
      )}

      <dialog
        ref={refreshAsk}
        className={ws.ojLeave}
        aria-labelledby="dj-refresh-title"
        onClose={() => reply("cancel")}
      >
        <Posty pose="hand" face="oh" tone="note" size={78} label={null} />
        <h3 id="dj-refresh-title">잠깐만요!</h3>
        <p>바뀐 근거를 받으면 저장 안 한 글이 사라져요.</p>
        <div>
          <button type="button" className={ws.primary} onClick={() => reply("save")}>
            저장하고 반영
          </button>
          <button type="button" className={ws.secondary} onClick={() => reply("discard")}>
            편집 버리고 반영
          </button>
          <button type="button" className={ws.link} autoFocus onClick={() => reply("cancel")}>
            취소
          </button>
        </div>
      </dialog>
    </div>
  );
}

function NoteChips({
  chips,
  disabled,
  onPick,
}: {
  chips: string[];
  disabled: boolean;
  onPick: (chip: string) => void;
}) {
  if (!chips.length) return null;
  return (
    <div className={dj.chips}>
      {chips.map((chip) => (
        <button key={chip} type="button" disabled={disabled} onClick={() => onPick(chip)}>
          + {chip}
        </button>
      ))}
    </div>
  );
}

/**
 * AI 검증 칸 — 누르기 전 · 대조하는 중 · 끝난 뒤가 한눈에 갈린다.
 * 끝나면 「AI 검증 끝」 도장과 몇 문장이 걸렸는지, 걸린 문장은 공책 아래 쪽지로 짚는다.
 */
function VerifyBox({
  review,
  issues,
  running,
  disabled,
  onVerify,
}: {
  review: Review | null;
  issues: string[];
  running: boolean;
  disabled: boolean;
  onVerify: () => void;
}) {
  const flagged = new Set(review?.issues.map((i) => `${i.heading}|${i.sentence}`)).size;
  return (
    <section className={dj.verify} aria-labelledby="dj-verify" data-state={verifyState(review)}>
      <div className={dj.verifyHead}>
        <h3 id="dj-verify">AI 검증</h3>
        {review && (
          <span className={dj.verifyStamp}>{review.judged ? "AI 검증 끝" : "판정 못 함"}</span>
        )}
      </div>
      <VerifySay review={review} flagged={flagged} />
      {issues.length > 0 && (
        <ul className={dj.blocking} role="alert">
          {issues.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      )}
      <button type="button" className={dj.paperButton} disabled={disabled} onClick={onVerify}>
        {running ? "기록과 대조하고 있어요…" : review ? "다시 검증하기" : "AI 검증하기"}
      </button>
    </section>
  );
}

const verifyState = (review: Review | null) =>
  !review ? "idle" : !review.judged ? "skipped" : review.issues.length ? "flagged" : "clean";

function VerifySay({ review, flagged }: { review: Review | null; flagged: number }) {
  if (!review)
    return (
      <p>
        해석과 지원을 문장마다 쪽지와 대조해요. 아이 이름은 가명으로 바꿔 보내고, 확정은 선생님이
        해요.
      </p>
    );
  if (!review.judged)
    return (
      <p role="status">기본 항목은 통과했어요. AI 판정은 꺼져 있어서 쪽지와 직접 대조해 주세요.</p>
    );
  if (!flagged)
    return (
      <p role="status">
        <b>문제 없음.</b> 쪽지와 어긋난 문장을 찾지 못했어요. 확정 전에 한 번 더 읽어 주세요.
      </p>
    );
  return (
    <p role="status">
      <b>확인할 문장 {flagged}개.</b> 공책 아래에 노란 형광펜으로 짚어 두었어요.
    </p>
  );
}

/** 공책 아래 쪽지 — 검증이 짚은 문장을 형광펜으로, 이유는 한 줄로. 지금 칸에 그 문장이 있을 때만. */
function Flags({
  heading,
  body,
  issues,
}: {
  heading: string;
  body: string;
  issues: VerifyIssue[];
}) {
  const bySentence = new Map<string, VerifyIssue[]>();
  for (const i of issues)
    if (i.heading === heading && body.includes(i.sentence))
      bySentence.set(i.sentence, [...(bySentence.get(i.sentence) ?? []), i]);
  if (!bySentence.size) return null;
  return (
    <ul className={dj.flags} aria-label={`${heading}에서 확인할 문장`}>
      {[...bySentence].map(([sentence, found]) => (
        <li key={sentence}>
          <mark>{sentence}</mark>
          <small>
            {found
              .map(
                (i) => `${i.reason}${i.sourceText ? ` 기록에는 「${i.sourceText}」` : ""} ${i.fix}`,
              )
              .join(" ")}
          </small>
        </li>
      ))}
    </ul>
  );
}

/** 확정본 — 흰 종이에 확정 도장. 내려받는 한글 파일과 같은 순서(오늘 한 일 → 해석 → 지원 → 특이사항). */
function DoneSheet({
  doc,
  facts,
  children,
}: {
  doc: SavedDocument;
  facts: FactNote[];
  children: React.ReactNode;
}) {
  const section = (heading: string) => doc.sections.find((s) => s.heading === heading)?.body ?? "";
  return (
    <article className={dj.sheet} aria-label="확정한 일지">
      <span className={dj.doneMark} aria-hidden="true">
        확정
      </span>
      <header>
        <h2>{doc.title}</h2>
        <p>{doc.className}</p>
      </header>
      <h3>오늘 한 일</h3>
      <ul className={dj.sheetFacts}>
        {facts.map((fact, index) => (
          <li key={`${index}-${fact.name}`}>
            <span>{fact.start || fact.end ? clockText(fact.start, fact.end) : ""}</span>
            <b>{fact.name}</b>
            <p>{fact.text}</p>
          </li>
        ))}
      </ul>
      <h3>해석</h3>
      <p>{section("해석") || "적지 않았어요."}</p>
      <h3>지원</h3>
      <p>{section("지원") || "적지 않았어요."}</p>
      <h3>반 운영 특이사항</h3>
      <p>{doc.classNote || "적지 않았어요."}</p>
      {children}
    </article>
  );
}
