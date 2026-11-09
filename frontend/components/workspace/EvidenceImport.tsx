"use client";

import { useState } from "react";
import { DOCUMENT_KINDS, today, validPeriod } from "@/lib/workspace/model";
import { importDocument, type EvidenceNotice } from "@/lib/api/documents";
import { FORM_EXTENSIONS, parseForm, tableText } from "@/lib/api/forms";
import { invalidFields, isUnauthenticated } from "@/lib/api/client";
import { useClientState } from "@/lib/hooks/use-client-state";
import { chosenClassFor, loadClassSettings } from "@/lib/onboarding/settings";
import { Message, useClasses, ws } from "./WorkspaceUI";
import styles from "./Evaluation.module.css";

/**
 * 서버가 짚은 칸 → 교사가 읽을 말. 전에는 「입력값을 확인해주세요」 한 줄만 떠서 어느 칸이
 * 틀렸는지 몰랐다(멘토 12주차 리뷰 · 평가 점검 2).
 */
const WHY: Record<string, string> = {
  child_id: "영유아 평가는 아이를 한 명 골라야 해요.",
  end: "일일 보육일지는 하루짜리예요. 날짜 하나만 골라 주세요.",
  start: "시작일이 종료일보다 늦어요.",
  body: "파일에서 글자를 읽지 못했어요. 스캔한 PDF 는 글자가 없어 읽을 수 없어요.",
  title: "파일 이름이 너무 길어요. 200자 안으로 바꿔 주세요.",
  class_id: "반을 다시 골라 주세요.",
};
/** DB 칸이 200자다. 파일 이름이 더 길면 앞부분만 제목으로 쓴다. */
const TITLE_MAX = 200;

/** `date`(YYYY-MM-DD)는 시간대가 없어 잘라 써도 된다. 「11월 9일」 */
function shortDay(value: string) {
  const [, m, d] = value.split("-").map(Number);
  return `${m}월 ${d}일`;
}

/** 한글 파일은 서버(§8 parse)가, 나머지는 화면 서버(/api/templates/extract)가 글자를 뽑는다. */
async function readText(file: File) {
  // 화면 서버는 5MB 를 넘으면 거절하지만 §8 parse 는 크기를 보지 않는다. 안내한 한도를 여기서 같이 지킨다.
  if (file.size > 5 * 1024 * 1024) throw new Error("5MB 이하 파일을 올려 주세요.");
  const hwp = FORM_EXTENSIONS.some((ext) => file.name.toLowerCase().endsWith(ext));
  if (hwp) return tableText((await parseForm(file)).tables);
  const form = new FormData();
  form.append("file", file);
  const response = await fetch("/api/templates/extract", { method: "POST", body: form });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error);
  return result.text as string;
}

/**
 * 예전 서류를 서버에 증빙으로 등록한다 (§11 「증빙 등록」 · FR-804).
 * 파일은 저장하지 않는다 — 뽑은 글자만 교사가 확인한 뒤 보낸다.
 * 등록한 문서는 보관함에 들어가고 평가 점검 집계(§12)에 세어진다.
 */
