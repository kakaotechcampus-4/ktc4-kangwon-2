"use client";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import {
  DOCUMENT_KINDS,
  today,
  validPeriod,
  compareEvidence,
  invalidateDependents,
  assertDocumentUnchanged,
  type DocumentKind,
  type SavedDocument,
} from "@/lib/workspace/model";
import { useWorkspace } from "@/lib/workspace/store";
import { isUnauthenticated, invalidFields } from "@/lib/api/client";
import { listRecords } from "@/lib/api/records";
import type { ServerObservation } from "@/lib/api/observations";
import {
  listDocuments,
  getDocument,
  createDocument,
  updateDocument,
  confirmDocument,
  unconfirmDocument,
  refreshDocument,
  deleteDocument,
  documentServerId,
  isRecordKind,
  RECORD_KINDS,
  type DocumentSummary,
  type RecordKind,
} from "@/lib/api/documents";
import DocumentEditor from "./DocumentEditor";
import { createSelection } from "./document-selection";
import { WorkspacePage, Empty, Message, useClasses, ws } from "./WorkspaceUI";
import {
  WorkspaceViewState,
  FieldError,
  fieldErrorProps,
  type ViewStatus,
} from "./WorkspaceViewState";

/** 서버가 짚는 칸 이름 → 화면 입력 (docs/api-spec.md §11 의 POST body). */
const FIELD_INPUT: Record<string, string> = {
  kind: "kind",
  class_id: "classId",
  child_id: "childId",
  start: "start",
  end: "end",
  // 근거는 `source_ids` 로도, `sources.{id}` 로도 온다. 화면에는 선택 목록 하나뿐이다.
  source_ids: "sources",
  sources: "sources",
};
/** 근거 후보 하나. 주간 보육일지는 확정된 일일 보육일지, 나머지는 관찰 기록이다 (§11). */
type Candidate = { id: string; date: string; label: string };

function messageFor(error: unknown) {
  if (isUnauthenticated(error)) return "로그인이 필요해요. 다시 로그인한 뒤 이용해주세요.";
  return error instanceof Error ? error.message : "요청을 처리하지 못했어요.";
}

