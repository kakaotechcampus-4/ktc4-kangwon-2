"use client";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import {
  DOCUMENT_KINDS,
  today,
  validPeriod,
  validDate,
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
  reconfirmDocument,
  type ReconfirmInput,
  type SourceResolution,
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
import { listDayRoutines, type RoutineLine } from "@/lib/api/routines";
import { listAnnualPlans } from "@/lib/api/plans";
import type { AnnualPlanSummary } from "@/lib/api/types";
import DailyLogSources from "./DailyLogSources";
import { classServerId } from "@/lib/api/onboarding";
import { useClientState } from "@/lib/hooks/use-client-state";
import { routinesPath, routinesQuery, routinesScope } from "@/lib/workspace/routines-route";
import { chosenClassFor, loadClassSettings } from "@/lib/onboarding/settings";
import DocumentEditor from "./DocumentEditor";
import DocumentArchivePreview from "./DocumentArchivePreview";
import DocumentArchiveView, { type ArchiveDoc } from "./DocumentArchiveView";
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
/**
 * 근거 후보 하나 (§11). 주간 보육일지는 확정된 일일 보육일지,
 * 일일 보육일지는 일과 기록, 나머지는 관찰 기록이다.
 */
type Candidate = { id: string; date: string; label: string };
/** 렌더마다 새 배열이 생기면 useMemo 가 매번 다시 돈다. */
const NO_ROUTINES: RoutineLine[] = [];

function messageFor(error: unknown) {
  if (isUnauthenticated(error)) return "로그인이 필요해요. 다시 로그인한 뒤 이용해주세요.";
  return error instanceof Error ? error.message : "요청을 처리하지 못했어요.";
}

export default function DocumentsPage() {
  const { data, error, save } = useWorkspace();
  const [entry] = useClientState(
    () =>
      typeof window === "undefined"
        ? { date: "", classId: null, daily: false, assessment: false }
        : {
            ...routinesScope(window.location.search),
            daily: new URLSearchParams(window.location.search).get("kind") === "dailyLog",
            // 평가 준비 4-2 「영유아 평가 작성하기」가 여는 길.
            assessment: new URLSearchParams(window.location.search).get("kind") === "assessment",
          },
    { date: "", classId: null as number | null, daily: false, assessment: false },
  );
  const [mode, setMode] = useState<"library" | "create">("library");
  const [editingId, setEditingId] = useState("");
  const [kind, setKind] = useState<DocumentKind>("observation");
  const [pickedClass, setClassId] = useState<string | null>(null);
  const [primaryClass] = useClientState(() => chosenClassFor(loadClassSettings())?.id ?? "", "");
  const [childId, setChildId] = useState("");
  const [start, setStart] = useState(today);
  const [end, setEnd] = useState(today);
  const [selected, setSelected] = useState<string[]>([]);
  // 주간 보육일지의 근거를 어디서 받나 (§11 `source_kind`).
  // 일일 보육일지를 쓰지 않는 원은 그 주 일과 기록을 바로 근거로 쓴다.
  const [weeklyFrom, setWeeklyFrom] = useState<"dailyLog" | "routine">("dailyLog");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [invalid, setInvalid] = useState<string[]>([]);
  const classes = useClasses(setMessage);
  // 서버에만 있던 반은 useClasses가 늦게 들여온다. 먼저 주 반을 고르거나 미리 포기를 확정하지 않는다.
  const requestedClass =
    entry.classId !== null
      ? (classes.find((c) => classServerId(c.id) === entry.classId)?.id ?? "")
      : primaryClass;
  const classId = pickedClass ?? requestedClass;
  const [serverDocs, setServerDocs] = useState<DocumentSummary[]>([]);
  const [listStatus, setListStatus] = useState<ViewStatus>("loading");
  const [listError, setListError] = useState("");
  const [records, setRecords] = useState<ServerObservation[]>([]);
  // 연간계획안은 일지와 다른 API 다 (FR-701). 따로 부르고 따로 실패한다 — 한쪽이 죽어도
  // 다른 쪽은 그린다. null 이면 아직 불러오는 중.
  const [plans, setPlans] = useState<{ items: AnnualPlanSummary[]; error: string } | null>(null);
  const latestPlans = useRef(0);
  const [dailyPrefilled, setDailyPrefilled] = useState(false);
  if (entry.daily && !dailyPrefilled) {
    setDailyPrefilled(true);
    setMode("create");
    setKind("dailyLog");
    setChildId("");
    setStart(entry.date || today());
    setEnd(entry.date || today());
    setSelected([]);
  }
  const [assessmentPrefilled, setAssessmentPrefilled] = useState(false);
  if (entry.assessment && !assessmentPrefilled) {
    setAssessmentPrefilled(true);
    setMode("create");
    setKind("assessment");
  }
  // 일일 보육일지의 근거(일과 기록). 반 · 날짜를 key 로 둬서 「불러오는 중」을 따로 저장하지 않는다.
  const [routineData, setRoutineData] = useState<{
    key: string;
    items: RoutineLine[];
    error: string;
  } | null>(null);
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
        reconfirm: reconfirmDocument,
        remove: deleteDocument,
      },
      messageFor,
    ),
  );
  const chosen = useSyncExternalStore(selection.subscribe, selection.get, selection.get);
  const active = chosen.active;

  useEffect(() => {
    const mine = ++latestList.current;
    Promise.all([listDocuments(), listRecords(classId)])
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
  }, [selection, classId]);
  async function reloadList() {
    const mine = ++latestList.current;
    try {
      const [documents, observations] = await Promise.all([listDocuments(), listRecords(classId)]);
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

  // 마운트할 때 한 번. 일지를 고치거나 만들어도 계획안 목록은 바뀌지 않는다.
  useEffect(() => {
    const mine = ++latestPlans.current;
    listAnnualPlans()
      .then(({ items }) => {
        if (mine === latestPlans.current) setPlans({ items, error: "" });
      })
      .catch((e) => {
        if (mine === latestPlans.current) setPlans({ items: [], error: messageFor(e) });
      });
    return () => {
      latestPlans.current += 1;
    };
  }, []);
  async function reloadPlans() {
    const mine = ++latestPlans.current;
    setPlans(null);
    try {
      const { items } = await listAnnualPlans();
      if (mine === latestPlans.current) setPlans({ items, error: "" });
    } catch (e) {
      if (mine === latestPlans.current) setPlans({ items: [], error: messageFor(e) });
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

  // 일과 기록을 근거로 쓰는 두 경우다 — 일일 보육일지, 그리고 그렇게 고른 주간 보육일지.
  const fromRoutines = kind === "dailyLog" || (kind === "weeklyLog" && weeklyFrom === "routine");
  const routineKey =
    mode === "create" && fromRoutines && classId && validDate(start) && validDate(end)
      ? `${classId}|${start}|${kind === "dailyLog" ? start : end}`
      : "";
  useEffect(() => {
    if (!routineKey) return;
    let stale = false;
    const [cls, from, to] = routineKey.split("|");
    listDayRoutines(cls, from, to)
      .then((items) => !stale && setRoutineData({ key: routineKey, items, error: "" }))
      .catch((e) => !stale && setRoutineData({ key: routineKey, items: [], error: messageFor(e) }));
    return () => {
      stale = true;
    };
  }, [routineKey]);
  const routines = routineData?.key === routineKey ? routineData.items : NO_ROUTINES;
  const routineStatus: ViewStatus = !routineKey
    ? "ready"
    : routineData?.key !== routineKey
      ? "loading"
      : routineData.error
        ? "error"
        : "ready";
  const candidates: Candidate[] = useMemo(
    () =>
      fromRoutines
        ? routines
            .filter((r) => r.execution)
            .map((r) => ({ id: r.id, date: r.date, label: r.execution }))
        : kind === "weeklyLog"
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
    [fromRoutines, kind, routines, serverDocs, records, classId, childId, start, end],
  );
  // 근거 목록이 어느 요청에서 오나. 일과 기록이면 일과 조회, 나머지는 문서 · 관찰 목록이다.
  const sourceStatus = fromRoutines ? routineStatus : listStatus;
  const sourceError = fromRoutines ? (routineData?.error ?? "") : listError;
  // 일일 보육일지는 고른 순서가 사실의 순서다 (S-J2). 나머지는 목록 순서 그대로 보낸다.
  const sources =
    kind === "dailyLog"
      ? selected.flatMap((id) => candidates.filter((s) => s.id === id))
      : candidates.filter((s) => selected.includes(s.id));

  // 새로 등록하는 증빙은 서버로 간다 (§11 「증빙 등록」) — 아래 서버 목록에 섞여 온다.
  // 이 줄은 그 길이 열리기 전에 브라우저에 쌓인 증빙을 계속 보여 주기 위한 것이다.
  // 브라우저에 남은 옛 계획안은 읽지 않는다. 계획안은 이제 서버 목록에서 온다.
  const localDocs = data.documents.filter((d) => d.origin === "import");
  // 목록에는 sections · sources 가 없다 — 제목 · 종류 · 날짜 · 상태만 그린다 (§11).
  const entries = [
    ...serverDocs.map((d) => ({
      id: d.id,
      source: "document" as const,
      serverId: d.serverId,
      title: d.title,
      className: d.className,
      childName: d.childName,
      kind: d.kind,
      status: d.status,
      createdAt: d.createdAt,
      stale: d.stale,
    })),
    ...localDocs.map((d) => ({
      id: d.id,
      source: "document" as const,
      serverId: null,
      title: d.title,
      className: d.className,
      childName: d.childName,
      kind: d.kind,
      status: d.status,
      createdAt: d.createdAt,
      stale: false,
    })),
    ...(plans?.items ?? []).map((p) => ({
      id: `annual:${p.id}`,
      source: "plan" as const,
      serverId: p.id,
      format: p.format,
      title: `${p.school_year}학년도 ${DOCUMENT_KINDS.annual}`,
      // 목록에는 반 이름이 없다. 모르는 반이면 비워 둔다 — 지어내지 않는다.
      className: classes.find((c) => classServerId(c.id) === p.class_id)?.className ?? "",
      childName: "",
      kind: "annual" as const,
      status: (p.status === "CONFIRMED" ? "confirmed" : "draft") as SavedDocument["status"],
      createdAt: p.created_at,
      stale: false,
    })),
  ];

  // 보관함 탐색(반 → 종류 → 기간)이 쓰는 목록. 계획안은 각자 API 가 따로 준다.
  const archiveDocs: ArchiveDoc[] = [
    ...serverDocs.map((d) => ({
      id: d.id,
      kind: d.kind,
      title: d.title,
      classId: d.classId,
      childId: d.childId,
      start: d.start,
      status: d.status,
      createdAt: d.createdAt,
      updatedAt: d.updatedAt,
    })),
    ...localDocs.map((d) => ({
      id: d.id,
      kind: d.kind,
      title: d.title,
      classId: d.classId,
      childId: d.childId,
      start: d.start,
      status: d.status,
      createdAt: d.createdAt,
      updatedAt: d.updatedAt,
    })),
  ];

  /** 보관함에서 「작성」을 누르면 **기존 생성 화면**으로 넘어간다 — 가짜 생성을 만들지 않는다. */
  function startCreate(next: RecordKind, options: { date: string; childId?: string }) {
    selection.leaveCreation();
    setMode("create");
    setKind(next);
    setChildId(options.childId ?? "");
    setStart(options.date);
    setEnd(options.date);
    setSelected([]);
    setInvalid([]);
    setMessage("");
  }

  const activeServerId = documentServerId(active);
  const localCurrent = data.documents.find((d) => d.id === active);
  // 서버 문서는 `active` 와 같은 문서일 때만 화면에 올린다.
  const serverCurrent = chosen.detail?.id === active ? chosen.detail : null;
  const current = activeServerId === null ? localCurrent : serverCurrent;
  // 첫 목록이 비어 있어도 조회가 끝나기 전에는 로딩임을 알린다.
  const journalsPending = listStatus === "loading";

  /** 고친 칸만 지운다. 서버가 함께 짚은 다른 칸은 아직 그대로다. */
  const clearInvalid = (name: string) =>
    setInvalid((prev) => (prev.includes(name) ? prev.filter((f) => f !== name) : prev));

  /** 일일 보육일지는 반 단위 · 하루짜리다 — 아이를 비우고 종료일을 시작일에 맞춘다. */
  function changeKind(next: DocumentKind) {
    setKind(next);
    setSelected([]);
    clearInvalid("kind");
    if (next === "dailyLog") {
      setChildId("");
      setEnd(start);
    }
  }

  function changeStart(date: string) {
    setStart(date);
    if (kind === "dailyLog") setEnd(date);
    setSelected([]);
    clearInvalid("start");
  }

  function toggleSource(id: string, checked: boolean) {
    setSelected((prev) => (checked ? [...prev, id] : prev.filter((x) => x !== id)));
    clearInvalid("sources");
  }

  function open(id: string) {
    setEditingId("");
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
        ...(kind === "weeklyLog" ? { sourceKind: weeklyFrom } : {}),
      });
      if (creation.adopt(created)) {
        setEditingId(created.id);
        // 목록 재조회가 끝나기 전에도 방금 만든 문서를 기존 편집기로 연다.
        setServerDocs((prev) => [
          { ...created, sourcesCount: created.sources.length },
          ...prev.filter((d) => d.id !== created.id),
        ]);
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

  // 못 만드는 이유. 버튼을 끄고 그 자리에서 말한다 — 경고가 페이지 맨 위에만 뜨면
  // 스크롤을 내린 교사에게는 「눌러도 아무 일이 없다」로 보인다.
  const blocked =
    listStatus !== "ready"
      ? ""
      : !classroom
        ? "반을 먼저 골라주세요."
        : (kind === "observation" || kind === "assessment") && !child
          ? "이 문서는 아동을 한 명 골라야 만들 수 있어요."
          : kind === "dailyLog" && start !== end
            ? "일일 보육일지는 시작일과 종료일이 같아야 해요."
            : !validPeriod(start, end)
              ? "기간을 확인해주세요."
              : !sources.length
                ? "근거로 쓸 기록을 하나 이상 골라주세요."
                : "";

  // 일과 기록 화면(S-J1)의 주소 — docs/screen-spec.md 「들어오는 길」. 날짜 · 반이 그대로 넘어간다.
  const routineHref =
    pickedClass === null && entry.daily && entry.classId !== null
      ? `/routines${routinesQuery(entry.classId, start)}`
      : routinesPath(classId, start);

  const serverActions = serverCurrent
    ? {
        stale: serverCurrent.stale,
        pending: chosen.pending !== "",
        reload: selection.reload,
        reconfirm: async (input: ReconfirmInput) => {
          const next = await selection.reconfirm(input);
          void reloadList();
          return next;
        },
        save: async (
          sections: SavedDocument["sections"],
          reviewNote: string,
          classNote?: string,
        ) => {
          const saved = await selection.save(sections, reviewNote, classNote);
          void reloadList();
          return saved;
        },
        saveAndConfirm: async (
          sections: SavedDocument["sections"],
          reviewNote: string,
          classNote?: string,
        ) => {
          const confirmed = await selection.saveAndConfirm(sections, reviewNote, classNote);
          void reloadList();
          return confirmed;
        },
        unconfirm: async () => {
          const next = await selection.unconfirm();
          void reloadList();
          return next;
        },
        refresh: async (resolutions?: SourceResolution[]) => {
          const next = await selection.refresh(resolutions);
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

  const detailPane = (
    <WorkspaceViewState
      status={chosen.status}
      error={chosen.error ? `문서를 불러오지 못했어요. ${chosen.error}` : ""}
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
  );

  /** 제목 · 설명 · 생성 액션. 보관함에서는 **반 사이드바 오른쪽 본문 안에만** 그린다. */
  /** 생성 화면에서 보관함으로 돌아오는 단추. **보관함 쪽에는 두지 않는다.** */
  const modeButton = (
    <button
      className={ws.primary}
      onClick={() => {
        selection.leaveCreation();
        setMode("library");
        setMessage("");
      }}
    >
      보관함 보기
    </button>
  );
  const notices = (
    <>
      <Message error>{error}</Message>
      <Message>{message}</Message>
    </>
  );
  /** 보관함 모드는 `WorkspacePage` 를 쓰지 않는다(전폭 3단이라) — 제목을 직접 그린다. */
  const head = (
    <>
      <div className={ws.pageHead}>
        <div>
          <h1>문서 보관함</h1>
          <p>계획안과 일지를 한곳에서 확인하고 관리하세요.</p>
        </div>
        {/* 보관함은 찾아보는 곳이다. 만들기는 종류별 화면 안의 작성 단추로만 한다. */}
      </div>
      {notices}
    </>
  );

  if (mode === "library")
    return (
      <DocumentArchiveView
        header={
          <>
            {head}
            {listStatus === "error" && (
              <div>
                <Message error>{listError}</Message>
                <button className={ws.secondary} disabled={busy} onClick={reloadList}>
                  다시 시도
                </button>
              </div>
            )}
            {plans?.error && (
              <div>
                <Message error>계획안 목록을 불러오지 못했어요. {plans.error}</Message>
                <button className={ws.secondary} onClick={reloadPlans}>
                  계획안 다시 시도
                </button>
              </div>
            )}
            {journalsPending && (
              <Message>
                {entries.length ? "일지를 불러오고 있어요." : "문서 목록을 불러오고 있어요."}
              </Message>
            )}
          </>
        }
        classes={classes}
        classId={classId}
        onPickClass={(id) => {
          setClassId(id);
          setChildId("");
          setSelected([]);
          setMessage("");
          selection.select("", null);
        }}
        documents={archiveDocs}
        annual={plans?.items ?? null}
        activeId={active}
        editingId={editingId}
        onBackToPreview={() => setEditingId("")}
        preview={
          <DocumentArchivePreview
            document={current?.classId === classId ? current : null}
            status={chosen.status}
            error={chosen.error}
            onRetry={() => selection.select(active, activeServerId)}
            onEdit={() => setEditingId(active)}
          />
        }
        onOpen={open}
        onCloseDetail={() => selection.select("", null)}
        onCreate={startCreate}
        detail={
          <>
            {detailPane}
            {chosen.status === "error" && (
              <button className={ws.secondary} onClick={() => open(active)}>
                문서 다시 불러오기
              </button>
            )}
          </>
        }
      />
    );

  return (
    <WorkspacePage
      title="문서 보관함"
      description="계획안과 일지를 한곳에서 확인하고 관리하세요."
      action={modeButton}
    >
      {notices}
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
                onChange={(e) => changeKind(e.target.value as DocumentKind)}
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
              {kind !== "dailyLog" && (
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
              )}
            </div>
            {kind === "weeklyLog" && (
              <div className={ws.row}>
                <label className={ws.field}>
                  근거로 쓸 기록
                  <select
                    name="sourceKind"
                    disabled={busy}
                    value={weeklyFrom}
                    onChange={(e) => {
                      setWeeklyFrom(e.target.value as "dailyLog" | "routine");
                      setSelected([]);
                      clearInvalid("sources");
                    }}
                  >
                    <option value="dailyLog">확정한 일일 보육일지</option>
                    <option value="routine">일과 기록</option>
                  </select>
                </label>
              </div>
            )}
            <div className={ws.row}>
              <label className={ws.field}>
                {kind === "dailyLog" ? "날짜" : "시작일"}
                <input
                  name="start"
                  disabled={busy}
                  type="date"
                  value={start}
                  {...fieldErrorProps("start", invalid)}
                  onChange={(e) => changeStart(e.target.value)}
                />
                <FieldError name="start" invalid={invalid} />
              </label>
              {kind !== "dailyLog" && (
                <label className={ws.field}>
                  종료일
                  <input
                    name="end"
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
              )}
            </div>
            <p className={ws.hint}>
              {kind === "dailyLog"
                ? "일일 보육일지는 반 전체 문서라 아동은 선택하지 않아요. 하루에 한 장씩 만들어요."
                : kind === "weeklyLog"
                  ? weeklyFrom === "routine"
                    ? "일일 보육일지를 쓰지 않는 원이면 그 주 일과 기록을 바로 근거로 써요. 날짜별 해석·지원 칸은 비워서 내보내고, 주간 총평 하나만 적어요."
                    : "주간 보육일지는 검토가 완료된 일일 보육일지만 근거로 사용해요."
                  : kind === "assessment"
                    ? "한 아동의 누적 관찰을 선택해주세요. 기록에 드러난 변화만 다루며 발달을 진단하지 않아요."
                    : "관찰일지는 아동을 선택하고, 일일 보육일지는 시작·종료일을 같은 날짜로 지정해주세요."}
            </p>
            <button
              className={ws.primary}
              disabled={busy || !!blocked || listStatus !== "ready" || sourceStatus !== "ready"}
              onClick={generate}
            >
              {busy ? "초안 작성 중…" : "초안 만들기"}
            </button>
            {blocked && <p className={ws.hint}>{blocked}</p>}
            {fromRoutines && routineHref && (
              <Link className={ws.link} href={routineHref}>
                새 일과 기록 입력 →
              </Link>
            )}
            {!fromRoutines && (
              <Link className={ws.link} href="/records">
                새 관찰 기록 입력 →
              </Link>
            )}
          </div>
        </section>
        {kind === "dailyLog" && (
          <DailyLogSources
            status={routineStatus}
            error={routineData?.error ?? ""}
            routines={routines}
            selected={selected}
            busy={busy}
            writeHref={routineHref}
            onToggle={toggleSource}
            onSelectAll={() =>
              setSelected(sources.length === candidates.length ? [] : candidates.map((s) => s.id))
            }
          />
        )}
        {kind !== "dailyLog" && (
          <section className={ws.card}>
            <div className={ws.between}>
              <h2>문서에 사용할 근거</h2>
              <span className={ws.badge}>{sources.length}건 선택</span>
            </div>
            <p className={ws.hint}>선택한 반·아동·기간의 기록만 표시됩니다.</p>
            <WorkspaceViewState
              status={sourceStatus}
              error={sourceError}
              loading="근거 기록을 불러오고 있어요."
              empty={
                !candidates.length && (
                  <Empty title="조건에 맞는 근거가 없어요">
                    날짜를 변경하거나{" "}
                    {fromRoutines
                      ? "일과 기록을 먼저 입력해주세요."
                      : kind === "weeklyLog"
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
        )}
      </div>
    </WorkspacePage>
  );
}
