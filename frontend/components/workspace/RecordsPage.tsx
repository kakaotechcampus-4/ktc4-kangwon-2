"use client";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { today, validDate } from "@/lib/workspace/model";
import { useObservationDomains } from "@/lib/hooks/use-observation-domains";
import { DOMAIN_LOOK } from "@/lib/workspace/domain-look";
import { isUnauthenticated, invalidFields } from "@/lib/api/client";
import {
  listRecords,
  addRecord,
  editRecord,
  removeRecord,
  suggestRecordDomain,
  missingInRecord,
  dayRoutines,
  type ReviewImpact,
} from "@/lib/api/records";
import {
  CONTEXT_MAX,
  PLACES,
  contextFor,
  isIndoorPlay,
  nowTime,
  pickedSlot,
  slotAt,
  type DaySlot,
} from "@/lib/workspace/record-context";
import { documentLocalId } from "@/lib/api/documents";
import type { ServerObservation } from "@/lib/api/observations";
import { useClientState } from "@/lib/hooks/use-client-state";
import { useUnsavedWarning } from "@/lib/hooks/use-unsaved-warning";
import { chosenClassFor, loadClassSettings } from "@/lib/onboarding/settings";
import { Posty } from "@/components/app/Posty";
import { Icon } from "@/components/app/icons";
import { ChildNote } from "@/components/app/ChildPicker";
import { markFor } from "@/lib/workspace/child-mark";
import { WorkspacePage, Empty, Message, useClasses, ws } from "./WorkspaceUI";
import {
  WorkspaceViewState,
  FieldError,
  fieldErrorProps,
  type ViewStatus,
} from "./WorkspaceViewState";

const ENTRY_NONE = { classId: "", childId: "" };

export type RecordsStatus = ViewStatus;

/** 적다가 이만큼 멈추면 AI 에게 영역을 묻는다. 치는 동안 매번 부르지 않는다. */
const SUGGEST_PAUSE_MS = 900;
/** 이보다 짧은 글로는 묻지 않는다 — 몇 글자로는 영역이 안 보인다. */
const SUGGEST_MIN = 6;

/** 저장 뒤 빠진 것 쪽지(ADR-082). 서버가 준 순서의 첫 하나만 띄운다. */
const GAP_TEXT: Record<string, string> = {
  상황: "어디서 무엇을 하던 중인지 안 보여요. 한 줄 더 쓸까요?",
  행동: "아이가 한 행동이나 말이 안 보여요. 한 줄 더 쓸까요?",
  반응: "아이 반응이 안 보여요. 한 줄 더 쓸까요?",
};

/** 서버가 짚는 칸 이름 → 화면 입력 (docs/api-spec.md §10 의 POST·PUT body). */
const FIELD_INPUT: Record<string, string> = {
  class_id: "classId",
  child_id: "childId",
  date: "date",
  domain: "domain",
  context: "context",
  fact: "fact",
};

function messageFor(error: unknown) {
  if (isUnauthenticated(error)) return "로그인이 필요해요. 다시 로그인한 뒤 이용해주세요.";
  return error instanceof Error ? error.message : "요청을 처리하지 못했어요.";
}