export default function DocumentsPage() {
  const { data, error, save } = useWorkspace();
  const [mode, setMode] = useState<"library" | "create">("library");
  const [kind, setKind] = useState<DocumentKind>("observation");
  const [classId, setClassId] = useState("");
  const [childId, setChildId] = useState("");
  const [start, setStart] = useState(today);
  const [end, setEnd] = useState(today);
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [invalid, setInvalid] = useState<string[]>([]);
  const classes = useClasses(setMessage);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");

  const [serverDocs, setServerDocs] = useState<DocumentSummary[]>([]);
  const [listStatus, setListStatus] = useState<ViewStatus>("loading");
  const [listError, setListError] = useState("");
  const [records, setRecords] = useState<ServerObservation[]>([]);
  // 늦게 온 옛 응답이 최신 화면을 덮지 않게 요청마다 번호를 매긴다.
  const latestList = useRef(0);
  const [selection] = useState(() =>
    createSelection(
      {
        get: getDocument,
        update: updateDocument,
        confirm: confirmDocument,
        unconfirm: unconfirmDocument,
        refresh: refreshDocument,
        remove: deleteDocument,
      },
      messageFor,
    ),
  );
  const chosen = useSyncExternalStore(selection.subscribe, selection.get, selection.get);
  const active = chosen.active;

  useEffect(() => {
    const mine = ++latestList.current;
    Promise.all([listDocuments(), listRecords()])
      .then(([documents, observations]) => {
        if (mine !== latestList.current) return;
        setServerDocs(documents);
        setRecords(observations);
        setListError("");
        setListStatus("ready");
      })
      .catch((e) => {
        if (mine !== latestList.current) return;
        setListError(messageFor(e));
        setListStatus("error");
      });
    return () => {
      latestList.current += 1;
      selection.leaveCreation();
    };
  }, [selection]);
  async function reloadList() {
    const mine = ++latestList.current;
    try {
      const [documents, observations] = await Promise.all([listDocuments(), listRecords()]);
      if (mine !== latestList.current) return;
      setServerDocs(documents);
      setRecords(observations);
      setListError("");
      setListStatus("ready");
    } catch (e) {
      if (mine !== latestList.current) return;
      setListError(messageFor(e));
      setListStatus("error");
    }
  }

  const [recordId] = useState(() =>
    typeof window === "undefined"
      ? null
      : new URLSearchParams(window.location.search).get("record"),
  );
  const [prefilled, setPrefilled] = useState(false);
  if (listStatus === "ready" && !prefilled) {
    setPrefilled(true);
    const record = records.find((r) => r.id === recordId);
    if (record) {
      setMode("create");
      setClassId(record.classId);
      setChildId(record.childId);
      setStart(record.date);
      setEnd(record.date);
      setSelected([record.id]);
    }
  }

  const classroom = classes.find((c) => c.id === classId);
  const child = classroom?.children.find((c) => c.id === childId);
  const candidates: Candidate[] = useMemo(
    () =>
      kind === "weeklyLog"
        ? serverDocs
            .filter(
              (d) =>
                d.kind === "dailyLog" &&
                d.status === "confirmed" &&
                d.classId === classId &&
                (!childId || d.childId === childId) &&
                d.start >= start &&
                d.end <= end,
            )
            .map((d) => ({ id: d.id, date: d.start, label: d.title }))
        : records
            .filter(
              (r) =>
                r.classId === classId &&
                (!childId || r.childId === childId) &&
                r.date >= start &&
                r.date <= end,
            )
            .map((r) => ({ id: r.id, date: r.date, label: r.fact })),
    [kind, serverDocs, records, classId, childId, start, end],
  );
  const sources = candidates.filter((s) => selected.includes(s.id));

  // 계획안과 등록 증빙은 아직 서버에 없다 — 보관함에서는 계속 브라우저 저장소를 본다.
  const localDocs = data.documents.filter((d) => d.origin === "import" || !isRecordKind(d.kind));
  const library = [
    ...serverDocs.map((d) => ({
      id: d.id,
      title: d.title,
      className: d.className,
      childName: d.childName,
      kind: d.kind,
      status: d.status,
      start: d.start,
      updatedAt: d.updatedAt,
      sources: d.sourcesCount,
      stale: d.stale,
    })),
    ...localDocs.map((d) => ({
      id: d.id,
      title: d.title,
      className: d.className,
      childName: d.childName,
      kind: d.kind,
      status: d.status,
      start: d.start,
      updatedAt: d.updatedAt,
      sources: d.sources.length,
      stale: false,
    })),
  ]
    .filter(
      (d) =>
        (filter === "all" || d.status === filter) &&
        `${d.title} ${d.childName} ${d.className}`.includes(search),
    )
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));

  const activeServerId = documentServerId(active);
  const localCurrent = data.documents.find((d) => d.id === active);
  // 서버 문서는 `active` 와 같은 문서일 때만 화면에 올린다.
  const serverCurrent = chosen.detail?.id === active ? chosen.detail : null;
  const current = activeServerId === null ? localCurrent : serverCurrent;
  // 목록 재조회 실패가 이미 표시 중인 목록과 편집기를 숨기지 않게 한다.
  const keepDocuments =
    listStatus === "error" && (serverDocs.length > 0 || localDocs.length > 0 || !!current);

  /** 고친 칸만 지운다. 서버가 함께 짚은 다른 칸은 아직 그대로다. */
  const clearInvalid = (name: string) =>
    setInvalid((prev) => (prev.includes(name) ? prev.filter((f) => f !== name) : prev));

  function open(id: string) {
    setMessage("");
    selection.select(id, documentServerId(id));
  }

  async function generate() {
    if (
      busy ||
      !classroom ||
      !validPeriod(start, end) ||
      !sources.length ||
      !isRecordKind(kind) ||
      ((kind === "observation" || kind === "assessment") && !child) ||
      (kind === "dailyLog" && start !== end)
    ) {
      setMessage(
        "반·아동·기간·근거 기록을 확인해주세요. 일일 보육일지는 같은 날짜로 설정해주세요.",
      );
      return;
    }
    setBusy(true);
    setMessage("");
    const creation = selection.beginCreation();
    try {
      // 사실·해석·지원은 서버가 만든다 — 화면이 초안을 짓지 않는다 (§11).
      const created = await createDocument({
        kind: kind as RecordKind,
        classId,
        childId,
        start,
        end,
        sourceIds: sources.map((s) => s.id),
      });
      if (creation.adopt(created)) {
        setSelected([]);
        setInvalid([]);
        setMode("library");
        setMessage("원본 사실을 담은 초안을 만들었어요. 해석과 지원을 검토해주세요.");
      }
      // 다른 문서를 편집 중이어도 생성 자체는 성공했다. 선택은 두고 목록만 갱신한다.
      await reloadList();
    } catch (e) {
      // 실패해도 반·아동·기간·근거 선택을 그대로 둔다.
      if (creation.isCurrent()) {
        setMessage(messageFor(e));
        setInvalid(invalidFields(e, FIELD_INPUT));
      }
    } finally {
      setBusy(false);
    }
  }

  const serverActions = serverCurrent
    ? {
        stale: serverCurrent.stale,
        pending: chosen.pending !== "",
        reload: selection.reload,
        save: async (sections: SavedDocument["sections"], reviewNote: string) => {
          const saved = await selection.save(sections, reviewNote);
          void reloadList();
          return saved;
        },
        saveAndConfirm: async (sections: SavedDocument["sections"], reviewNote: string) => {
          const confirmed = await selection.saveAndConfirm(sections, reviewNote);
          void reloadList();
          return confirmed;
        },
        unconfirm: async () => {
          const next = await selection.unconfirm();
          void reloadList();
          return next;
        },
        refresh: async () => {
          const next = await selection.refresh();
          void reloadList();
          return next;
        },
        remove: async () => {
          await selection.remove();
          setMessage("문서를 삭제했어요.");
          await reloadList();
        },
      }
    : undefined;

  return (
    <WorkspacePage
      title="문서 보관함"
      description="기록에서 시작해, 선생님의 검토로 완성되는 우리 반 문서."
    >
      <div className={ws.hero}>
        <div>
          <div className={ws.eyebrow}>DOCUMENTS · 기록을 의미 있는 문서로</div>
          <h2>사실은 그대로, 지원은 구체적으로.</h2>
          <p>일일·주간 보육일지부터 관찰일지와 영유아 평가까지 한곳에서 관리해요.</p>
        </div>
        <button
          className={ws.primary}
          onClick={() => {
            selection.leaveCreation();
            setMode(mode === "create" ? "library" : "create");
            setMessage("");
          }}
        >
          {mode === "create" ? "보관함 보기" : "＋ 기록으로 문서 만들기"}
        </button>
      </div>
      <Message error>{error}</Message>
      <Message>{message}</Message>
      {mode === "create" ? (
        <div className={ws.grid}>
          <section className={ws.card}>
            <h2>문서 작성 조건</h2>
            <div className={ws.form}>
              <label className={ws.field}>
                문서 종류
                <select
                  disabled={busy}
                  value={kind}
                  {...fieldErrorProps("kind", invalid)}
                  onChange={(e) => {
                    setKind(e.target.value as DocumentKind);
                    setSelected([]);
                    clearInvalid("kind");
                  }}
                >
                  {RECORD_KINDS.map((k) => (
                    <option key={k} value={k}>
                      {DOCUMENT_KINDS[k]}
                    </option>
                  ))}
                </select>
                <FieldError name="kind" invalid={invalid} />
              </label>
              <div className={ws.row}>
                <label className={ws.field}>
                  담당 반
                  <select
                    disabled={busy}
                    value={classId}
                    {...fieldErrorProps("classId", invalid)}
                    onChange={(e) => {
                      setClassId(e.target.value);
                      setChildId("");
                      setSelected([]);
                      clearInvalid("classId");
                    }}
                  >
                    <option value="">반 선택</option>
                    {classes.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.className || "이름 없는 반"}
                      </option>
                    ))}
                  </select>
                  <FieldError name="classId" invalid={invalid} />
                </label>
                <label className={ws.field}>
                  대상 아동
                  <select
                    disabled={busy}
                    value={childId}
                    {...fieldErrorProps("childId", invalid)}
                    onChange={(e) => {
                      setChildId(e.target.value);
                      setSelected([]);
                      clearInvalid("childId");
                    }}
                  >
                    <option value="">반 전체</option>
                    {classroom?.children.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                  <FieldError name="childId" invalid={invalid} />
                </label>
              </div>
              <div className={ws.row}>
                <label className={ws.field}>
                  시작일
                  <input
                    disabled={busy}
                    type="date"
                    value={start}
                    {...fieldErrorProps("start", invalid)}
                    onChange={(e) => {
                      setStart(e.target.value);
                      setSelected([]);
                      clearInvalid("start");
                    }}
                  />
                  <FieldError name="start" invalid={invalid} />
                </label>
                <label className={ws.field}>
                  종료일
                  <input
                    disabled={busy}
                    type="date"
                    value={end}
                    {...fieldErrorProps("end", invalid)}
                    onChange={(e) => {
                      setEnd(e.target.value);
                      setSelected([]);
                      clearInvalid("end");
                    }}
                  />
                  <FieldError name="end" invalid={invalid} />
                </label>
              </div>
              <p className={ws.hint}>
                {kind === "weeklyLog"
                  ? "주간 보육일지는 검토가 완료된 일일 보육일지만 근거로 사용해요."
                  : kind === "assessment"
                    ? "한 아동의 누적 관찰을 선택해주세요. 기록에 드러난 변화만 다루며 발달을 진단하지 않아요."
                    : "관찰일지는 아동을 선택하고, 일일 보육일지는 시작·종료일을 같은 날짜로 지정해주세요."}
              </p>
              <button
                className={ws.primary}
                disabled={busy || !sources.length || listStatus !== "ready"}
                onClick={generate}
              >
                {busy ? "초안 작성 중…" : "초안 만들기"}
              </button>
              <Link className={ws.link} href="/records">
                새 관찰 기록 입력 →
              </Link>
            </div>
          </section>
          <section className={ws.card}>
            <div className={ws.between}>
              <h2>문서에 사용할 근거</h2>
              <span className={ws.badge}>{sources.length}건 선택</span>
            </div>
            <p className={ws.hint}>선택한 반·아동·기간의 기록만 표시됩니다.</p>
            <WorkspaceViewState
              status={listStatus}
              error={listError}
              loading="근거 기록을 불러오고 있어요."
              empty={
                !candidates.length && (
                  <Empty title="조건에 맞는 근거가 없어요">
                    날짜를 변경하거나{" "}
                    {kind === "weeklyLog"
                      ? "일일 보육일지를 먼저 작성하고 확정해주세요."
                      : "관찰 기록을 먼저 입력해주세요."}
                  </Empty>
                )
              }
            >
              <button
                disabled={busy}
                className={ws.secondary}
                onClick={() =>
                  setSelected(
                    sources.length === candidates.length ? [] : candidates.map((s) => s.id),
                  )
                }
              >
                {sources.length === candidates.length ? "선택 해제" : "모두 선택"}
              </button>
              <div role="group" className={ws.scroll} {...fieldErrorProps("sources", invalid)}>
                {candidates.map((s) => (
                  <label key={s.id} className={ws.check}>
                    <input
                      type="checkbox"
                      disabled={busy}
                      checked={selected.includes(s.id)}
                      onChange={(e) => {
                        setSelected((prev) =>
                          e.target.checked ? [...prev, s.id] : prev.filter((id) => id !== s.id),
                        );
                        clearInvalid("sources");
                      }}
                    />
                    <span>
                      <b>{s.date}</b>
                      <small>{s.label}</small>
                    </span>
                  </label>
                ))}
              </div>
              <FieldError name="sources" invalid={invalid} />
            </WorkspaceViewState>
          </section>
        </div>
      ) : (
        <>
          <div className={ws.between}>
            <div className={ws.pills}>
              {[
                ["all", "전체"],
                ["draft", "검토 중"],
                ["confirmed", "확정"],
              ].map(([id, label]) => (
                <button
                  key={id}
                  aria-pressed={filter === id}
                  className={filter === id ? ws.selected : undefined}
                  onClick={() => setFilter(id)}
                >
                  {label}{" "}
                  {
                    [...serverDocs, ...localDocs].filter((d) => id === "all" || d.status === id)
                      .length
                  }
                </button>
              ))}
            </div>
            <Link className={ws.link} href="/evaluation">
              평가제·증빙 점검 →
            </Link>
          </div>
          <input
            className={ws.input}
            style={{ margin: "17px 0" }}
            aria-label="문서 검색"
            placeholder="문서 제목, 반, 아동으로 검색"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {listStatus === "error" && (
            <div>
              {keepDocuments && <Message error>{listError}</Message>}
              <button className={ws.secondary} disabled={busy} onClick={reloadList}>
                다시 시도
              </button>
            </div>
          )}
          <WorkspaceViewState
            status={keepDocuments ? "ready" : listStatus}
            error={listError}
            loading="문서를 불러오고 있어요."
            empty={
              !library.length &&
              !(keepDocuments && current) && (
                <Empty title="보관된 문서가 없어요">관찰 기록으로 첫 문서를 만들어보세요.</Empty>
              )
            }
          >
            <div className={ws.grid}>
              <div className={ws.list}>
                {library.map((d) => (
                  <button
                    key={d.id}
                    className={`${ws.item} ${active === d.id ? ws.selected : ""}`}
                    onClick={() => open(d.id)}
                  >
                    <div className={ws.between}>
                      <span className={ws.badge}>
                        {d.status === "confirmed" ? "확정" : "검토 중"}
                        {d.stale ? " · 재검토" : ""}
                      </span>
                      <span className={ws.muted}>{d.start}</span>
                    </div>
                    <h3 style={{ marginTop: 13 }}>{d.title}</h3>
                    <p className={ws.muted}>
                      {d.className} · {DOCUMENT_KINDS[d.kind]} · 근거 {d.sources}건
                    </p>
                  </button>
                ))}
              </div>
              <WorkspaceViewState
                status={chosen.status}
                error={chosen.error}
                loading="문서를 불러오고 있어요."
                empty={
                  !current && (
                    <Empty title="확인할 문서를 선택해주세요">
                      초안을 수정하고 원본과 대조한 후 확정할 수 있어요.
                    </Empty>
                  )
                }
              >
                {current ? (
                  <DocumentEditor
                    key={current.id}
                    initial={current}
                    server={serverActions}
                    onSave={(doc, expected) =>
                      save((prev) => {
                        assertDocumentUnchanged(
                          prev.documents.find((d) => d.id === doc.id),
                          expected,
                        );
                        if (
                          doc.status === "confirmed" &&
                          compareEvidence(doc, prev.documents, prev.observations).linked.some(
                            (r) => r.state !== "일치",
                          )
                        )
                          throw new Error(
                            "원본이 변경되었거나 없어졌어요. 최신 기록으로 초안을 다시 생성해주세요.",
                          );
                        return {
                          ...prev,
                          documents: invalidateDependents(
                            prev.documents.map((d) => (d.id === doc.id ? doc : d)),
                            doc.id,
                          ),
                        };
                      })
                    }
                  />
                ) : null}
              </WorkspaceViewState>
            </div>
          </WorkspaceViewState>
        </>
      )}
    </WorkspacePage>
  );
}
