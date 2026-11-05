"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { today, validDate } from "@/lib/workspace/model";
import { listRecords } from "@/lib/api/records";
import type { ServerObservation } from "@/lib/api/observations";
import { createDocument, listDocuments, type DocumentSummary } from "@/lib/api/documents";
import { classServerId } from "@/lib/api/onboarding";
import { useClientState } from "@/lib/hooks/use-client-state";
import { chosenClassFor, loadClassSettings } from "@/lib/onboarding/settings";
import { markFor, weekStart } from "@/lib/workspace/child-mark";
import { ChildNote } from "@/components/app/ChildPicker";
import { Posty } from "@/components/app/Posty";
import { WorkspacePage, Empty, Message, useClasses, ws } from "./WorkspaceUI";
import DocumentEditor from "./DocumentEditor";
import { useServerDocument } from "./use-server-document";
import { openPicker } from "./RecordsPage";

const NO_ENTRY = { childId: "", recordId: "" };

function messageFor(error: unknown) {
  return error instanceof Error ? error.message : "요청을 처리하지 못했어요.";
}

/**
 * 관찰일지 만들기 — **관찰 기록 화면 바로 아래(/records/journal)** 에서 만들고 끝까지 쓴다.
 *
 * 전에는 「관찰일지 만들기」가 문서 보관함으로 보냈다. 보관함은 다 쓴 문서가 쌓이는 곳이고,
 * 기록을 남긴 교사는 방금 적은 기록을 근거로 일지를 손보러 온 것이다. 일과 기록 화면이
 * 보육일지를 그 자리에서 쓰는 것과 같은 짜임이다.
 *
 * 아이 한 명 · 기간 하나 · 그 사이 그 아이 기록이 근거다 (api-spec §11).
 */
