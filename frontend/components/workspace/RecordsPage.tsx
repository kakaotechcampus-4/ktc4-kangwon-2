"use client";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { today, validDate } from "@/lib/workspace/model";
import { useObservationDomains } from "@/lib/hooks/use-observation-domains";
import { ROUTINES_UNMAPPED, routinesPath } from "@/lib/workspace/routines-route";
import { isUnauthenticated, invalidFields } from "@/lib/api/client";
import { listRecords, addRecord, editRecord, removeRecord } from "@/lib/api/records";
import type { ServerObservation } from "@/lib/api/observations";
import { classServerId } from "@/lib/api/onboarding";
import { useClientState } from "@/lib/hooks/use-client-state";
import { chosenClassFor, loadClassSettings } from "@/lib/onboarding/settings";
import { WorkspacePage, Empty, Message, useClasses, ws } from "./WorkspaceUI";
import {
  WorkspaceViewState,
  FieldError,
  fieldErrorProps,
  type ViewStatus,
} from "./WorkspaceViewState";

const ENTRY_NONE = { classId: "", childId: "" };

// 서버 observations.context 컬럼이 50자다. 더 받으면 저장할 때 422 다.
const CONTEXT_MAX = 50;

export type RecordsStatus = ViewStatus;

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
  const [picked, setDomain] = useState("");
  const domain = picked || domains[0];
  const [context, setContext] = useState("");
  const [fact, setFact] = useState("");
  const [editId, setEditId] = useState("");
  const [message, setMessage] = useState("");
  const [invalid, setInvalid] = useState<string[]>([]);
  const [classError, setClassError] = useState("");
  const classes = useClasses(setClassError);
  const [search, setSearch] = useState("");
  /*
    적는 칸은 접어 둔다.

    전에는 「새 관찰 기록」 폼이 화면 **왼쪽 절반**을 늘 차지해서, 기록을 보러 들어온
    교사가 목록을 찾아야 했다. 보러 오는 길(홈의 「전체 기록」·「이 아이 기록 보기」)이
    둘이나 되는데 도착한 화면의 주인공은 적는 칸이었다.

    고칠 때(`editId`)는 접혀 있어도 열린다 — 누른 것이 안 보이면 안 된다.
  */
  const [writing, setWriting] = useState(false);
  const classroom = classes.find((c) => c.id === classId);
  /** 적는 칸이 고른 아이. 저장할 때 보내는 값이다. */
  const child = classroom?.children.find((c) => c.id === childId);
  /** 목록과 숫자를 거르고 있는 아이. 없으면 반 전체다. */
  const onlyChild = classroom?.children.find((c) => c.id === onlyChildId);
  // 늦게 온 옛 조회가 최신 목록을 덮지 않게 조회마다 번호를 매긴다.
  const latest = useRef(0);

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
    () => counted.filter((r) => `${r.fact} ${r.childName} ${r.context}`.includes(search)),
    [counted, search],
  );
  /** 온보딩 명단에 없는 반·아동은 수정 폼을 채울 수 없다. 화면 id 를 지어내지 않는다. */
  const canEdit = (record: ServerObservation) =>
    classes.some((c) => c.id === record.classId && c.children.some((k) => k.id === record.childId));

  /** 고친 칸만 지운다. 서버가 함께 짚은 다른 칸은 아직 그대로다. */
  const clearInvalid = (name: string) =>
    setInvalid((prev) => (prev.includes(name) ? prev.filter((f) => f !== name) : prev));

  function startEdit(record: ServerObservation) {
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
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!classroom || !child || !validDate(date) || !fact.trim() || date > today()) {
      setMessage("반·아동·관찰 날짜와 실제 관찰 내용을 확인해주세요.");
      return;
    }
    const body = { date, domain, context: context.trim(), fact: fact.trim() };
    setPending(true);
    setMessage("");
    try {
      // 실패하면 입력값을 그대로 둔다 — 다시 적게 하지 않는다.
      if (editId) await editRecord(editId, body);
      else await addRecord({ ...body, classId, childId });
      await reload();
      setFact("");
      setContext("");
      setEditId("");
      setInvalid([]);
      // 다른 아이 기록만 보고 있는 채로 새 기록을 저장하면 저장한 것이 목록에 안 보인다.
      // 「저장했어요」만 뜨고 아무것도 안 늘어나면 저장이 안 된 것으로 읽힌다.
      if (!editId && onlyChildId && onlyChildId !== childId) setOnlyChild("");
      setMessage(editId ? "수정했어요." : "관찰 기록을 저장했어요.");
    } catch (e) {
      setMessage(messageFor(e));
      setInvalid(invalidFields(e, FIELD_INPUT));
    } finally {
      setPending(false);
    }
  }
  async function remove(record: ServerObservation) {
    if (!window.confirm("이 관찰 기록을 지울까요? 되돌릴 수 없어요.")) return;
    setPending(true);
    setMessage("");
    try {
      await removeRecord(record.id);
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
        description="아이의 말과 행동을 기록하고, 일지 작성에 활용하세요."
      >
        <Message error>{classError}</Message>
      </WorkspacePage>
    );
  }
  // 목록을 못 읽은 동안 숫자는 감춘다. 0 은 「기록이 없다」는 말이라 거짓말이 된다.
  const countable = status !== "error";

  return (
    <WorkspacePage
      title="관찰 기록"
      description="아이의 말과 행동을 기록하고, 일지 작성에 활용하세요."
    >
      {/* 머리말 그림판(「있는 그대로 기록하면…」)을 걷었다. 화면에서 제일 크고 노랗던
          자리인데 하는 말이 없었고, 거기 달린 단추는 다른 화면으로 나가는 길이었다.
          보러 온 교사 눈에 제일 먼저 들어오는 것이 「나가기」였다. */}
      <div className={ws.stats} hidden={!countable}>
        {[
          [
            onlyChild ? `${onlyChild.name} 기록` : `${classroom?.className ?? "우리 반"} 기록`,
            counted.length,
          ],
          ["오늘 남긴 기록", counted.filter((r) => r.date === today()).length],
          onlyChild
            ? ["기록한 영역", new Set(counted.map((r) => r.domain)).size]
            : ["기록한 아동", new Set(counted.map((r) => r.childId)).size],
        ].map(([label, value]) => (
          <div className={ws.card} key={label}>
            <p className={ws.muted}>{label}</p>
            <strong className={ws.count}>{value}</strong>
          </div>
        ))}
      </div>
      <Message>{message}</Message>
      <div className={ws.stack}>
        <section className={ws.card}>
          <div className={ws.between}>
            <h2>{editId ? "관찰 기록 수정" : "새 관찰 기록"}</h2>
            <span className={ws.actions}>
              <Link href="/onboarding" className={ws.link}>
                반·아동 관리
              </Link>
              {!editId && (
                <button
                  type="button"
                  className={ws.secondary}
                  aria-expanded={writing}
                  onClick={() => setWriting((on) => !on)}
                >
                  {writing ? "접기" : "＋ 새 관찰 기록 쓰기"}
                </button>
              )}
            </span>
          </div>
          {!(writing || editId) ? (
            <p className={ws.hint}>
              길게 적을 때 여기를 펼치세요. 한 줄만 남길 때는 우리 반 홈이 더 빨라요.
            </p>
          ) : !classes.some((c) => c.children.length) ? (
            <Empty title="먼저 우리 반과 아동을 등록해주세요">
              <Link href="/onboarding">반·아동 등록하기 →</Link>
            </Empty>
          ) : (
            <form onSubmit={submit}>
              <p className={ws.hint}>
                기록은 서버에 저장돼요. 다른 기기에서 로그인해도 같은 목록을 볼 수 있어요.
              </p>
              {/* 요청 중에는 폼 전체가 잠긴다 — 보낸 값과 그 뒤 입력이 섞이지 않게. */}
              <fieldset
                className={ws.form}
                disabled={pending}
                style={{ border: 0, margin: 0, padding: 0, minWidth: 0 }}
              >
                <div className={ws.row}>
                  <label className={ws.field}>
                    담당 반
                    <select
                      required
                      disabled={!!editId}
                      value={classId}
                      {...fieldErrorProps("classId", invalid)}
                      onChange={(e) => {
                        setClassId(e.target.value);
                        setChildId("");
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
                    아동
                    <select
                      required
                      disabled={!!editId}
                      value={childId}
                      {...fieldErrorProps("childId", invalid)}
                      onChange={(e) => {
                        setChildId(e.target.value);
                        clearInvalid("childId");
                      }}
                    >
                      <option value="">아동 선택</option>
                      {classroom?.children.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                    </select>
                    <FieldError name="childId" invalid={invalid} />
                  </label>
                </div>
                {editId && <small>반과 아동은 수정할 수 없어요. 지우고 다시 등록해주세요.</small>}
                <div className={ws.row}>
                  <label className={ws.field}>
                    관찰 날짜
                    <input
                      name="date"
                      required
                      type="date"
                      max={today()}
                      value={date}
                      {...fieldErrorProps("date", invalid)}
                      onChange={(e) => {
                        setDate(e.target.value);
                        clearInvalid("date");
                      }}
                    />
                    <FieldError name="date" invalid={invalid} />
                  </label>
                  <label className={ws.field}>
                    관찰 영역
                    <select
                      value={domain}
                      {...fieldErrorProps("domain", invalid)}
                      onChange={(e) => {
                        setDomain(e.target.value);
                        clearInvalid("domain");
                      }}
                    >
                      {(domains.includes(domain) ? domains : [domain, ...domains]).map((d) => (
                        <option key={d}>{d}</option>
                      ))}
                    </select>
                    <FieldError name="domain" invalid={invalid} />
                  </label>
                </div>
                <label className={ws.field}>
                  놀이 상황 / 장소
                  <input
                    name="context"
                    maxLength={CONTEXT_MAX}
                    value={context}
                    {...fieldErrorProps("context", invalid)}
                    onChange={(e) => {
                      setContext(e.target.value);
                      clearInvalid("context");
                    }}
                    placeholder="예: 오전 자유놀이 · 쌓기 영역"
                  />
                  <small>
                    {context.length} / {CONTEXT_MAX}자
                  </small>
                  <FieldError name="context" invalid={invalid} />
                </label>
                <label className={ws.field}>
                  실제로 관찰한 사실
                  <textarea
                    required
                    maxLength={5000}
                    value={fact}
                    {...fieldErrorProps("fact", invalid)}
                    onChange={(e) => {
                      setFact(e.target.value);
                      clearInvalid("fact");
                    }}
                    placeholder={
                      "예: 오전 자유놀이 시간 쌓기 영역에서 블록 세 개를 쌓은 뒤 “더 높이 만들래”라고 말했다. " +
                      "블록이 쓰러지자 넓은 블록을 아래에 놓고 다시 쌓았다. " +
                      "옆에 있던 친구가 같은 방법으로 따라 했다. 교사는 기다리며 지켜보았다."
                    }
                  />
                  {/* 적는 순서를 보여준다(FR-404). 교사가 빠뜨리기 쉬운 것이 「반응」과 「교사 지원」인데,
                      그 둘이 없으면 AI 가 해석과 지원을 쓸 근거가 없다. 안내일 뿐 막지는 않는다. */}
                  <small>
                    {fact.length} / 5,000자 · <b>상황 → 행동 → 반응 → 교사 지원</b> 순서로 적으면
                    일지가 잘 나와요. 다 적지 않아도 저장됩니다.
                  </small>
                  <FieldError name="fact" invalid={invalid} />
                </label>
                <div className={ws.actions}>
                  <button className={ws.primary}>{editId ? "수정 저장" : "관찰 기록 저장"}</button>
                  {editId && (
                    <button type="button" className={ws.secondary} onClick={cancelEdit}>
                      수정 취소
                    </button>
                  )}
                </div>
              </fieldset>
            </form>
          )}
        </section>
        <section className={ws.stack}>
          <div className={ws.between}>
            <h2>
              차곡차곡 쌓인 기록 <span className={ws.muted}>{shown.length}</span>
            </h2>
            <span className={ws.actions}>
              <Link href="/records/children" className={ws.link}>
                아이별 모아보기 →
              </Link>
              <RoutinesLink classId={classId} date={date} />
              <Link href="/compare" className={ws.link}>
                이전 기록과 비교 →
              </Link>
              <Link href="/documents" className={ws.link}>
                기록으로 문서 만들기 →
              </Link>
            </span>
          </div>
          {/* 홈의 「이 아이 기록 보기」로 들어오면 목록이 한 아이만 남는다. 그 사실을 화면이
              말해 주지 않아서, 들어온 교사가 「제대로 찾아온 건가」를 알 수 없었다. */}
          {onlyChild && (
            <p className={ws.between}>
              <span className={ws.badge}>지금 {onlyChild.name} 기록만 보고 있어요</span>
              <button type="button" className={ws.link} onClick={() => setOnlyChild("")}>
                반 전체 보기 →
              </button>
            </p>
          )}
          <input
            name="record_search"
            aria-label="관찰 기록 검색"
            className={ws.input}
            placeholder="아동 이름, 놀이 내용 검색"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
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
    </WorkspacePage>
  );
}

/**
 * 일과 기록으로 가는 길. 보고 있던 반·날짜를 그대로 들고 간다.
 *
 * **고른 반의 서버 번호를 모르면 보내지 않는다.** 날짜만 들려 보내면 S-J1 이 「반을 안 골랐다」로
 * 읽고 주 반을 연다 — 교사는 B 를 눌렀는데 A 가 열린다 (FR-405).
 */
function RoutinesLink({ classId, date }: { classId: string; date: string }) {
  const href = routinesPath(classId, date);
  if (!href) return <small className={ws.hint}>{ROUTINES_UNMAPPED}</small>;
  return (
    <Link href={href} className={ws.link}>
      일과 기록 →
    </Link>
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
          <Empty title="아직 남긴 기록이 없어요">
            첫 관찰을 입력하고 아이의 이야기를 시작해보세요.
          </Empty>
        )
      }
    >
      <div className={ws.list}>
        {records.map((r) => (
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
    </WorkspaceViewState>
  );
}

/** 기록 카드 하나. 부모의 상태를 모른다 — 수정·삭제는 콜백으로만 알린다. */
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
  return (
    <article className={ws.item}>
      <div className={ws.between}>
        <h3>
          {record.childName} <span className={ws.muted}>· {record.className}</span>
        </h3>
        <span className={ws.badge}>{record.domain}</span>
      </div>
      <p className={ws.muted}>
        {record.date} {record.context && `· ${record.context}`}
      </p>
      <p>{record.fact}</p>
      {!editable && <small>반·아동 정보를 확인할 수 없어 수정할 수 없어요.</small>}
      <div className={ws.actions}>
        {editable && (
          <Link
            className={ws.secondary}
            href={`/documents?record=${encodeURIComponent(record.id)}&class_id=${classServerId(record.classId)}`}
          >
            관찰일지 만들기
          </Link>
        )}
        <button
          className={ws.secondary}
          disabled={pending || !editable}
          onClick={() => onEdit(record)}
        >
          기록 수정
        </button>
        <button className={ws.secondary} disabled={pending} onClick={() => onDelete(record)}>
          기록 삭제
        </button>
      </div>
    </article>
  );
}