export default function RecordsPage() {
  const [records, setRecords] = useState<ServerObservation[]>([]);
  const [status, setStatus] = useState<RecordsStatus>("loading");
  const [listError, setListError] = useState("");
  const [pending, setPending] = useState(false);
  // 우리 반 홈의 「이 아이 기록 보기」가 반·아이를 주소로 넘긴다. 없으면 주 반을 연다.
  const [entry] = useClientState(() => {
    if (typeof window === "undefined") return { classId: "", childId: "" };
    const q = new URLSearchParams(window.location.search);
    return { classId: q.get("class") ?? "", childId: q.get("child") ?? "" };
  }, ENTRY_NONE);
  const [pickedClass, setClassId] = useState<string | null>(null);
  const [primaryClass] = useClientState(() => chosenClassFor(loadClassSettings())?.id ?? "", "");
  const classId = pickedClass ?? primaryClass;
  const [childId, setChildId] = useState("");
  /*
    목록을 거르는 아이와 **적는 칸이 고른 아이를 따로 둔다.**

    전에는 한 값이었다. 그래서 새 기록을 쓰려고 아동을 고르면 아래 목록이 조용히 그 아이
    것만 남았고, 위 숫자는 또 전체라 셋이 서로 다른 것을 가리켰다. 거는 것과 쓰는 것은
    다른 일이다.

    홈에서 「이 아이 기록 보기」로 올 때는 둘 다 채운다 — 보러 온 김에 그 아이 기록을
    이어 쓰는 길이 제일 짧다.
  */
  const [onlyChildId, setOnlyChild] = useState("");
  // entry 는 hydration 뒤에야 값이 온다. 그래서 초기값이 아니라 한 번만 도는 채움으로 넣는다.
  const [entryUsed, setEntryUsed] = useState(false);
  if ((entry.classId || entry.childId) && !entryUsed) {
    setEntryUsed(true);
    if (entry.classId) setClassId(entry.classId);
    if (entry.childId) {
      setChildId(entry.childId);
      setOnlyChild(entry.childId);
    }
  }
  const [date, setDate] = useState(today);
  // 원마다 축이 다르다 (observation-axis.ts). 고칠 때는 그 기록의 영역을 그대로 띄운다 —
  // 원이 축을 바꾸기 전에 쓴 기록이면 지금 목록에 없는 이름일 수 있다.
  const domains = useObservationDomains();
  // **고른 영역 하나만 둔다.** 칸에 띄운 값과 보내는 값이 달라지면 안 된다.
  // 기본값이 없다 — 첫 영역이 눌린 채 저장돼 블록 놀이가 신체 줄에 들어갔다(ADR-082).
  const [picked, setDomain] = useState("");
  const domain = picked;
  /** AI 가 제안한 영역과 그것을 물은 입력(반 · 사실 · 상황). 칩에 점선만 친다 — 고르는 것은 교사다. */
  const [suggested, setSuggested] = useState<{ key: string; domain: string | null } | null>(null);
  const asking = useRef(0);
  /** 방금 저장한 기록에서 빠진 것 하나 — 쪽지 한 줄로 띄운다. */
  const [gap, setGap] = useState<{ record: ServerObservation; part: string } | null>(null);
  /*
    상황 칸. `auto` 는 화면이 미리 눌러 둔 값이다 — 「오늘 기록 + 지금이 그 일과 시간 안」일 때만
    그 일과 이름이 들어간다. 교사가 손대지 않은 그 값은 적던 글로 치지 않는다.
  */
  const [contextBox, setContextBox] = useState({ text: "", auto: "" });
  const context = contextBox.text;
  const setContext = (text: string) => setContextBox({ text, auto: "" });
  /** 그날 일과 — 상황 칸 위 시간표. `key` 는 「반|날짜」다. 늦게 온 다른 날 일과를 그리지 않는다. */
  const [slots, setSlots] = useState<{ key: string; rows: DaySlot[] }>({ key: "", rows: [] });
  /** 아이 이름 칩을 펼쳤나. 아이를 고르면 접히고, 문장 속 이름을 누르면 다시 펼친다. */
  const [kidsOpen, setKidsOpen] = useState(false);
  const [fact, setFact] = useState("");
  const [editId, setEditId] = useState("");
  /** 「고치기」 전에 칸에 있던 것. 「그만두기」를 누르면 이대로 되돌린다. 적던 글은 묻고 버렸으므로 없다. */
  const [beforeEdit, setBeforeEdit] = useState<{
    classId: string | null;
    childId: string;
    date: string;
    domain: string;
    invalid: string[];
  } | null>(null);
  /** 적던 글이 있어 묻는 중인 일 — 고칠 기록이거나, 관찰일지로 나가기. */
  const [ask, setAsk] = useState<ServerObservation | null>(null);
  const askDialog = useRef<HTMLDialogElement>(null);
  /** 떠나려다 붙잡힌 링크 · 단추. 쪽지를 띄운 동안만 있다. */
  const [held, setHeld] = useState<HTMLElement | null>(null);
  const leaveNote = useRef<HTMLDialogElement>(null);
  /** 머리줄 「저장됨」. 다시 적기 시작하면 내린다. */
  const [savedMark, setSavedMark] = useState(false);
  const [message, setMessage] = useState("");
  /** 방금 고치거나 지운 기록을 쓴 확정 일지 — 「N건 다시 검토」 안내 (§10). */
  const [review, setReview] = useState<ReviewImpact | null>(null);
  const [invalid, setInvalid] = useState<string[]>([]);
  const [classError, setClassError] = useState("");
  const classes = useClasses(setClassError);
  const [search, setSearch] = useState("");
  /** 목록을 거르는 영역. 빈 값이면 다섯 영역 전부다. */
  const [area, setArea] = useState("");
  /** 목록을 거르는 날짜. 빈 값이면 모든 날이다. */
  const [day, setDay] = useState("");
  /*
    적는 칸은 펴 둔다.

    한동안 접어 뒀다. 적는 칸이 화면 왼쪽 절반을 늘 차지해서 기록을 보러 온 교사가
    목록을 찾아야 했기 때문이다. 접으니 이번에는 적으러 온 교사가 한 번 더 눌러야 했다.
    지금은 폼을 세 줄로 줄여 목록이 바로 아래 보이게 했다 — 접지 않고도 둘 다 보인다.
  */
  const classroom = classes.find((c) => c.id === classId);
  /** 적는 칸이 고른 아이. 저장할 때 보내는 값이다. */
  const child = classroom?.children.find((c) => c.id === childId);
  const kidsShown = !editId && (!child || kidsOpen);
  /** 목록과 숫자를 거르고 있는 아이. 없으면 반 전체다. */
  const onlyChild = classroom?.children.find((c) => c.id === onlyChildId);
  const edited = records.find((r) => r.id === editId);
  /** 저장하지 않은 글이 있나. 고치는 중이면 그 기록과 달라졌는지 본다. */
  const unsaved = edited
    ? fact !== edited.fact || context !== edited.context
    : !!(fact.trim() || (context.trim() && context !== contextBox.auto));
  useUnsavedWarning(unsaved);
  const journalHref = child
    ? `/records/journal?child=${encodeURIComponent(child.id)}&class=${encodeURIComponent(classId)}`
    : "/records/journal";
  // 늦게 온 옛 조회가 최신 목록을 덮지 않게 조회마다 번호를 매긴다.
  const latest = useRef(0);

  /*
    적고 멈추면 AI 에게 영역을 묻는다(ADR-082). 이미 골랐거나 고치는 중이면 묻지 않는다.
    늦게 온 옛 답은 버린다 — 고친 글과 다른 글에 대한 제안이다.
  */
  const askedFor = JSON.stringify([classId, fact.trim(), context.trim()]);
  useEffect(() => {
    // 입력이 바뀌면 진행 중인 물음도 버린다 — 짧게 줄여 다시 묻지 않는 글에도 옛 답이 오면 안 된다.
    const mine = ++asking.current;
    if (picked || editId || !classId || fact.trim().length < SUGGEST_MIN) return;
    const key = askedFor;
    const timer = setTimeout(() => {
      void suggestRecordDomain(classId, fact.trim(), context.trim()).then((found) => {
        if (mine === asking.current) setSuggested({ key, domain: found });
      });
    }, SUGGEST_PAUSE_MS);
    return () => clearTimeout(timer);
  }, [askedFor, fact, context, picked, editId, classId]);
  // 제안은 그것을 물은 글에만 보인다. 글을 바꾸거나 저장해 비우면 옛 제안은 사라진다.
  const suggestion = !picked && !editId && suggested?.key === askedFor ? suggested.domain : null;

  /** 지금 이 날 · 이 시각에 미리 눌러 둘 상황. 오늘이 아니거나 일과 밖이면 비운다. */
  const autoContext = (rows: DaySlot[], on: string) =>
    on === today() ? (slotAt(rows, nowTime())?.name ?? "") : "";
  useEffect(() => {
    if (!classId || !validDate(date)) return;
    let live = true;
    void dayRoutines(classId, date).then((rows) => {
      if (!live) return;
      setSlots({ key: `${classId}|${date}`, rows });
      if (editId) return;
      const auto = autoContext(rows, date);
      // 교사가 적거나 고른 상황은 덮지 않는다. 미리 눌러 둔 값만 날짜를 따라 바뀐다.
      setContextBox((prev) => (prev.text && prev.text !== prev.auto ? prev : { text: auto, auto }));
    });
    return () => {
      live = false;
    };
  }, [classId, date, editId]);
  const daySlots = slots.key === `${classId}|${date}` ? slots.rows : [];

  useEffect(() => {
    const mine = ++latest.current;
    listRecords(classId)
      .then((items) => {
        if (mine !== latest.current) return;
        setRecords(items);
        setListError("");
        setStatus("ready");
      })
      .catch((e) => {
        if (mine !== latest.current) return;
        setListError(messageFor(e));
        setStatus("error");
      });
    return () => {
      latest.current += 1;
    };
  }, [classId]);
  // 저장·삭제 뒤 서버를 다시 읽는다. 첫 렌더가 이미 loading 이라 상태를 새로 세우지 않는다.
  async function reload() {
    const mine = ++latest.current;
    try {
      const items = await listRecords(classId);
      if (mine !== latest.current) return;
      setRecords(items);
      setListError("");
      setStatus("ready");
    } catch (e) {
      if (mine !== latest.current) return;
      setListError(messageFor(e));
      setStatus("error");
    }
  }

  /**
   * 지금 보고 있는 범위 — 이 반, 아이를 골랐으면 그 아이.
   *
   * **위 숫자와 아래 목록이 같은 것을 세야 한다.** 전에는 숫자가 모든 반·모든 아이였고
   * 목록만 걸러져 있어서, 「누적 48」 아래에 3건짜리 목록이 놓였다.
   */
  const counted = useMemo(
    () =>
      records.filter((r) => r.classId === classId && (!onlyChildId || r.childId === onlyChildId)),
    [records, classId, onlyChildId],
  );
  // 검색은 숫자에 넣지 않는다. 치는 동안 숫자가 따라 움직이면 세고 있는 것이 뭔지 흐려진다.
  const shown = useMemo(
    () =>
      counted.filter(
        (r) =>
          (!area || r.domain === area) &&
          (!day || r.date === day) &&
          `${r.fact} ${r.childName} ${r.context}`.includes(search),
      ),
    [counted, search, area, day],
  );
  /** 영역 칩에 붙는 숫자 — 지금 보고 있는 범위(반 · 아이)에서 센다. */
  const areaCounts = useMemo(() => {
    const n = new Map<string, number>();
    for (const r of counted) n.set(r.domain, (n.get(r.domain) ?? 0) + 1);
    return n;
  }, [counted]);
  /** 온보딩 명단에 없는 반·아동은 수정 폼을 채울 수 없다. 화면 id 를 지어내지 않는다. */
  const canEdit = (record: ServerObservation) =>
    classes.some((c) => c.id === record.classId && c.children.some((k) => k.id === record.childId));

  /** 고친 칸만 지운다. 서버가 함께 짚은 다른 칸은 아직 그대로다. */
  const clearInvalid = (name: string) =>
    setInvalid((prev) => (prev.includes(name) ? prev.filter((f) => f !== name) : prev));

  function askFirst(next: ServerObservation) {
    setAsk(next);
    askDialog.current?.showModal();
  }
  function closeAsk() {
    askDialog.current?.close();
    setAsk(null);
  }
  /** 적던 글을 묻지 않고 덮어쓰지 않는다. */
  function startEdit(record: ServerObservation) {
    if (unsaved) return askFirst(record);
    beginEdit(record);
  }
  function beginEdit(record: ServerObservation) {
    closeAsk();
    // 고치던 기록을 두고 다른 기록을 고칠 때는 처음 것을 그대로 둔다.
    if (!editId) setBeforeEdit({ classId: pickedClass, childId, date, domain: picked, invalid });
    setEditId(record.id);
    setClassId(record.classId);
    setChildId(record.childId);
    setDate(record.date);
    setDomain(record.domain);
    setContext(record.context);
    setFact(record.fact);
    setMessage("");
    setInvalid([]);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
  function cancelEdit() {
    setEditId("");
    setFact("");
    setContext("");
    setMessage("");
    if (!beforeEdit) return setInvalid([]);
    setClassId(beforeEdit.classId);
    setChildId(beforeEdit.childId);
    setDate(beforeEdit.date);
    setDomain(beforeEdit.domain);
    setInvalid(beforeEdit.invalid);
    setBeforeEdit(null);
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    await save();
  }
  /** 저장한다. 떠날 때도 이 길을 탄다. 저장했으면 true — 실패하면 적던 글이 그대로 남는다. */
  async function save(): Promise<boolean> {
    if (!classroom || !child || !validDate(date) || !fact.trim() || date > today()) {
      setMessage("반·아동·관찰 날짜와 실제 관찰 내용을 확인해주세요.");
      return false;
    }
    if (!domain) {
      setMessage("영역을 골라 주세요.");
      setInvalid((prev) => [...prev.filter((f) => f !== "domain"), "domain"]);
      return false;
    }
    const body = { date, domain, context: context.trim(), fact: fact.trim() };
    setPending(true);
    setMessage("");
    setReview(null);
    setGap(null);
    try {
      // 실패하면 입력값을 그대로 둔다 — 다시 적게 하지 않는다.
      let saved: ServerObservation;
      if (editId) {
        const done = await editRecord(editId, body);
        saved = done.record;
        setReview(done.impact);
      } else saved = await addRecord({ ...body, classId, childId });
      lookForGap(saved);
      await reload();
      setFact("");
      const auto = autoContext(daySlots, date);
      setContextBox({ text: auto, auto });
      setEditId("");
      setDomain("");
      setInvalid([]);
      // 다른 아이 기록만 보고 있는 채로 새 기록을 저장하면 저장한 것이 목록에 안 보인다.
      // 「저장했어요」만 뜨고 아무것도 안 늘어나면 저장이 안 된 것으로 읽힌다.
      if (!editId && onlyChildId && onlyChildId !== childId) setOnlyChild("");
      setMessage(editId ? "수정했어요." : "관찰 기록을 저장했어요.");
      setSavedMark(true);
      return true;
    } catch (e) {
      setMessage(messageFor(e));
      setInvalid(invalidFields(e, FIELD_INPUT));
      return false;
    } finally {
      setPending(false);
    }
  }

  /*
    떠날 때(딸깍 시안 「떠날 때」). 계획안처럼 **저장하고 이동한다.** 저장할 수 없을 때 —
    아이나 영역을 안 골랐을 때 — 만 쪽지로 묻는다. 사이드바 링크도 같은 길이다.
    새로고침 · 탭 닫기는 브라우저 창이 묻는다(`useUnsavedWarning`).
  */
  const lacking = !child ? "child" : !domain ? "domain" : null;
  // 저장하는 동안에도 붙잡는다. 놓으면 두 번째 링크가 저장이 끝나기 전에 화면을 닫고,
  // 저장이 실패했을 때 적던 글을 돌려줄 화면이 없다. 저장 중 누른 이동은 무시한다.
  const leavingSave = useRef(false);
  const pass = useLeaveCatch(unsaved && !!fact.trim(), (target) => {
    if (pending || leavingSave.current) return;
    if (lacking) {
      setHeld(target);
      leaveNote.current?.showModal();
      return;
    }
    leavingSave.current = true;
    void save().then((done) => {
      leavingSave.current = false;
      if (done) pass(target);
    });
  });
  function closeNote() {
    leaveNote.current?.close();
    setHeld(null);
  }
  /** 쪽지의 주 버튼 — 빠진 것을 고르러 돌아간다. */
  function pickMissing() {
    closeNote();
    if (lacking === "child") {
      setKidsOpen(true);
      setInvalid((prev) => [...prev.filter((f) => f !== "childId"), "childId"]);
    } else setInvalid((prev) => [...prev.filter((f) => f !== "domain"), "domain"]);
  }
  function discardAndGo() {
    const target = held;
    closeNote();
    if (target) pass(target);
  }
  /** 저장한 기록에 빠진 것이 있나 AI 에게 묻는다. 기다리지 않는다 — 저장은 이미 끝났다. */
  function lookForGap(saved: ServerObservation) {
    void missingInRecord(saved.id).then((parts) => {
      if (parts[0] && GAP_TEXT[parts[0]]) setGap({ record: saved, part: parts[0] });
    });
  }
  async function remove(record: ServerObservation) {
    if (!window.confirm("이 관찰 기록을 지울까요? 되돌릴 수 없어요.")) return;
    setPending(true);
    setMessage("");
    setReview(null);
    try {
      setReview(await removeRecord(record.id));
      if (editId === record.id) cancelEdit();
      await reload();
      setMessage("기록을 지웠어요.");
    } catch (e) {
      setMessage(messageFor(e));
    } finally {
      setPending(false);
    }
  }

  /*
    **반 명단**을 못 불러오면 안내 하나만 둔다. 「먼저 반과 아동을 등록해주세요」가 같이
    보이면 멀쩡한 명단을 다시 만들러 간다.

    **목록만** 못 불러온 것은 다르다. 적는 칸은 다른 길(POST)로 저장하므로 그대로 쓸 수
    있다. 여기까지 묶어 화면을 지우면, 낮에 조회가 한 번 흔들린 교사가 그날 기록을 아예
    못 남긴다 — 보는 걸 못 하는 것보다 무겁다. 목록 자리의 오류는 `RecordList` 가 이미
    자기 자리에서 말한다.

    저장 · 삭제 실패는 둘 다 아니다 — 적던 글이 남아야 한다.
  */
  if (classError) {
    return (
      <WorkspacePage
        title="관찰 기록"
        description="아이의 말과 행동을 적어 둡니다. 적은 것으로 일지를 만듭니다."
      >
        <Message error>{classError}</Message>
      </WorkspacePage>
    );
  }
  return (
    <WorkspacePage
      title="관찰 기록"
      description="아이의 말과 행동을 적어 둡니다. 적은 것으로 일지를 만듭니다."
    >
      {/* 반은 사이드바 맨 위에서 고른다. 화면 안에 또 두면 두 곳에서 같은 것을 고르게 되어
          어느 쪽이 이기는지 교사가 알 수 없다. */}
      {/* 머리말 그림판(「있는 그대로 기록하면…」)을 걷었다. 화면에서 제일 크고 노랗던
          자리인데 하는 말이 없었고, 거기 달린 단추는 다른 화면으로 나가는 길이었다.
          보러 온 교사 눈에 제일 먼저 들어오는 것이 「나가기」였다. */}
      <Message>{message}</Message>
      <ReviewNotice impact={review} />
      {gap && (
        <p className={ws.recordGap} role="status">
          {GAP_TEXT[gap.part]}{" "}
          <button type="button" className={ws.link} onClick={() => startEdit(gap.record)}>
            이어 쓰기
          </button>
        </p>
      )}
      {/* 왼쪽에 적고 오른쪽에 쌓인다 — 일과 기록 · 계획안과 같은 짜임이다.
          폼을 화면 너비로 펴면 「본 대로 적기」 한 줄이 1,800px 로 늘어나 읽히지 않았고,
          쌓인 기록은 폼 밑으로 밀려 스크롤해야 보였다. 폼은 따라 내려와 있어
          오른쪽 기록을 「고치기」 하면 바로 옆에서 고친다. */}
      <div className={`${ws.grid} ${ws.recordGrid}`}>
        <div className={ws.side}>
          {/* 왼쪽 · 오른쪽 머리를 같은 줄에 세운다 — 카드 안에 있던 제목이 오른쪽 「쌓인 기록」보다
              한 칸 내려앉아 두 칸 높이가 어긋나 보였다. */}
          <div className={ws.recordListHead}>
            <h2 className={ws.recordListTitle}>
              {editId ? "기록 고치기" : "오늘 본 것 적기"}
              {savedMark && (
                <span className={ws.recordSaved} role="status">
                  저장됨
                </span>
              )}
            </h2>
            {/* 기록하러 온 교사가 다음에 하려는 일이 관찰일지다. 목록 머리 작은 단추로는 눈에 안
                띄었다. 적는 칸 바로 위, 화면을 열자마자 보이는 자리에 둔다. */}
            <Link className={ws.recordJournalLink} href={journalHref}>
              관찰일지 만들기 →
            </Link>
          </div>
          <section className={`${ws.card} ${ws.recordForm}`} data-tour="records-form">
            {!classes.some((c) => c.children.length) ? (
              <Empty title="먼저 아이를 등록해 주세요">
                <Link href="/onboarding">아이 등록하기 →</Link>
              </Empty>
            ) : (
              <form onSubmit={submit}>
                {/* 요청 중에는 폼 전체가 잠긴다 — 보낸 값과 그 뒤 입력이 섞이지 않게. */}
                <fieldset
                  className={ws.recordWrite}
                  disabled={pending}
                  style={{ border: 0, margin: 0, padding: 0, minWidth: 0 }}
                >
                  {/* 이름표와 회색 네모가 다섯 개 늘어선 칸이 가입 양식처럼 보였다.
                      「오늘, 쌓기 영역에서 하늘이가 …」 로 읽히는 문장 속 빈칸으로 바꿨다. */}
                  {daySlots.length > 0 && (
                    <DayStrip
                      slots={daySlots}
                      context={context}
                      onPick={(text) => {
                        setContext(text);
                        clearInvalid("context");
                      }}
                    />
                  )}
                  <p className={ws.recordSentence}>
                    <span className={ws.recordDateBlank}>
                      <span className={ws.recordBlank} aria-hidden="true">
                        {dateLabel(date)}
                      </span>
                      <input
                        name="date"
                        required
                        type="date"
                        aria-label="날짜"
                        max={today()}
                        value={date}
                        {...fieldErrorProps("date", invalid)}
                        onClick={(e) => openPicker(e.currentTarget)}
                        onChange={(e) => {
                          setDate(e.target.value);
                          clearInvalid("date");
                        }}
                      />
                    </span>
                    ,{" "}
                    <span className={ws.recordNowrap}>
                      <input
                        name="context"
                        aria-label="어디서, 무슨 놀이"
                        className={ws.recordBlank}
                        maxLength={CONTEXT_MAX}
                        value={context}
                        {...fieldErrorProps("context", invalid)}
                        onChange={(e) => {
                          setContext(e.target.value);
                          clearInvalid("context");
                        }}
                        placeholder="실내놀이, 쌓기"
                      />
                      에서
                    </span>{" "}
                    <button
                      type="button"
                      className={ws.recordBlank}
                      data-empty={!child || undefined}
                      disabled={!!editId}
                      aria-expanded={kidsShown}
                      aria-controls="record-kids"
                      onClick={() => setKidsOpen((on) => !on)}
                    >
                      {child ? subjectOf(child.name) : "누가"}
                    </button>
                  </p>
                  <FieldError name="date" invalid={invalid} />
                  <FieldError name="context" invalid={invalid} />
                  {kidsShown && (
                    <div id="record-kids" className={ws.recordKids} role="group" aria-label="아이">
                      {classroom?.children.map((c) => (
                        <button
                          key={c.id}
                          type="button"
                          className={ws.recordKid}
                          aria-pressed={c.id === childId}
                          {...fieldErrorProps("childId", invalid)}
                          onClick={() => {
                            setChildId(c.id === childId ? "" : c.id);
                            setKidsOpen(false);
                            clearInvalid("childId");
                          }}
                        >
                          <ChildNote name={c.name} mark={markFor(c.id)} size={24} />
                          {c.name}
                        </button>
                      ))}
                    </div>
                  )}
                  <FieldError name="childId" invalid={invalid} />
                  {editId && <small>아이와 반은 고칠 수 없어요. 지우고 다시 적어 주세요.</small>}
                  <textarea
                    required
                    aria-label="본 대로 적기"
                    className={ws.recordFactInput}
                    maxLength={5000}
                    value={fact}
                    {...fieldErrorProps("fact", invalid)}
                    onChange={(e) => {
                      setFact(e.target.value);
                      setSavedMark(false);
                      clearInvalid("fact");
                    }}
                    placeholder={"블록 세 개를 쌓은 뒤 “더 높이 만들래”라고 말했다."}
                  />
                  <FieldError name="fact" invalid={invalid} />
                  {/* 적는 순서를 보여준다(FR-404). 교사가 빠뜨리기 쉬운 것이 「반응」과 「교사 지원」인데,
                    그 둘이 없으면 AI 가 해석과 지원을 쓸 근거가 없다. 안내일 뿐 막지는 않는다. */}
                  <p className={ws.recordGuide}>
                    <span className={ws.recordCount}>{fact.length.toLocaleString()} / 5,000자</span>
                    <span className={ws.recordTip} data-tour="records-order">
                      <b>TIP!</b> “상황 → 행동 → 반응 → 교사 지원” 순서로 적어봐요!
                    </span>
                  </p>
                  <div className={ws.recordAreaRow}>
                    <span className={ws.recordAreaLabel} id="record-area-label">
                      영역
                    </span>
                    {/* 평소에는 그림만, 마우스를 올리거나 고르면 옆으로 펼쳐져 이름이 보인다.
                        이름은 늘 버튼 안에 있어 화면 낭독기는 그대로 읽는다. */}
                    <div
                      className={ws.recordAreas}
                      role="group"
                      aria-labelledby="record-area-label"
                      {...fieldErrorProps("domain", invalid)}
                    >
                      {(!domain || domains.includes(domain) ? domains : [domain, ...domains]).map(
                        (d) => (
                          <button
                            key={d}
                            type="button"
                            className={ws.recordArea}
                            data-tone={DOMAIN_LOOK[d]?.tone}
                            data-plain={!DOMAIN_LOOK[d] || undefined}
                            data-suggested={d === suggestion || undefined}
                            aria-describedby={d === suggestion ? "record-area-hint" : undefined}
                            aria-pressed={d === domain}
                            onClick={() => {
                              setDomain(d);
                              clearInvalid("domain");
                            }}
                          >
                            {DOMAIN_LOOK[d] && (
                              <Icon name={DOMAIN_LOOK[d].icon} width={17} height={17} />
                            )}
                            <span>{d}</span>
                          </button>
                        ),
                      )}
                    </div>
                  </div>
                  {suggestion && (
                    <small id="record-area-hint" className={ws.recordAreaHint}>
                      점선은 AI 제안이에요. 맞으면 눌러 주세요.
                    </small>
                  )}
                  <FieldError name="domain" invalid={invalid} />
                  <div className={ws.recordSubmit}>
                    {editId && (
                      <button type="button" className={ws.secondary} onClick={cancelEdit}>
                        그만두기
                      </button>
                    )}
                    <button className={ws.primary}>{editId ? "고친 대로 저장" : "기록하기"}</button>
                  </div>
                </fieldset>
              </form>
            )}
          </section>
        </div>
        <section className={ws.stack} data-tour="records-list">
          <div className={ws.recordListHead}>
            <h2 className={ws.recordListTitle}>쌓인 기록</h2>
            <Link href="/records/children" className={ws.recordWay}>
              아이별 기록
            </Link>
          </div>
          {/* 홈의 「이 아이 기록 보기」로 들어오면 목록이 한 아이만 남는다. 그 사실을 화면이
              말해 주지 않아서, 들어온 교사가 「제대로 찾아온 건가」를 알 수 없었다. */}
          {onlyChild && (
            <p className={ws.between}>
              <span className={ws.badge}>{onlyChild.name} 기록만 보는 중</span>
              <button type="button" className={ws.link} onClick={() => setOnlyChild("")}>
                모두 보기 →
              </button>
            </p>
          )}
          <div className={ws.recordFindRow}>
            <label className={ws.recordFind}>
              <SearchMark />
              <input
                name="record_search"
                aria-label="기록 찾기"
                placeholder="아이 이름이나 적은 내용으로 찾기"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </label>
            {/* 날짜로 거르기. 달력 그림을 누르면 달력이 열린다. */}
            <span className={ws.recordDayPick} data-on={day ? "" : undefined}>
              <CalendarMark />
              {day && <span>{dateLabel(day)}</span>}
              <input
                type="date"
                aria-label="날짜로 거르기"
                max={today()}
                value={day}
                onClick={(e) => openPicker(e.currentTarget)}
                onChange={(e) => setDay(e.target.value)}
              />
            </span>
          </div>
          {day && (
            <p className={ws.between}>
              <span className={ws.badge}>{dateLabel(day)} 기록만 보는 중</span>
              <button type="button" className={ws.link} onClick={() => setDay("")}>
                모든 날짜 보기 →
              </button>
            </p>
          )}
          <div className={ws.recordFilters} role="group" aria-label="영역으로 거르기">
            {["", ...Object.keys(DOMAIN_LOOK)].map((name) => (
              <button
                key={name || "all"}
                type="button"
                aria-pressed={area === name}
                className={ws.recordFilter}
                data-tone={DOMAIN_LOOK[name]?.tone}
                onClick={() => setArea(name)}
              >
                {name && <Icon name={DOMAIN_LOOK[name].icon} width={14} height={14} />}
                {name || "전체"}
                <span>{name ? (areaCounts.get(name) ?? 0) : counted.length}</span>
              </button>
            ))}
          </div>
          <RecordList
            status={status}
            error={listError}
            records={shown}
            pending={pending}
            canEdit={canEdit}
            onEdit={startEdit}
            onDelete={remove}
          />
        </section>
      </div>
      <dialog
        ref={askDialog}
        className={ws.ojLeave}
        aria-labelledby="record-ask-title"
        onClose={() => setAsk(null)}
      >
        <Posty pose="hand" face="oh" tone="note" size={78} label={null} />
        <h3 id="record-ask-title">잠깐만요!</h3>
        <p>적던 글을 버리고 이 기록을 고칠까요?</p>
        <div>
          <button type="button" className={ws.secondary} autoFocus onClick={closeAsk}>
            계속 쓰기
          </button>
          {ask && (
            <button type="button" className={ws.link} onClick={() => beginEdit(ask)}>
              버리고 고치기
            </button>
          )}
        </div>
      </dialog>
      {/* 떠날 때 저장할 수 없으면 붙는 포스트잇. 테이프에 매달려 처음 한 번 흔들린다. */}
      <dialog
        ref={leaveNote}
        className={ws.recordLeave}
        aria-labelledby="record-leave-title"
        aria-describedby="record-leave-why"
        onClose={() => setHeld(null)}
      >
        {held && (
          <>
            <h3 id="record-leave-title">잠깐만요!</h3>
            <p id="record-leave-why">
              {lacking === "domain" ? "영역을 골라야 저장돼요." : "누구 기록인지 골라야 저장돼요."}
            </p>
            <div>
              <button type="button" className={ws.primary} autoFocus onClick={pickMissing}>
                {lacking === "domain" ? "영역 고르기" : "아이 고르기"}
              </button>
              <button type="button" className={ws.recordDiscard} onClick={discardAndGo}>
                버리고 이동
              </button>
            </div>
          </>
        )}
      </dialog>
    </WorkspacePage>
  );
}

/**
 * 이 화면을 떠나는 누르기(앱 안 링크 · `data-leave` 단추)를 누르기 전에 붙잡는다(캡처 단계).
 * Next 앱 라우터에는 이동을 멈추는 훅이 없다. 돌려주는 함수로 붙잡은 것을 다시 누르면 그대로 떠난다.
 * 관찰일지 편집기(`ObservationJournalEditor` 의 `useLeaveGuard`)와 같은 방식이다.
 *
 * ponytail: 브라우저 뒤로 가기는 붙잡지 않는다. 편집기처럼 history 칸을 끼워 넣으면 되지만
 * 저장하고 이동하는 길과 겹쳐 따로 맞춰야 한다.
 */
function useLeaveCatch(on: boolean, onLeave: (target: HTMLElement) => void) {
  const passing = useRef(false);
  const latest = useRef(onLeave);
  useEffect(() => {
    latest.current = onLeave;
  });
  useEffect(() => {
    if (!on) return;
    const catchLeave = (event: MouseEvent) => {
      if (passing.current || event.defaultPrevented || event.button !== 0) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const target = (event.target as Element | null)?.closest<HTMLElement>(
        'a[href]:not([target="_blank"]):not([download]), [data-leave]',
      );
      if (!target || target.closest("dialog")) return;
      if (target.getAttribute("href")?.startsWith("#")) return;
      event.preventDefault();
      event.stopPropagation();
      latest.current(target);
    };
    document.addEventListener("click", catchLeave, true);
    return () => document.removeEventListener("click", catchLeave, true);
  }, [on]);
  return (target: HTMLElement) => {
    passing.current = true;
    target.click();
    passing.current = false;
  };
}

/**
 * 그날 일과 시간표 한 줄 — 보육일지와 같은 모양(손글씨 시각 + 일과 이름). 누르면 상황 칸에 들어가고,
 * 실내 놀이 시간이면 그 아래 「어디서」 흥미 영역을 고른다. 고른 것은 상황 칸 글에서 읽는다.
 */
function DayStrip({
  slots,
  context,
  onPick,
}: {
  slots: DaySlot[];
  context: string;
  onPick: (text: string) => void;
}) {
  const picked = pickedSlot(slots, context);
  return (
    <div className={ws.recordSlots}>
      <div className={ws.recordSlotRow} role="group" aria-label="그날 일과">
        {slots.map((slot, i) => (
          <button
            key={i}
            type="button"
            data-slot
            className={ws.recordSlot}
            aria-pressed={picked?.slot === slot}
            onClick={() => onPick(contextFor(slot.name))}
          >
            <span className={ws.recordSlotTime}>{slot.start}</span>
            {slot.name}
          </button>
        ))}
      </div>
      {picked && isIndoorPlay(picked.slot.name) && (
        <div className={ws.recordPlaces} role="group" aria-labelledby="record-places-label">
          <span id="record-places-label">어디서</span>
          {PLACES.map((place) => (
            <button
              key={place}
              type="button"
              aria-pressed={picked.place === place}
              onClick={() => onPick(contextFor(picked.slot.name, place))}
            >
              {place}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * 고치거나 지운 기록을 쓴 확정 일지 수와 그 일지로 가는 길. 일과 기록 화면과 같은 문구다.
 * 하나면 그 일지를 바로 열고, 여럿이면 보관함으로 보낸다.
 */
function ReviewNotice({ impact }: { impact: ReviewImpact | null }) {
  if (!impact?.affected.length) return null;
  const fresh = impact.newlyStale.length;
  const already = impact.affected.length - fresh;
  const only = impact.affected.length === 1;
  return (
    <Message>
      {fresh > 0 && `이 기록을 쓴 일지 ${fresh}건이 다시 검토 대상이 되었어요. `}
      {already > 0 && `이미 재검토 대상인 일지 ${already}건도 이 변경의 영향을 받았어요. `}
      <Link
        href={
          only
            ? `/documents?id=${encodeURIComponent(documentLocalId(impact.affected[0]))}`
            : "/documents"
        }
      >
        {only ? "일지 보기 →" : "문서 보관함에서 보기 →"}
      </Link>
    </Message>
  );
}

/** 목록의 네 상태. 불러오는 중 · 실패 · 비었음을 먼저 끝내고 아래는 "있다"만 다룬다. */
export function RecordList({
  status,
  error,
  records,
  pending,
  canEdit,
  onEdit,
  onDelete,
}: {
  status: RecordsStatus;
  error: string;
  records: ServerObservation[];
  pending: boolean;
  canEdit: (record: ServerObservation) => boolean;
  onEdit: (record: ServerObservation) => void;
  onDelete: (record: ServerObservation) => void;
}) {
  return (
    <WorkspaceViewState
      status={status}
      error={error}
      loading="관찰 기록을 불러오고 있어요."
      empty={
        !records.length && (
          <Empty
            title="아직 남긴 기록이 없어요"
            art={<Posty pose="sitWave" face="empty" tone="shell" size={92} label={null} />}
          >
            위 칸에 오늘 본 것을 한 줄 적어 보세요.
          </Empty>
        )
      }
    >
      <div className={ws.recordDays}>
        {groupByDate(records).map(([date, day]) => (
          <section key={date} className={ws.recordDay}>
            <h3 className={ws.recordDate}>
              {longDate(date)}
              <span>{day.length}건</span>
            </h3>
            {/* 한 줄이 화면 끝까지 가면 긴 기록은 읽히지 않는다. 폭이 정해진 카드로 나눈다. */}
            <div className={ws.recordCards}>
              {day.map((r) => (
                <RecordItem
                  key={r.id}
                  record={r}
                  pending={pending}
                  editable={canEdit(r)}
                  onEdit={onEdit}
                  onDelete={onDelete}
                />
              ))}
            </div>
          </section>
        ))}
      </div>
    </WorkspaceViewState>
  );
}

/**
 * 기록 한 줄. 평소에는 글만 보이고, 줄을 누르면 그 줄에서만 할 일이 나온다.
 *
 * 전에는 줄마다 단추가 셋이라 기록 열세 건이면 화면에 단추가 서른아홉 개였다.
 * 교사가 보러 온 것은 아이가 한 말이지 단추가 아니다.
 */
function RecordItem({
  record,
  pending,
  editable,
  onEdit,
  onDelete,
}: {
  record: ServerObservation;
  pending: boolean;
  editable: boolean;
  onEdit: (record: ServerObservation) => void;
  onDelete: (record: ServerObservation) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <article className={ws.recordCard} data-open={open || undefined}>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((on) => !on)}
        className={ws.recordRow}
      >
        <span className={ws.recordWho}>
          {/* 아이 표식. 이름 글자를 읽기 전에 누구 기록인지 눈에 먼저 들어온다. */}
          <ChildNote name={record.childName} mark={markFor(record.childId)} size={28} />
          <b>{record.childName}</b>
          {/* 영역 이름은 위 거르기 칩이 읽어 준다. 카드에는 그림과 색만 남겨 아이가 한 말이 먼저 보이게 한다. */}
          {DOMAIN_LOOK[record.domain] ? (
            <span
              className={ws.recordDomain}
              data-tone={DOMAIN_LOOK[record.domain].tone}
              role="img"
              aria-label={record.domain}
              title={record.domain}
            >
              <Icon name={DOMAIN_LOOK[record.domain].icon} width={15} height={15} />
            </span>
          ) : (
            <span className={ws.recordDomain}>{record.domain}</span>
          )}
        </span>
        <span className={ws.recordFact}>{record.fact}</span>
      </button>
      {open && (
        <div className={ws.recordActions}>
          {editable ? (
            <Link
              className={ws.secondary}
              href={`/records/journal?record=${encodeURIComponent(record.id)}&class=${encodeURIComponent(record.classId)}`}
            >
              이 기록으로 일지 만들기
            </Link>
          ) : (
            <small>반·아이 정보를 확인할 수 없어 고칠 수 없어요.</small>
          )}
          <button
            className={ws.secondary}
            disabled={pending || !editable}
            onClick={() => onEdit(record)}
          >
            고치기
          </button>
          <button className={ws.secondary} disabled={pending} onClick={() => onDelete(record)}>
            지우기
          </button>
        </div>
      )}
    </article>
  );
}

/** 날짜 거르기 단추의 달력. */
function CalendarMark() {
  return (
    <svg
      className={ws.recordFindMark}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      aria-hidden="true"
      focusable="false"
    >
      <rect x="4" y="5.5" width="16" height="14" rx="2.5" />
      <path d="M4 10h16M8.5 3.5v4M15.5 3.5v4" />
    </svg>
  );
}

/** 찾기 칸의 돋보기. 글자만 있던 칸이 목록과 같은 흰 네모라 무슨 칸인지 몰랐다. */
function SearchMark() {
  return (
    <svg className={ws.recordFindMark} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <circle cx="10.6" cy="10.6" r="6.4" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path d="M15.4 15.4 20 20" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

const WEEK = ["일", "월", "화", "수", "목", "금", "토"];

/** 날짜 빈칸 글자. 오늘이면 「오늘(11월 5일)」, 아니면 「11월 3일(화)」. */
function dateLabel(date: string) {
  const at = new Date(`${date}T00:00:00Z`);
  if (Number.isNaN(at.getTime())) return "날짜 고르기";
  const day = `${at.getUTCMonth() + 1}월 ${at.getUTCDate()}일`;
  return date === today() ? `오늘(${day})` : `${day}(${WEEK[at.getUTCDay()]})`;
}

/** 「김하늘」 → 「하늘이가」, 「박서아」 → 「서아가」. 문장 속 「누가」 자리에 들어간다. */
export function subjectOf(name: string) {
  const chars = Array.from(name.trim());
  const given = chars.length >= 3 ? chars.slice(1).join("") : chars.join("");
  const last = given.charCodeAt(given.length - 1) - 0xac00;
  const closed = last >= 0 && last < 11172 && last % 28 !== 0;
  return `${given}${closed ? "이가" : "가"}`;
}

/** 날짜 칸을 누르면 달력을 연다. 못 여는 브라우저는 그대로 둔다 — 칸은 키보드로도 고칠 수 있다. */
export function openPicker(input: HTMLInputElement) {
  try {
    input.showPicker();
  } catch {
    /* showPicker 가 없거나 막혔다 */
  }
}

/** 「2026-11-03」 을 「11월 3일 월요일」 로. 묶음 머리라 날짜를 다 읽어 준다. */
function longDate(date: string) {
  const at = new Date(`${date}T00:00:00Z`);
  if (Number.isNaN(at.getTime())) return date;
  return `${at.getUTCMonth() + 1}월 ${at.getUTCDate()}일 ${WEEK[at.getUTCDay()]}요일`;
}

/**
 * 같은 날 기록을 한 묶음으로 센다.
 *
 * 열세 건이 같은 리듬으로 흐르면 「언제 적은 것」이 안 보인다. 목록은 이미 날짜 내림차순이라
 * 차례대로 모으기만 하면 된다 — 다시 정렬하지 않는다.
 */
function groupByDate(records: ServerObservation[]): [string, ServerObservation[]][] {
  const days: [string, ServerObservation[]][] = [];
  for (const record of records) {
    const last = days[days.length - 1];
    if (last && last[0] === record.date) last[1].push(record);
    else days.push([record.date, [record]]);
  }
  return days;
}
