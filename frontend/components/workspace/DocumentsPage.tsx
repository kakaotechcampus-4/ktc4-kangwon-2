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
import {
  isAlreadyExists,
  isApiNotFound,
  isClassAccessRequired,
  isClassReadOnly,
  isStaleWrite,
  isUnauthenticated,
  invalidFields,
} from "@/lib/api/client";
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
import type { AnnualPlanSummary, ApiClass, ClassAccess } from "@/lib/api/types";
import { getMe } from "@/lib/api/auth";
import {
  decideAccessRequest,
  getArchiveSummary,
  getClasses,
  getReceivedRequests,
  requestClassAccess,
} from "@/lib/api/classes";
import { getChildren } from "@/lib/api/children";
import type { ChildEntry, ClassroomEntry } from "@/lib/onboarding/types";
import DailyLogSources from "./DailyLogSources";
import { CHILD_PREFIX, CLASS_PREFIX, classServerId } from "@/lib/api/onboarding";
import { useClientState } from "@/lib/hooks/use-client-state";
import { routinesPath, routinesQuery, routinesScope } from "@/lib/workspace/routines-route";
import { chosenClassFor, loadClassSettings } from "@/lib/onboarding/settings";
import DocumentEditor from "./DocumentEditor";
import DocumentArchivePreview from "./DocumentArchivePreview";
import DocumentArchiveView, { type ArchiveDoc } from "./DocumentArchiveView";
import {
  ACCESS_REQUIRED_MESSAGE,
  LockedClassPanel,
  READ_ONLY_MESSAGE,
  ReceivedRequestsPanel,
  isLocked,
  type ReceivedState,
  type SummaryState,
} from "./DocumentArchiveAccess";
import { createSelection } from "./document-selection";
import { Empty, Message, useClasses, ws } from "./WorkspaceUI";
import { Icon } from "@/components/app/icons";
import { ArchiveNoteArt } from "./DocumentArchiveArt";
import { FlowerMeadow } from "./ChildTrackingArt";
import creation from "./DocumentCreation.module.css";
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
  // 같은 원 다른 반의 권한 거절 (docs/api-spec.md §2-2). 서버 문구 대신 화면 말로 바꾼다.
  if (isClassAccessRequired(error)) return ACCESS_REQUIRED_MESSAGE;
  if (isClassReadOnly(error)) return READ_ONLY_MESSAGE;
  return error instanceof Error ? error.message : "요청을 처리하지 못했어요.";
}

const DECIDED = {
  APPROVED: "열람을 승인했어요. 이제 그 선생님이 이 반 문서를 볼 수 있어요.",
  REJECTED: "요청을 거절했어요.",
  REVOKED: "열람 승인을 취소했어요. 그 선생님은 더 이상 이 반 문서를 볼 수 없어요.",
} as const;

/** 같은 원의 반 전부와 각 반의 `my_access` (§2). 원이 없는 계정이면 null. */
async function fetchCenterClasses(): Promise<ApiClass[] | null> {
  const me = await getMe();
  if (me.center_id === null) return null;
  return (await getClasses(me.center_id)).items;
}

/**
 * 보관함 목록. `class_id` 없는 문서 목록은 OWNER · OPEN 반 것만 준다(§2-2) — 승인된 남의 반을
 * 보고 있으면 그 반 목록을 `class_id` 로 따로 받아 합친다. 승인 전 반은 기록을 부르지 않는다.
 */
async function fetchLists(
  classId: string,
  approvedServerId: number | null,
  locked: boolean,
): Promise<[DocumentSummary[], ServerObservation[]]> {
  const [own, approved, observations] = await Promise.all([
    listDocuments(),
    approvedServerId === null ? [] : listDocuments({ class_id: approvedServerId }),
    locked ? [] : listRecords(classId),
  ]);
  return [[...own, ...approved.filter((d) => !own.some((o) => o.id === d.id))], observations];
}