export default function ObservationJournalPage() {
  const [entry] = useClientState(() => {
    if (typeof window === "undefined") return NO_ENTRY;
    const q = new URLSearchParams(window.location.search);
    return { childId: q.get("child") ?? "", recordId: q.get("record") ?? "" };
  }, NO_ENTRY);
  const [classId] = useClientState(() => chosenClassFor(loadClassSettings())?.id ?? "", "");
  const [classError, setClassError] = useState("");
  const classes = useClasses(setClassError);
  const classroom = classes.find((c) => c.id === classId);
  const serverClass = classId ? classServerId(classId) : null;

  const [records, setRecords] = useState<ServerObservation[] | null>(null);
  const [docs, setDocs] = useState<DocumentSummary[]>([]);
  const [reload, setReload] = useState(0);
  const [error, setError] = useState("");
  const [childId, setChildId] = useState("");
  const [start, setStart] = useState(() => weekStart(today()));
  const [end, setEnd] = useState(today);
  /** 근거에서 뺀 기록. 기본은 기간 안 그 아이 기록 전부다. */
  const [left, setLeft] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [openId, setOpenId] = useState("");

  useEffect(() => {
    if (!classId) return;
    let live = true;
    listRecords(classId)
      .then((items) => {
        if (live) setRecords(items);
      })
      .catch((e) => {
        if (!live) return;
        setRecords([]);
        setError(messageFor(e));
      });
    return () => {
      live = false;
    };
  }, [classId]);

  useEffect(() => {
    if (serverClass === null) return;
    let live = true;
    listDocuments({ kind: "observation", class_id: serverClass })
      .then((items) => {
        if (live) setDocs(items);
      })
      .catch((e) => {
        if (live) setError(messageFor(e));
      });
    return () => {
      live = false;
    };
  }, [serverClass, reload]);

  // 기록 카드의 「이 기록으로 일지 만들기」는 그 기록 하루로, 주소에 아이만 있으면 그 아이로 연다.
  const [entryUsed, setEntryUsed] = useState(false);
  if (records && !entryUsed) {
    setEntryUsed(true);
    const record = records.find((r) => r.id === entry.recordId);
    if (record) {
      setChildId(record.childId);
      setStart(record.date);
      setEnd(record.date);
    } else if (entry.childId) setChildId(entry.childId);
  }

  const child = classroom?.children.find((c) => c.id === childId);
  const inRange = useMemo(
    () =>
      (records ?? [])
        .filter(
          (r) => r.classId === classId && r.childId === childId && r.date >= start && r.date <= end,
        )
        .sort((a, b) => a.date.localeCompare(b.date)),
    [records, classId, childId, start, end],
  );
  const sources = inRange.filter((r) => !left.includes(r.id));
  const mine = docs.filter((d) => d.childId === childId);
  const periodOk = validDate(start) && validDate(end) && start <= end;

  const blocked = !child
    ? "아이를 먼저 골라 주세요."
    : !periodOk
      ? "기간을 확인해 주세요."
      : !sources.length
        ? "이 기간에 고른 기록이 없어요."
        : "";

  async function make() {
    if (busy || blocked) return;
    setBusy(true);
    setError("");
    try {
      const made = await createDocument({
        kind: "observation",
        classId,
        childId,
        start,
        end,
        sourceIds: sources.map((r) => r.id),
      });
      setOpenId(made.id);
      setReload((n) => n + 1);
    } catch (e) {
      // 실패해도 아이 · 기간 · 근거는 그대로 둔다.
      setError(messageFor(e));
    } finally {
      setBusy(false);
    }
  }

  const back = (
    <Link href="/records" className={ws.secondary}>
      ← 관찰 기록
    </Link>
  );
  if (classError)
    return (
      <WorkspacePage title="관찰일지 만들기" description="" action={back}>
        <Message error>{classError}</Message>
      </WorkspacePage>
    );

  return (
    <WorkspacePage
      title="관찰일지 만들기"
      description="쌓인 관찰 기록으로 한 아이의 관찰일지 초안을 만들고, 이 화면에서 바로 고칩니다."
      action={back}
    >
      <Message error>{error}</Message>
      <div className={`${ws.grid} ${ws.recordGrid}`}>
        <div className={ws.side}>
          <section className={`${ws.card} ${ws.jrSetup}`}>
            {!classroom?.children.length ? (
              <Empty title="먼저 아이를 등록해 주세요">
                <Link href="/onboarding">아이 등록하기 →</Link>
              </Empty>
            ) : (
              <>
                <div className={ws.jrStep}>
                  <h2 id="jr-kids">누구 관찰일지인가요?</h2>
                  <div className={ws.recordKids} role="group" aria-labelledby="jr-kids">
                    {classroom.children.map((c) => (
                      <button
                        key={c.id}
                        type="button"
                        className={ws.recordKid}
                        aria-pressed={c.id === childId}
                        onClick={() => {
                          setChildId(c.id);
                          setLeft([]);
                          setOpenId("");
                        }}
                      >
                        <ChildNote name={c.name} mark={markFor(c.id)} size={24} />
                        {c.name}
                      </button>
                    ))}
                  </div>
                </div>
                <div className={ws.jrStep}>
                  <h2>기간</h2>
                  <div className={ws.jrPeriod}>
                    <input
                      type="date"
                      aria-label="시작일"
                      onClick={(e) => openPicker(e.currentTarget)}
                      value={start}
                      max={end || today()}
                      onChange={(e) => {
                        setStart(e.target.value);
                        setLeft([]);
                      }}
                    />
                    <span aria-hidden="true">~</span>
                    <input
                      type="date"
                      aria-label="종료일"
                      onClick={(e) => openPicker(e.currentTarget)}
                      value={end}
                      min={start}
                      max={today()}
                      onChange={(e) => {
                        setEnd(e.target.value);
                        setLeft([]);
                      }}
                    />
                  </div>
                </div>
                <div className={ws.jrStep}>
                  <h2>
                    근거로 쓸 기록 <span>{child ? `${sources.length}건` : ""}</span>
                  </h2>
                  {!child ? (
                    <p className={ws.hint}>아이를 고르면 그 아이 기록이 여기 모여요.</p>
                  ) : records === null ? (
                    <p className={ws.hint}>기록을 불러오고 있어요.</p>
                  ) : !inRange.length ? (
                    <p className={ws.hint}>
                      이 기간에 {child.name} 기록이 없어요. 기간을 넓혀 보세요.
                    </p>
                  ) : (
                    <ul className={ws.jrSources}>
                      {inRange.map((r) => (
                        <li key={r.id}>
                          <label>
                            <input
                              type="checkbox"
                              checked={!left.includes(r.id)}
                              onChange={(e) =>
                                setLeft((prev) =>
                                  e.target.checked
                                    ? prev.filter((id) => id !== r.id)
                                    : [...prev, r.id],
                                )
                              }
                            />
                            <span>
                              <small>
                                {shortDate(r.date)} · {r.domain}
                              </small>
                              {r.fact}
                            </span>
                          </label>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <div className={ws.jrMake}>
                  {blocked && <small>{blocked}</small>}
                  <button
                    type="button"
                    className={ws.primary}
                    disabled={!!blocked || busy}
                    onClick={make}
                  >
                    {busy ? "만드는 중…" : "초안 만들기"}
                  </button>
                </div>
              </>
            )}
          </section>
        </div>

        <div className={ws.stack}>
          {openId ? (
            <JournalEditor
              id={openId}
              onChanged={() => setReload((n) => n + 1)}
              onClose={() => setOpenId("")}
            />
          ) : (
            <section className={`${ws.card} ${ws.jrList}`}>
              <h2>{child ? `${child.name} 관찰일지` : "만든 관찰일지"}</h2>
              {!child ? (
                <div className={ws.jrEmpty}>
                  <Posty pose="wave" face="base" tone="note" size={72} label={null} />
                  <p>왼쪽에서 아이를 고르면, 그 아이 기록으로 초안을 만들 수 있어요.</p>
                </div>
              ) : !mine.length ? (
                <div className={ws.jrEmpty}>
                  <Posty pose="hand" face="base" tone="lilac" size={72} label={null} />
                  <p>아직 만든 관찰일지가 없어요. 「초안 만들기」를 누르면 여기서 바로 열려요.</p>
                </div>
              ) : (
                <ul className={ws.jrDocs}>
                  {mine.map((d) => (
                    <li key={d.id}>
                      <button type="button" onClick={() => setOpenId(d.id)}>
                        <b>{d.title}</b>
                        <small>
                          {d.start === d.end ? d.start : `${d.start} ~ ${d.end}`} ·{" "}
                          {d.status === "confirmed" ? "확정" : d.stale ? "다시 볼 것 있음" : "초안"}
                        </small>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}
        </div>
      </div>
    </WorkspacePage>
  );
}

/** 펴 놓은 관찰일지. 문서 보관함과 같은 편집기를 쓴다 — 서버에 바로 쓴다. */
function JournalEditor({
  id,
  onChanged,
  onClose,
}: {
  id: string;
  onChanged: () => void;
  onClose: () => void;
}) {
  const edit = useServerDocument(id, { onChanged, onRemoved: onClose });
  return (
    <section className={`${ws.card} ${ws.journalCard}`} aria-label="관찰일지">
      <button type="button" className={ws.link} onClick={onClose}>
        ← 관찰일지 목록
      </button>
      {edit.status === "loading" && <p className={ws.hint}>일지를 불러오는 중…</p>}
      {edit.status === "error" && <Message error>{edit.error}</Message>}
      {edit.doc && (
        <DocumentEditor
          key={edit.doc.id}
          initial={edit.doc}
          server={edit.server}
          onSave={() => true}
        />
      )}
    </section>
  );
}

const WEEK = ["일", "월", "화", "수", "목", "금", "토"];
/** 「2026-11-03」 → 「11/3(화)」 */
function shortDate(date: string) {
  const at = new Date(`${date}T00:00:00Z`);
  if (Number.isNaN(at.getTime())) return date;
  return `${at.getUTCMonth() + 1}/${at.getUTCDate()}(${WEEK[at.getUTCDay()]})`;
}
