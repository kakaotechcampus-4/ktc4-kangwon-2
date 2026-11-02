"use client";

import { useState } from "react";
import { DOCUMENT_KINDS, today, validPeriod } from "@/lib/workspace/model";
import { importDocument, type EvidenceNotice } from "@/lib/api/documents";
import { FORM_EXTENSIONS, parseForm, tableText } from "@/lib/api/forms";
import { isUnauthenticated } from "@/lib/api/client";
import { useClientState } from "@/lib/hooks/use-client-state";
import { chosenClassFor, loadClassSettings } from "@/lib/onboarding/settings";
import { Message, useClasses, ws } from "./WorkspaceUI";
import styles from "./Evaluation.module.css";

/** 한글 파일은 서버(§8 parse)가, 나머지는 화면 서버(/api/templates/extract)가 글자를 뽑는다. */
async function readText(file: File) {
  // 화면 서버는 5MB 를 넘으면 거절하지만 §8 parse 는 크기를 보지 않는다. 안내한 한도를 여기서 같이 지킨다.
  if (file.size > 5 * 1024 * 1024) throw new Error("5MB 이하 파일을 업로드해주세요.");
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
    if (!classroom || !text || !validPeriod(start, end) || !reviewed) {
      setMessage("반 · 작성 기간과 원문 확인 여부를 확인해주세요.");
      return;
    }
    setBusy(true);
    setMessage("");
    setNotices([]);
    try {
      const { notices } = await importDocument({
        kind,
        classId,
        childId,
        start,
        end,
        title: filename,
        body: text,
      });
      setNotices(notices);
      setText("");
      setReviewed(false);
      setMessage(
        notices.length
          ? "등록했어요. 아래 확인할 점을 봐주세요."
          : "등록했어요. 문서 보관함에서 볼 수 있고 위 숫자에 반영돼요.",
      );
      onImported();
    } catch (e) {
      setMessage(
        isUnauthenticated(e)
          ? "로그인이 필요해요. 다시 로그인한 뒤 이용해주세요."
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
      <p className={ws.hint}>
        원에서 쓰던 {DOCUMENT_KINDS[kind]}를 올리면 글자만 읽어 보관함에 등록해요. 파일은 저장하지
        않아요. 한글 파일은 표 안의 글만 읽어요. 등록했다고 평가 기준을 채운 것은 아니에요.
      </p>
      <div className={ws.row}>
        <label className={ws.field}>
          아동
          <select
            value={childId}
            onChange={(e) => {
              setChildId(e.target.value);
              setReviewed(false);
            }}
          >
            <option value="">반 전체</option>
            {classroom?.children.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label className={ws.field}>
          시작일
          <input
            type="date"
            value={start}
            onChange={(e) => {
              setStart(e.target.value);
              setReviewed(false);
            }}
          />
        </label>
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
      </div>
      <label className={ws.field}>
        파일 · 한글(HWP · HWPX) / PDF / DOCX / TXT / MD / CSV · 5MB
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
        원문과 등록할 아동 · 반 · 기간이 일치하는지 확인했어요.
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