/** 받은 요청 중 지금 보고 있는 내 반 것만. */
function ownRequests(state: ReceivedState, serverClassId: number | null): ReceivedState {
  if (state.status !== "ready") return state;
  return { status: "ready", items: state.items.filter((r) => r.class_id === serverClassId) };
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
  /**
   * **보관함만** 같은 원의 모든 반을 본다 (§2 의 반 목록은 원 단위다).
   * 다른 화면은 그대로 `useClasses` — 담당 반만 쓴다.
   */
  const [centerClasses, setCenterClasses] = useState<ApiClass[]>([]);
  useEffect(() => {
    let live = true;
    fetchCenterClasses()
      // 못 받아도 담당 반 목록은 이미 그려져 있다. 보관함이 좁아질 뿐이다.
      .then((items) => live && items && setCenterClasses(items))
      .catch(() => {});
    return () => {
      live = false;
    };
  }, []);
  /**
   * 반 목록을 다시 받아 `my_access` 를 최신으로 맞춘다. 요청 · 승인 · 취소는 다른 계정이
   * 바꾸므로, 반을 고를 때와 권한 거절(403 · 409 · 404)을 받았을 때 다시 묻는다.
   */
  async function refreshAccess() {
    const items = await fetchCenterClasses().catch(() => null);
    if (items) setCenterClasses(items);
  }
  // 반마다 서버가 준 열람 상태 (§2). 칸이 없는 옛 서버면 비어 있고, 그때는 지금처럼 다 연다.
  const accessByServerId = useMemo(
    () =>
      new Map(
        centerClasses.flatMap((c) =>
          c.my_access ? ([[c.id, c.my_access]] as [number, ClassAccess][]) : [],
        ),
      ),
    [centerClasses],
  );
  const classServer = classId ? classServerId(classId) : null;
  const classAccess = classServer === null ? undefined : accessByServerId.get(classServer);
  // 승인 전 반이면 실제 자료(문서 · 기록 · 명단)를 부르지 않는다 — 403 CLASS_ACCESS_REQUIRED 다.
  const lockedClass = isLocked(classAccess);
  // 승인된 남의 반은 class_id 를 붙여야 목록에 나온다 (§2-2 「반 단위 API 공통 규칙」).
  const approvedServerId = classAccess === "APPROVED" ? classServer : null;
  // 고른 반이 담당 반이 아니면 아이 명단이 로컬에 없다. 관찰일지는 아이를 골라야 열린다.
  // 읽을 수 있는 반(OWNER · OPEN · APPROVED)만 명단을 부른다.
  const guestClassId =
    classId && !lockedClass && !classes.some((c) => c.id === classId) ? classId : "";
  const [roster, setRoster] = useState<{ classId: string; children: ChildEntry[] }>({
    classId: "",
    children: [],
  });
  useEffect(() => {
    const serverId = guestClassId ? classServerId(guestClassId) : null;
    if (serverId === null) return;
    let live = true;
    getChildren(serverId)
      .then(({ items }) => {
        if (!live) return;
        setRoster({
          classId: guestClassId,
          children: items.map((kid) => ({
            // 기록 쪽(documents.ts · observations.ts)이 연결 없는 서버 id 를 푸는 규칙과 같다.
            id: CHILD_PREFIX + kid.id,
            name: kid.name,
            code: kid.code,
          })),
        });
      })
      .catch(() => live && setMessage("이 반의 아동 명단을 불러오지 못했어요."));
    return () => {
      live = false;
    };
  }, [guestClassId]);
  /**
   * 보관함에 그릴 반 목록(같은 원 전부)과, 반마다의 열람 상태 · **열람만 되는** 반.
   *
   * 읽기는 OWNER · OPEN · APPROVED, 쓰기는 OWNER · OPEN 이다 (ADR-059 · §2-2).
   * APPROVED 반은 서버가 쓰기를 403 CLASS_READ_ONLY 로 막고, 화면도 작성·수정 단추를 감춘다.
   * `my_access` 를 안 주는 옛 서버에서는 아무 반도 잠기지 않아 예전과 똑같이 동작한다.
   */
  const archive = useMemo(() => {
    const known = new Set(classes.map((c) => classServerId(c.id)));
    const guests = centerClasses
      .filter((item) => !known.has(item.id))
      .map<ClassroomEntry>((item) => {
        const id = CLASS_PREFIX + item.id;
        return {
          id,
          className: item.name,
          ageGroup: "",
          // 서버는 연령을 범위로만 들고 있다 (lib/api/age-adapter.ts).
          selectedAges: [
            ...([3, 4, 5] as const).filter((a) => a >= item.age_min && a <= item.age_max),
          ],
          currentChildCount: item.child_count ?? "",
          teacherName: item.teacher_name,
          guardianConsent: item.consent_confirmed_at !== null,
          childrenSkipped: false,
          children: roster.classId === id ? roster.children : [],
        };
      });
    const list = [...classes, ...guests];
    const access = new Map(
      list.flatMap((c) => {
        const a = accessByServerId.get(classServerId(c.id) ?? -1);
        return a ? ([[c.id, a]] as [string, ClassAccess][]) : [];
      }),
    );
    return {
      list,
      access,
      readOnly: new Set(list.filter((c) => access.get(c.id) === "APPROVED").map((c) => c.id)),
    };
  }, [classes, centerClasses, roster, accessByServerId]);
  const readOnlyClass = archive.readOnly.has(classId);
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
    fetchLists(classId, approvedServerId, lockedClass)
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
        // 보는 사이 승인이 취소됐다 — 반 상태를 다시 받아 요청 화면으로 돌린다.
        if (isClassAccessRequired(e)) void refreshAccess();
      });
    return () => {
      latestList.current += 1;
      selection.leaveCreation();
    };
  }, [selection, classId, approvedServerId, lockedClass]);
  async function reloadList() {
    const mine = ++latestList.current;
    try {
      const [documents, observations] = await fetchLists(classId, approvedServerId, lockedClass);
      if (mine !== latestList.current) return;
      setServerDocs(documents);
      setRecords(observations);
      setListError("");
      setListStatus("ready");
    } catch (e) {
      if (mine !== latestList.current) return;
      setListError(messageFor(e));
      setListStatus("error");
      if (isClassAccessRequired(e)) void refreshAccess();
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
  // class_id 없는 연간 목록에는 승인된 남의 반이 없다(§2-2). 그 반을 볼 때만 따로 부른다.
  const [approvedAnnual, setApprovedAnnual] = useState<{
    classId: number;
    items: AnnualPlanSummary[];
  } | null>(null);
  useEffect(() => {
    if (approvedServerId === null) return;
    let live = true;
    listAnnualPlans(approvedServerId)
      .then(({ items }) => live && setApprovedAnnual({ classId: approvedServerId, items }))
      .catch((e) => {
        if (!live) return;
        setApprovedAnnual({ classId: approvedServerId, items: [] });
        setMessage(`연간계획안을 불러오지 못했어요. ${messageFor(e)}`);
        if (isClassAccessRequired(e)) void refreshAccess();
      });
    return () => {
      live = false;
    };
  }, [approvedServerId]);
  const annualItems = useMemo(() => {
    const own = plans?.items ?? [];
    if (approvedAnnual === null || approvedAnnual.classId !== approvedServerId) return own;
    return [...own, ...approvedAnnual.items.filter((p) => !own.some((o) => o.id === p.id))];
  }, [plans, approvedAnnual, approvedServerId]);

  // 승인 전 반의 요약 (§2-2 「요약」). 같은 원이면 열람 상태와 관계없이 받는다.
  const lockedServerId = lockedClass ? classServer : null;
  const [summary, setSummary] = useState<{ classId: number; state: SummaryState } | null>(null);
  const [summaryRetry, setSummaryRetry] = useState(0);
  useEffect(() => {
    if (lockedServerId === null) return;
    let live = true;
    getArchiveSummary(lockedServerId)
      .then(
        ({ items }) =>
          live && setSummary({ classId: lockedServerId, state: { status: "ready", items } }),
      )
      .catch((e) => {
        if (!live) return;
        setSummary({ classId: lockedServerId, state: { status: "error", error: messageFor(e) } });
        // 404 는 다른 원 · 없는 반이다. 반 목록을 다시 받아 그 반을 지운다 — 정보를 더 보이지 않는다.
        if (isApiNotFound(e)) void refreshAccess();
      });
    return () => {
      live = false;
    };
  }, [lockedServerId, summaryRetry]);
  const summaryState: SummaryState =
    summary?.classId === lockedServerId ? summary.state : { status: "loading" };

  // 열람 요청 (§2-2 「요청」). 누르는 동안 단추를 끈다 — 같은 요청이 두 번 나가지 않게.
  const [requesting, setRequesting] = useState(false);
  // 단추가 꺼지는 것은 다음 렌더다. 그 사이 두 번째 클릭이 들어와도 요청은 하나만 나가게 ref 로 막는다.
  const inFlight = useRef(false);
  const [accessMessage, setAccessMessage] = useState({ classId: "", text: "" });
  async function requestAccess() {
    if (inFlight.current || lockedServerId === null) return;
    inFlight.current = true;
    const target = lockedServerId;
    const forClass = classId;
    setRequesting(true);
    setAccessMessage({ classId: forClass, text: "" });
    try {
      const created = await requestClassAccess(target);
      setCenterClasses((prev) =>
        prev.map((c) => (c.id === target ? { ...c, my_access: created.status } : c)),
      );
      setAccessMessage({
        classId: forClass,
        text: "열람을 요청했어요. 담당 선생님이 승인하면 문서를 볼 수 있어요.",
      });
    } catch (e) {
      // 실패하면 지금 상태를 그대로 둔다. 409 · 404 는 서버 상태가 화면과 다르다는 뜻이라 다시 받는다.
      if (isAlreadyExists(e)) {
        await refreshAccess();
        setAccessMessage({
          classId: forClass,
          text: "이미 요청했거나 열람할 수 있는 반이에요. 최신 상태로 바꿨어요.",
        });
      } else if (isApiNotFound(e)) {
        await refreshAccess();
        setAccessMessage({ classId: forClass, text: "이 반을 찾을 수 없어요." });
      } else {
        setAccessMessage({ classId: forClass, text: `요청하지 못했어요. ${messageFor(e)}` });
      }
    } finally {
      inFlight.current = false;
      setRequesting(false);
    }
  }

  // 내 반에 온 요청 (§2-2 「받은 요청」). 메일 없이 화면 안 목록으로만 알린다.
  const [received, setReceived] = useState<ReceivedState>({ status: "loading" });
  const [receivedRetry, setReceivedRetry] = useState(0);
  useEffect(() => {
    let live = true;
    getReceivedRequests()
      .then(({ items }) => live && setReceived({ status: "ready", items }))
      .catch((e) => live && setReceived({ status: "error", error: messageFor(e) }));
    return () => {
      live = false;
    };
  }, [receivedRetry]);
  const [deciding, setDeciding] = useState<number | null>(null);
  const [decideMessage, setDecideMessage] = useState("");
  async function decide(id: number, next: "APPROVED" | "REJECTED" | "REVOKED") {
    if (inFlight.current) return;
    inFlight.current = true;
    setDeciding(id);
    setDecideMessage("");
    try {
      const updated = await decideAccessRequest(id, next);
      setReceived((prev) =>
        prev.status === "ready"
          ? { status: "ready", items: prev.items.map((r) => (r.id === id ? updated : r)) }
          : prev,
      );
      setDecideMessage(DECIDED[next]);
    } catch (e) {
      // 다른 화면이 먼저 처리했거나(409) 요청이 사라졌다(404). 목록을 다시 받는다.
      if (isStaleWrite(e) || isApiNotFound(e)) {
        setDecideMessage("다른 화면에서 먼저 처리된 요청이에요. 최신 상태를 불러왔어요.");
        setReceivedRetry((n) => n + 1);
      } else {
        setDecideMessage(`처리하지 못했어요. ${messageFor(e)}`);
      }
    } finally {
      inFlight.current = false;
      setDeciding(null);
    }
  }
  // 내 반(OWNER)마다 기다리는 요청 수 — 반 카드에 띄운다.
  const pendingRequests = useMemo(() => {
    const counts = new Map<string, number>();
    if (received.status !== "ready") return counts;
    for (const r of received.items) {
      if (r.status !== "PENDING") continue;
      const local = archive.list.find((c) => classServerId(c.id) === r.class_id);
      if (local) counts.set(local.id, (counts.get(local.id) ?? 0) + 1);
    }
    return counts;
  }, [received, archive.list]);

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
    ...annualItems.map((p) => ({
      id: `annual:${p.id}`,
      source: "plan" as const,
      serverId: p.id,
      format: p.format,
      title: `${p.school_year}학년도 ${DOCUMENT_KINDS.annual}`,
      // 목록에는 반 이름이 없다. 모르는 반이면 비워 둔다 — 지어내지 않는다.
      className: archive.list.find((c) => classServerId(c.id) === p.class_id)?.className ?? "",
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
    // 담임이 다른 반은 열람만 한다. 보관함이 단추를 감추지만 여기서도 막는다.
    if (readOnlyClass) return;
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
  const serverDetail = chosen.detail?.id === active ? chosen.detail : null;
  // 담임이 다른 반의 문서는 **열람만** 한다. 미리보기(current)는 그대로 두고, 고칠 수 있는
  // 문서(serverCurrent)에서만 뺀다 — 아래 serverActions 가 통째로 끊긴다. 서버도 403 이다.
  const serverCurrent = readOnlyClass ? null : serverDetail;
  const current = activeServerId === null ? localCurrent : serverDetail;
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
      readOnlyClass ||
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
          <p>계획안과 작성한 문서들이 차곡차곡 모여 있어요.</p>
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
        classes={archive.list}
        readOnlyClasses={archive.readOnly}
        classAccess={archive.access}
        pendingRequests={pendingRequests}
        renderLocked={(type) =>
          isLocked(classAccess) && (
            <LockedClassPanel
              className={archive.list.find((c) => c.id === classId)?.className ?? ""}
              access={classAccess}
              type={type}
              summary={summaryState}
              requesting={requesting}
              message={accessMessage.classId === classId ? accessMessage.text : ""}
              onRequest={requestAccess}
              onRetrySummary={() => setSummaryRetry((n) => n + 1)}
            />
          )
        }
        ownerPanel={
          classAccess === "OWNER" && (
            <ReceivedRequestsPanel
              className={archive.list.find((c) => c.id === classId)?.className ?? ""}
              state={ownRequests(received, classServer)}
              busyId={deciding}
              message={decideMessage}
              onDecide={decide}
              onRetry={() => setReceivedRetry((n) => n + 1)}
            />
          )
        }
        classId={classId}
        onPickClass={(id) => {
          setClassId(id);
          // 요청 · 승인은 다른 계정이 바꾼다. 반을 고를 때마다 상태를 다시 받는다.
          void refreshAccess();
          setChildId("");
          setSelected([]);
          setMessage("");
          // 편집 중이던 문서가 반을 바꿨다 돌아왔을 때 다시 열리지 않게 한다.
          setEditingId("");
          selection.select("", null);
        }}
        documents={archiveDocs}
        annual={plans ? annualItems : null}
        activeId={active}
        editingId={readOnlyClass ? "" : editingId}
        onBackToPreview={() => setEditingId("")}
        preview={
          <DocumentArchivePreview
            document={current?.classId === classId ? current : null}
            status={chosen.status}
            error={chosen.error}
            onRetry={() => selection.select(active, activeServerId)}
            onEdit={readOnlyClass ? undefined : () => setEditingId(active)}
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
    <main className={`${ws.page} ${creation.page}`}>
      <header className={`${ws.pageHead} ${creation.header}`}>
        <ArchiveNoteArt className={creation.headerCharacter} />
        <div className={creation.headerCopy}>
          <h1>문서 보관함</h1>
          <p>우리 반의 일과를 문서로 정리하고 안전하게 보관해요.</p>
        </div>
        {modeButton}
        <svg
          className={creation.headerLandscape}
          viewBox="0 0 600 160"
          aria-hidden="true"
          focusable="false"
        >
          <path
            d="M180 57q-9-16 8-22 3-21 23-19 18-2 23 18 21-2 22 14 0 12-15 12h-49q-9 0-12-3m185-7q-8-16 9-21 6-22 26-19 20-1 25 20 21-3 22 15 0 10-15 10h-55q-10 0-12-5"
            fill="#fffdfa"
          />
          <path
            d="M49 160q-4-24 24-24-2-28 27-29 20-26 43-2 27-9 35 17 30-1 32 38m99 0q-1-24 22-26 0-26 28-24 13-30 40-25 26-1 34 25 24-9 36 17 35-3 36 33"
            fill="#e4eacb"
          />
          <path
            d="m16 153-3-8m11 8 2-11m7 11 4-6"
            stroke="#accb85"
            strokeWidth="4"
            strokeLinecap="round"
          />
        </svg>
      </header>
      {notices}
      <div className={creation.grid}>
        <section className={`${ws.card} ${creation.card}`}>
          <div className={creation.cardHead}>
            <span className={creation.cardIcon}>
              <Icon name="record" />
            </span>
            <div>
              <h2>문서 작성 조건</h2>
              <p className={creation.cardDescription}>문서 종류, 담당 반, 날짜 등을 선택해요.</p>
            </div>
          </div>
          <div className={`${ws.form} ${creation.form}`}>
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
                  {classes
                    .filter((c) => !archive.readOnly.has(c.id))
                    .map((c) => (
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
                {/* 확정하지 않은 일일은 근거 목록에 아예 안 뜬다. 고르고 난 뒤 빈 목록을
                    보고서야 알게 되어 「왜 비었지」로 한 번 막혔다. 여기서 먼저 말해 준다. */}
                <p className={ws.hint}>
                  {weeklyFrom === "dailyLog"
                    ? "확정한 일일 보육일지만 근거가 돼요. 아직 확정한 게 없으면 일과 기록으로 바로 만들 수 있어요."
                    : "그 주의 일과 기록을 바로 근거로 씁니다. 일일 보육일지를 거치지 않아도 돼요."}
                </p>
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
                    : "시작일과 종료일은 같은 주로 골라주세요. 그 주에 확정한 일일 보육일지가 아래에 뜹니다."
                  : kind === "assessment"
                    ? "한 아동의 누적 관찰을 선택해주세요. 기록에 드러난 변화만 다루며 발달을 진단하지 않아요."
                    : "관찰일지는 아동을 선택하고, 일일 보육일지는 시작·종료일을 같은 날짜로 지정해주세요."}
            </p>
            <button
              className={`${ws.primary} ${creation.generate}`}
              disabled={busy || !!blocked || listStatus !== "ready" || sourceStatus !== "ready"}
              onClick={generate}
            >
              {busy ? "초안 작성 중…" : "초안 만들기"}
            </button>
            {blocked && <p className={ws.hint}>{blocked}</p>}
            {fromRoutines && routineHref && (
              <Link className={ws.link} href={routineHref}>
                새 일과 기록 열기 →
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
          <section className={`${ws.card} ${creation.card} ${creation.evidenceCard}`}>
            <div className={creation.cardHead}>
              <span className={creation.cardIcon}>
                <Icon name="doc" />
              </span>
              <div>
                <h2>문서에 사용할 근거</h2>
                <p className={creation.cardDescription}>선택한 반·아동·기간의 기록만 표시됩니다.</p>
              </div>
              <span className={`${ws.badge} ${creation.count}`}>{sources.length}건 선택</span>
            </div>
            <WorkspaceViewState
              status={sourceStatus}
              error={sourceError}
              loading="근거 기록을 불러오고 있어요."
              empty={
                !candidates.length && (
                  // 일일 보육일지 쪽(DailyLogSources)과 같은 빈 화면이다. 한 화면에서 종류만
                  // 바꿨는데 그림이 달라지면 다른 기능으로 읽힌다.
                  <div className={`${ws.empty} ${creation.empty}`}>
                    <div className={creation.emptyGarden} aria-hidden="true">
                      <FlowerMeadow className={creation.emptyFlowers} />
                      <ArchiveNoteArt tone="sage" className={creation.emptyCharacter} />
                    </div>
                    <h3>조건에 맞는 근거가 없어요</h3>
                    <p>
                      날짜를 변경하거나{" "}
                      {fromRoutines
                        ? "일과 기록을 먼저 입력해주세요."
                        : kind === "weeklyLog"
                          ? "일일 보육일지를 먼저 작성하고 확정해주세요."
                          : "관찰 기록을 먼저 입력해주세요."}
                    </p>
                  </div>
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
    </main>
  );
}
