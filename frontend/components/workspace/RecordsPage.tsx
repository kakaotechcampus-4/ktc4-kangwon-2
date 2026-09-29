"use client";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { DOMAINS, today, validDate } from "@/lib/workspace/model";
import { isUnauthenticated } from "@/lib/api/client";
import { listRecords, addRecord, editRecord, removeRecord } from "@/lib/api/records";
import type { ServerObservation } from "@/lib/api/observations";
import { WorkspacePage, Empty, Message, useClasses, ws } from "./WorkspaceUI";

// 서버 observations.context 컬럼이 50자다. 더 받으면 저장할 때 422 다.
const CONTEXT_MAX = 50;

export type RecordsStatus = "loading" | "ready" | "error";

function messageFor(error: unknown) {
  if (isUnauthenticated(error)) return "로그인이 필요해요. 다시 로그인한 뒤 이용해주세요.";
  return error instanceof Error ? error.message : "요청을 처리하지 못했어요.";
}

export default function RecordsPage() {
  const classes = useClasses();
  const [records, setRecords] = useState<ServerObservation[]>([]);
  const [status, setStatus] = useState<RecordsStatus>("loading");
  const [listError, setListError] = useState("");
  const [pending, setPending] = useState(false);
  const [classId, setClassId] = useState("");
  const [childId, setChildId] = useState("");
  const [date, setDate] = useState(today);
  const [domain, setDomain] = useState(DOMAINS[0]);
  const [context, setContext] = useState("");
  const [fact, setFact] = useState("");
  const [editId, setEditId] = useState("");
  const [message, setMessage] = useState("");
  const [search, setSearch] = useState("");
  const classroom = classes.find((c) => c.id === classId);
  const child = classroom?.children.find((c) => c.id === childId);
  // 늦게 온 옛 조회가 최신 목록을 덮지 않게 조회마다 번호를 매긴다.
  const latest = useRef(0);

  useEffect(() => {
    const mine = ++latest.current;
    listRecords()
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
  }, []);
  // 저장·삭제 뒤 서버를 다시 읽는다. 첫 렌더가 이미 loading 이라 상태를 새로 세우지 않는다.
  async function reload() {
    const mine = ++latest.current;
    try {
      const items = await listRecords();
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

  const shown = useMemo(
    () =>
      records.filter(
        (r) =>
          (!classId || r.classId === classId) &&
          (!childId || r.childId === childId) &&
          `${r.fact} ${r.childName} ${r.context}`.includes(search),
      ),
    [records, classId, childId, search],
  );
  /** 온보딩 명단에 없는 반·아동은 수정 폼을 채울 수 없다. 화면 id 를 지어내지 않는다. */
  const canEdit = (record: ServerObservation) =>
    classes.some((c) => c.id === record.classId && c.children.some((k) => k.id === record.childId));

  function startEdit(record: ServerObservation) {
    setEditId(record.id);
    setClassId(record.classId);
    setChildId(record.childId);
    setDate(record.date);
    setDomain(record.domain);
    setContext(record.context);
    setFact(record.fact);
    setMessage("");
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
      setMessage(editId ? "수정했어요." : "관찰 기록을 저장했어요.");
    } catch (e) {
      setMessage(messageFor(e));
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

  return (
    <WorkspacePage
      title="교사 관찰 기록"
      description="아이의 말과 행동, 선생님이 직접 본 순간을 남겨주세요."
    >
      <section className={ws.hero}>
        <div>
          <div className={ws.eyebrow}>RECORD · 하루의 작은 발견</div>
          <h2>
            있는 그대로 기록하면,
            <br />
            의미 있는 성장의 이야기가 돼요.
          </h2>
          <p>사실은 교사의 기록에서, 해석과 지원은 그 근거 위에서 시작합니다.</p>
        </div>
        <Link href="/documents" className={ws.primary}>
          기록으로 문서 만들기 →
        </Link>
      </section>
      <div className={ws.stats}>
        {[
          ["누적 관찰 기록", records.length],
          ["오늘 남긴 기록", records.filter((r) => r.date === today()).length],
          ["기록한 아동", new Set(records.map((r) => `${r.classId}:${r.childId}`)).size],
        ].map(([label, value]) => (
          <div className={ws.card} key={label}>
            <p className={ws.muted}>{label}</p>
            <strong className={ws.count}>{value}</strong>
          </div>
        ))}
      </div>
      <Message>{message}</Message>
      <div className={ws.grid}>
        <section className={ws.card}>
          <div className={ws.between}>
            <h2>{editId ? "관찰 기록 수정" : "새 관찰 기록"}</h2>
            <Link href="/onboarding" className={ws.link}>
              반·아동 관리
            </Link>
          </div>
          <p className={ws.hint}>
            기록은 서버에 저장돼요. 다른 기기에서 로그인해도 같은 목록을 볼 수 있어요.
          </p>
          {!classes.some((c) => c.children.length) ? (
            <Empty title="먼저 우리 반과 아동을 등록해주세요">
              <Link href="/onboarding">반·아동 등록하기 →</Link>
            </Empty>
          ) : (
            <form onSubmit={submit}>
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
                      onChange={(e) => {
                        setClassId(e.target.value);
                        setChildId("");
                      }}
                    >
                      <option value="">반 선택</option>
                      {classes.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.className || "이름 없는 반"}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className={ws.field}>
                    아동
                    <select
                      required
                      disabled={!!editId}
                      value={childId}
                      onChange={(e) => setChildId(e.target.value)}
                    >
                      <option value="">아동 선택</option>
                      {classroom?.children.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                {editId && <small>반과 아동은 수정할 수 없어요. 지우고 다시 등록해주세요.</small>}
                <div className={ws.row}>
                  <label className={ws.field}>
                    관찰 날짜
                    <input
                      required
                      type="date"
                      max={today()}
                      value={date}
                      onChange={(e) => setDate(e.target.value)}
                    />
                  </label>
                  <label className={ws.field}>
                    관찰 영역
                    <select value={domain} onChange={(e) => setDomain(e.target.value)}>
                      {DOMAINS.map((d) => (
                        <option key={d}>{d}</option>
                      ))}
                    </select>
                  </label>
                </div>
                <label className={ws.field}>
                  놀이 상황 / 장소
                  <input
                    maxLength={CONTEXT_MAX}
                    value={context}
                    onChange={(e) => setContext(e.target.value)}
                    placeholder="예: 오전 자유놀이 · 쌓기 영역"
                  />
                  <small>
                    {context.length} / {CONTEXT_MAX}자
                  </small>
                </label>
                <label className={ws.field}>
                  실제로 관찰한 사실
                  <textarea
                    required
                    maxLength={5000}
                    value={fact}
                    onChange={(e) => setFact(e.target.value)}
                    placeholder={
                      "예: 블록 세 개를 쌓은 뒤 “더 높이 만들래”라고 말했다. 블록이 쓰러지자 넓은 블록을 아래에 놓고 다시 쌓았다."
                    }
                  />
                  <small>{fact.length} / 5,000자 · 실제 행동과 발언을 적어주세요.</small>
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
            <Link href="/compare" className={ws.link}>
              이전 기록과 비교 →
            </Link>
          </div>
          <input
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
  if (status === "loading") {
    return (
      <div className={ws.loading} aria-busy="true">
        <span>🌱</span>
        <p>관찰 기록을 불러오고 있어요.</p>
      </div>
    );
  }
  if (status === "error") {
    return <Message error>{error}</Message>;
  }
  if (!records.length) {
    return (
      <Empty title="아직 남긴 기록이 없어요">
        첫 관찰을 입력하고 아이의 이야기를 시작해보세요.
      </Empty>
    );
  }
  return (
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
      {/* 문서 진입점은 문서 화면이 서버 기록을 읽게 된 뒤에 다시 연다. */}
      <div className={ws.actions}>
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
