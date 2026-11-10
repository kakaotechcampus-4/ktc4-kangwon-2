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
import { calledName, markFor, weekStart } from "@/lib/workspace/child-mark";
import { ChildNote } from "@/components/app/ChildPicker";
import { Posty } from "@/components/app/Posty";
import { WorkspacePage, Empty, Message, useClasses, ws } from "./WorkspaceUI";
import ObservationJournalEditor from "./ObservationJournalEditor";
import { useObservationDomains } from "@/lib/hooks/use-observation-domains";
import { useServerDocument } from "./use-server-document";
import { openPicker } from "./RecordsPage";
import ObservationClassDrafts from "./ObservationClassDrafts";
import oj from "./ObservationJournal.module.css";
import { DOMAIN_LOOK } from "@/lib/workspace/domain-look";
import { Icon } from "@/components/app/icons";

const NO_ENTRY = { classId: "", childId: "", recordId: "", docId: "" };

function messageFor(error: unknown) {
  return error instanceof Error ? error.message : "요청을 처리하지 못했어요.";
}

const pad = (n: number) => String(n).padStart(2, "0");
/** 기간 칩 — 한 번 눌러 기간을 정한다. 끝은 오늘을 넘지 않는다(날짜 칸의 max 와 같다). */
export const PERIODS: { label: string; range: (day: string) => [string, string] }[] = [
  { label: "이번 주", range: (day) => [weekStart(day), day] },
  { label: "이번 달", range: (day) => [`${day.slice(0, 8)}01`, day] },
  {
    label: "지난달",
    range: (day) => {
      const [y, m] = day.split("-").map(Number);
      const [py, pm] = m === 1 ? [y - 1, 12] : [y, m - 1];
      const last = new Date(Date.UTC(py, pm, 0)).getUTCDate();
      return [`${py}-${pad(pm)}-01`, `${py}-${pad(pm)}-${pad(last)}`];
    },
  },
];

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
    return {
      classId: q.get("class") ?? "",
      childId: q.get("child") ?? "",
      recordId: q.get("record") ?? "",
      docId: q.get("doc") ?? "",
    };
  }, NO_ENTRY);
  // 관찰 기록 화면이 반을 주소로 넘긴다. 없으면 주 반을 연다 — 관찰 기록 화면과 같다.
  const [primaryClass] = useClientState(() => chosenClassFor(loadClassSettings())?.id ?? "", "");
  const classId = entry.classId || primaryClass;
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
  /** 반 전체 초안이 도는 중. 그동안 아이 · 기간을 바꾸면 반 전체 목록이 바뀐 채 도는 일이 된다. */
  const [classBusy, setClassBusy] = useState(false);
  // 만드는 동안 고르기를 잠근다 — 늦게 온 응답이 바뀐 선택을 덮지 않게 (하민 교차 검토 F4).
  const locked = busy || classBusy;
  const [openId, setOpenId] = useState("");
  const domains = useObservationDomains();
  // 펴 둔 일지를 주소에 적어 둔다. 다른 화면에 갔다가 뒤로 오면 그 일지가 다시 펴진다(덕철 점검).
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    if ((q.get("doc") ?? "") === openId) return;
    if (openId) q.set("doc", openId);
    else q.delete("doc");
    const rest = q.toString();
    window.history.replaceState?.(null, "", `${window.location.pathname}${rest ? `?${rest}` : ""}`);
  }, [openId]);

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
  // 주소에 일지(`doc`)가 있으면 그 일지를 편다.
  const [entryUsed, setEntryUsed] = useState(false);
  if (records && !entryUsed) {
    setEntryUsed(true);
    if (entry.docId) setOpenId(entry.docId);
    const record = records.find((r) => r.id === entry.recordId);
    if (record) {
      setChildId(record.childId);
      setStart(record.date);
      setEnd(record.date);
    } else if (entry.childId) setChildId(entry.childId);
  }

  const child = classroom?.children.find((c) => c.id === childId);
  const inPeriod = (r: ServerObservation) =>
    r.classId === classId && r.date >= start && r.date <= end;
  const hasRecords = (kidId: string) =>
    (records ?? []).some((r) => r.childId === kidId && inPeriod(r));
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
  // 올린 서류(IMPORT)는 AI 편집기로 열지 않는다 — 문서 보관함이 연다.
  const mine = docs.filter((d) => d.childId === childId && d.origin === "ai");
  const periodOk = validDate(start) && validDate(end) && start <= end;

  /** 반 전체 초안의 다음 아이 — 반 순서로 이 일지 다음, 같은 기간 초안이 있는 첫 아이. */
  function nextDraft(docId: string) {
    const open = docs.find((d) => d.id === docId);
    const order = classroom?.children.map((c) => c.id) ?? [];
    if (!open) return undefined;
    return order
      .slice(order.indexOf(open.childId) + 1)
      .map((kid) =>
        docs.find(
          (d) =>
            d.childId === kid &&
            d.start === open.start &&
            d.end === open.end &&
            d.status === "draft" &&
            d.origin === "ai",
        ),
      )
      .find(Boolean)?.id;
  }
  const next = openId ? nextDraft(openId) : undefined;

  function pickPeriod(range: [string, string]) {
    setStart(range[0]);
    setEnd(range[1]);
    setLeft([]);
  }

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

  // 뒤로 가는 단추는 하나, 늘 「← 관찰 기록」이다(PM 11-10) — 일지를 펴 두었어도 같다.
  // 펴 둔 일지에 고친 것이 있으면 편집기가 링크 누르기를 잡아 한 번 묻는다.
  const back = (
    <Link href="/records" className={ws.secondary}>
      ← 관찰 기록
    </Link>
  );
  // 아이를 고르지 않으면 반 전체 초안이다(ObservationClassDrafts). 설명도 그 동작을 따른다.
  const description = child
    ? `쌓인 관찰 기록으로 ${child.name}의 관찰일지 초안을 만들고, 이 화면에서 바로 고칩니다.`
    : "쌓인 관찰 기록으로 반 아이들의 관찰일지 초안을 한 번에 만들고, 이 화면에서 바로 고칩니다. 한 아이만 만들려면 아이를 고르세요.";
  if (classError)
    return (
      <WorkspacePage title="관찰일지 만들기" description="" action={back}>
        <Message error>{classError}</Message>
      </WorkspacePage>
    );

  return (
    <WorkspacePage title="관찰일지 만들기" description={description} action={back}>
      <Message error>{error}</Message>
      {/* 일지를 펴면 화면 전체를 쓴다 — 칠판 위 쪽지 · 공책과 출력 미리보기가 좁은 칸에 안 들어간다. */}
      {openId ? (
        <JournalEditor
          id={openId}
          onChanged={() => setReload((n) => n + 1)}
          onClose={() => setOpenId("")}
          onNext={next ? () => setOpenId(next) : undefined}
          onOpen={setOpenId}
        />
      ) : (
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
                      {classroom.children.map((c) => {
                        // 숫자는 쓰지 않는다 — 「가람 7」은 무슨 숫자인지 안 읽힌다. 없는 아이만 점선.
                        const none = records !== null && !hasRecords(c.id);
                        return (
                          <button
                            key={c.id}
                            type="button"
                            className={`${ws.recordKid} ${none ? oj.kidNone : ""} tap44`}
                            aria-pressed={c.id === childId}
                            disabled={locked}
                            onClick={() => {
                              setChildId(childId === c.id ? "" : c.id);
                              setLeft([]);
                              setOpenId("");
                            }}
                          >
                            <ChildNote
                              name={c.name}
                              mark={markFor(c.id)}
                              size={24}
                              classNames={classroom.children.map((k) => k.name)}
                            />
                            {c.name}
                            {none && <small>기록 없음</small>}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                  <div className={ws.jrStep}>
                    <h2 id="jr-period">기간</h2>
                    <div className={oj.chips} role="group" aria-labelledby="jr-period">
                      {PERIODS.map(({ label, range }) => {
                        const [from, to] = range(today());
                        return (
                          <button
                            key={label}
                            type="button"
                            className={oj.chip}
                            aria-pressed={from === start && to === end}
                            disabled={locked}
                            onClick={() => pickPeriod([from, to])}
                          >
                            {label}
                          </button>
                        );
                      })}
                    </div>
                    <div className={ws.jrPeriod}>
                      <input
                        type="date"
                        aria-label="시작일"
                        disabled={locked}
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
                        disabled={locked}
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
                                disabled={locked}
                                onChange={(e) =>
                                  setLeft((prev) =>
                                    e.target.checked
                                      ? prev.filter((id) => id !== r.id)
                                      : [...prev, r.id],
                                  )
                                }
                              />
                              <span>
                                {/* 영역은 관찰 기록 카드 칩과 같은 그림 · 색 */}
                                <small>
                                  {shortDate(r.date)}
                                  <span
                                    className={ws.recordDomain}
                                    data-tone={DOMAIN_LOOK[r.domain]?.tone}
                                  >
                                    {DOMAIN_LOOK[r.domain] && (
                                      <Icon
                                        name={DOMAIN_LOOK[r.domain].icon}
                                        width={13}
                                        height={13}
                                      />
                                    )}
                                    {r.domain}
                                  </span>
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
            {child && !mine.length ? (
              // 초안 전 — 고른 기록이 어느 영역에 몰렸는지, 빈 영역은 어디인지 칠판에 먼저 보여 준다.
              <SourceBoard
                name={child.name}
                sources={sources}
                domains={domains}
                period={periodWord(start, end)}
              />
            ) : !child && classroom?.children.length ? (
              // 아이를 고르지 않았으면 반 전체 — 한 번 눌러 기록 있는 아이 전부 (ADR-083).
              <ObservationClassDrafts
                kids={classroom.children}
                records={records ?? []}
                docs={docs}
                start={start}
                end={end}
                classId={classId}
                onOpen={setOpenId}
                onBusy={setClassBusy}
                onChanged={() => setReload((n) => n + 1)}
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
                        <button type="button" disabled={busy} onClick={() => setOpenId(d.id)}>
                          <b>{d.title}</b>
                          <small>
                            {d.start === d.end ? d.start : `${d.start} ~ ${d.end}`} ·{" "}
                            {statusLabel(d)}
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
      )}
    </WorkspacePage>
  );
}

/** 펴 놓은 관찰일지. 서버에 바로 쓴다 — 저장 · 확정은 문서 보관함과 같은 한 벌이다. */
function JournalEditor({
  id,
  onChanged,
  onClose,
  onNext,
  onOpen,
}: {
  id: string;
  onChanged: () => void;
  onClose: () => void;
  onNext?: () => void;
  /** 다시 만든 초안을 편다. */
  onOpen: (id: string) => void;
}) {
  const edit = useServerDocument(id, { onChanged, onRemoved: onClose });
  const domains = useObservationDomains();
  if (edit.status === "error") return <Message error>{edit.error}</Message>;
  if (!edit.doc || !edit.server) return <p className={ws.hint}>일지를 불러오는 중…</p>;
  return (
    <ObservationJournalEditor
      key={edit.doc.id}
      initial={edit.doc}
      server={edit.server}
      domains={domains}
      onNext={onNext}
      onRemake={async () => {
        // 같은 아이 · 기간 · 근거로 「넣어서 다시」. 또 실패하면 서버가 옛 초안을 남기고 오류를 준다.
        const d = edit.doc!;
        const made = await createDocument({
          kind: "observation",
          classId: d.classId,
          childId: d.childId,
          start: d.start,
          end: d.end,
          sourceIds: d.sources.map((s) => s.id),
          replaceDraft: true,
        });
        onOpen(made.id);
        onChanged();
      }}
    />
  );
}

/** 기간 칩과 같은 기간이면 그 이름(「이번 주」), 아니면 날짜로. */
function periodWord(start: string, end: string) {
  const chip = PERIODS.find((p) => {
    const [s, e] = p.range(today());
    return s === start && e === end;
  });
  return chip ? chip.label : `${shortDate(start)} ~ ${shortDate(end)}`;
}

/**
 * 초안 만들기 전 오른쪽 칠판 — 「가람이의 이번 주」.
 *
 * 다섯 영역(두 축 원은 두 칸)을 늘 같은 크기로 세운다. 고른 기록이 있는 영역은 그 영역 색 쪽지에
 * 건수를 크게, 없는 영역은 점선 빈 쪽지에 「아직 없어요」. 영역 색 · 그림은 관찰 기록 카드와 같다.
 * 숫자와 영역 이름은 그림이 아니라 글자라 화면 낭독기가 그대로 읽는다.
 */
function SourceBoard({
  name,
  sources,
  domains,
  period,
}: {
  name: string;
  sources: ServerObservation[];
  domains: readonly string[];
  period: string;
}) {
  const count = (d: string) => sources.filter((r) => r.domain === d).length;
  const first = sources[0]?.date;
  const last = sources[sources.length - 1]?.date;
  const missing = domains.filter((d) => !count(d)).length;
  return (
    <section className={`chalkboard ${ws.jbBoard}`} aria-labelledby="jb-title">
      <h2 id="jb-title">
        {calledName(name)}의 {period}
      </h2>
      {sources.length ? (
        <p className={ws.jbStat}>
          <b>{sources.length}</b>건 골랐어요
          <span>
            {first === last ? shortDate(first) : `${shortDate(first)} ~ ${shortDate(last)}`}
          </span>
        </p>
      ) : (
        <p className={ws.jbStat}>아직 고른 기록이 없어요</p>
      )}
      <ul className={ws.jbSlots} data-count={domains.length} aria-label="영역별로 고른 기록">
        {domains.map((d) => {
          const n = count(d);
          const look = DOMAIN_LOOK[d];
          return (
            <li key={d} data-tone={n ? look?.tone : undefined} data-none={!n || undefined}>
              {look && (
                <span className={ws.jbIcon} aria-hidden="true">
                  <Icon name={look.icon} width={14} height={14} />
                </span>
              )}
              <span className={ws.jbName}>{d}</span>
              {n ? (
                <span className={ws.jbCount}>
                  <b>{n}</b>건
                </span>
              ) : (
                <em>아직 없어요</em>
              )}
            </li>
          );
        })}
      </ul>
      <div className={ws.jbFoot}>
        <span className={ws.jbPostyWide}>
          <Posty pose="hand" face="base" tone="note" size={46} label={null} />
        </span>
        <span className={ws.jbPostyNarrow}>
          <Posty pose="point" face="base" tone="note" size={46} label={null} />
        </span>
        <p>
          「초안 만들기」를 누르면 이 칠판에 바로 초안이 열려요.
          {missing > 0 && " 빈 영역은 초안에 「이 영역 관찰이 없어요」로 남아요."}
        </p>
      </div>
    </section>
  );
}

/** 확정이 stale 을 가리지 않는다 — 확정본도 근거가 바뀌면 다시 봐야 한다. */
function statusLabel(d: DocumentSummary) {
  if (d.status === "confirmed") return d.stale ? "확정 · 다시 확인 필요" : "확정";
  return d.stale ? "다시 볼 것 있음" : "초안";
}

const WEEK = ["일", "월", "화", "수", "목", "금", "토"];
/** 「2026-11-03」 → 「11/3(화)」 */
function shortDate(date: string) {
  const at = new Date(`${date}T00:00:00Z`);
  if (Number.isNaN(at.getTime())) return date;
  return `${at.getUTCMonth() + 1}/${at.getUTCDate()}(${WEEK[at.getUTCDay()]})`;
}