export default function EvidenceImport({
  kind,
  onImported,
}: {
  /** 카드가 정한다 — 4-1 은 일일 보육일지, 4-2 는 영유아 평가만 센다. */
  kind: "dailyLog" | "assessment";
  onImported: () => void;
}) {
  const classes = useClasses();
  const [classId] = useClientState(() => chosenClassFor(loadClassSettings())?.id ?? "", "");
  const [childId, setChildId] = useState("");
  const [start, setStart] = useState(today);
  const [end, setEnd] = useState(today);
  const [text, setText] = useState("");
  const [filename, setFilename] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  // 등록은 됐지만 교사가 알아야 하는 것 (§11). 막지 않고 알리기만 한다.
  const [notices, setNotices] = useState<EvidenceNotice[]>([]);
  const classroom = classes.find((c) => c.id === classId);
  // 일일 보육일지는 하루 · 반 전체 문서, 영유아 평가는 아이 한 명의 문서다(§11). 칸도 그대로 맞춘다.
  const daily = kind === "dailyLog";
  const periodEnd = daily ? start : end;
  // 확인 칸은 판에 보이는 반 · 날짜 · 아이를 그대로 말한다. 체크 하나가 원문 · 메타 · 「통과 아님」 확인 셋을 함께
  // 보내므로(documents.ts) 셋을 다 적는다(§11 · FR-804, 11-09 문구 토론). 전에는 판에 없는 「아동 · 반 · 기간」을 물었다.
  const roomName = classroom?.className ?? "고른 반";
  const pickedChild = classroom?.children.find((c) => c.id === childId)?.name ?? "고른 아이";
  const subject = daily
    ? `${roomName} ${shortDay(start)} 일지`
    : `${roomName} ${pickedChild} ${shortDay(start)}~${shortDay(end)} 평가`;

  async function pick(file?: File) {
    if (!file) return;
    setBusy(true);
    setMessage("");
    setText("");
    setReviewed(false);
    try {
      setText(await readText(file));
      setFilename(file.name);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "파일을 읽지 못했어요.");
    } finally {
      setBusy(false);
    }
  }

  async function register() {
    // 원문이 없거나 체크하지 않으면 단추가 이미 꺼져 있다. 여기 오는 건 주로 반이 없거나 날짜가 틀린 때다.
    if (!classroom) {
      setMessage("반을 먼저 골라 주세요.");
      return;
    }
    if (!text || !validPeriod(start, periodEnd) || !reviewed) {
      setMessage("날짜를 다시 봐 주세요.");
      return;
    }
    if (!daily && !childId) {
      setMessage(WHY.child_id);
      return;
    }
    setBusy(true);
    setMessage("");
    setNotices([]);
    try {
      const { notices } = await importDocument({
        kind,
        classId,
        childId: daily ? "" : childId,
        start,
        end: periodEnd,
        title: filename.slice(0, TITLE_MAX),
        body: text,
      });
      setNotices(notices);
      setText("");
      setReviewed(false);
      setMessage(
        notices.length
          ? "등록했어요. 아래 확인할 점을 봐 주세요."
          : "등록했어요. 문서 보관함에 들어갔고 평가 점검 숫자에도 세어져요.",
      );
      onImported();
    } catch (e) {
      const why = invalidFields(e, WHY);
      setMessage(
        isUnauthenticated(e)
          ? "로그인이 필요해요. 다시 로그인한 뒤 이용해 주세요."
          : why.length
            ? why.join(" ")
            : e instanceof Error
              ? e.message
              : "등록하지 못했어요.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.evidence}>
      {/* 「통과 아님」은 확인 칸으로 옮겼다 — 체크로 확인하는 문구라서(§11). 표 안 글만 읽는다는 것은 ADR-057 이 적으라고 했다. */}
      <p className={ws.hint}>
        원에서 쓰던 {DOCUMENT_KINDS[kind]}를 올리면 글자만 읽어 보관함에 넣어요. 파일은 저장하지
        않아요. 한글 파일은 표 안의 글만 읽어요.
      </p>
      {/* 반은 설정에서 고른 반으로 정해진다. 판에 보여야 확인 칸이 「반이 맞는지」를 물을 수 있다. */}
      <p className={ws.hint}>
        반 · <strong>{classroom?.className ?? "아직 고른 반이 없어요"}</strong>
      </p>
      <div className={ws.row}>
        {!daily && (
          <label className={ws.field}>
            아동
            <select
              value={childId}
              onChange={(e) => {
                setChildId(e.target.value);
                setReviewed(false);
              }}
            >
              <option value="">아이 고르기</option>
              {classroom?.children.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className={ws.field}>
          {daily ? "날짜" : "시작일"}
          <input
            type="date"
            value={start}
            onChange={(e) => {
              setStart(e.target.value);
              setReviewed(false);
            }}
          />
        </label>
        {!daily && (
          <label className={ws.field}>
            종료일
            <input
              type="date"
              value={end}
              onChange={(e) => {
                setEnd(e.target.value);
                setReviewed(false);
              }}
            />
          </label>
        )}
      </div>
      <label className={ws.field}>
        파일 (한글 · PDF · 워드 · 텍스트, 5MB까지)
        <input
          type="file"
          disabled={busy}
          accept=".hwp,.hwpx,.pdf,.docx,.txt,.md,.csv"
          onChange={(e) => {
            void pick(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
      </label>
      {text && <div className={ws.preview}>{text}</div>}
      <label className={ws.check}>
        <input type="checkbox" checked={reviewed} onChange={(e) => setReviewed(e.target.checked)} />
        원문이 {subject}와 맞아요. 올렸다고 평가 기준을 채운 것은 아니에요.
      </label>
      <button
        type="button"
        className={ws.primary}
        disabled={busy || !text || !reviewed}
        onClick={() => void register()}
      >
        {busy ? "처리 중…" : "등록하기"}
      </button>
      <Message>{message}</Message>
      {notices.length > 0 && (
        <ul className={styles.notes}>
          {notices.map((n) => (
            <li key={n.code}>{n.message}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
