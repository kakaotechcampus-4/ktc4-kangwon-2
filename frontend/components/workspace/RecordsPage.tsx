"use client";
import Link from "next/link";
import { useMemo, useRef, useState } from "react";
import {
  DOMAINS,
  today,
  validDate,
  invalidateDependents,
  type Observation,
} from "@/lib/workspace/model";
import { useWorkspace } from "@/lib/workspace/store";
import { WorkspacePage, Empty, Message, useClasses, ws } from "./WorkspaceUI";

export default function RecordsPage() {
  const { data, ready, error, blocked, save } = useWorkspace();
  const classes = useClasses();
  const [classId, setClassId] = useState("");
  const [childId, setChildId] = useState("");
  const [date, setDate] = useState(today);
  const [domain, setDomain] = useState(DOMAINS[0]);
  const [context, setContext] = useState("");
  const [fact, setFact] = useState("");
  const editBaseline = useRef<Observation | null>(null);
  const [editId, setEditId] = useState("");
  const [message, setMessage] = useState("");
  const [search, setSearch] = useState("");
  const classroom = classes.find((c) => c.id === classId);
  const child = classroom?.children.find((c) => c.id === childId);
  const records = useMemo(
    () =>
      data.observations
        .filter(
          (r) =>
            (!classId || r.classId === classId) &&
            (!childId || r.childId === childId) &&
            `${r.fact} ${r.childName} ${r.context}`.includes(search),
        )
        .sort((a, b) => b.date.localeCompare(a.date)),
    [data.observations, classId, childId, search],
  );
  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!classroom || !child || !validDate(date) || !fact.trim() || date > today()) {
      setMessage("반·아동·관찰 날짜와 실제 관찰 내용을 확인해주세요.");
      return;
    }
    const record: Observation = {
      id: editId || crypto.randomUUID(),
      classId,
      className: classroom.className,
      childId,
      childName: child.name,
      date,
      domain,
      context: context.trim(),
      fact: fact.trim(),
      createdAt:
        data.observations.find((r) => r.id === editId)?.createdAt || new Date().toISOString(),
    };
    if (
      save((prev) => {
        if (
          editId &&
          JSON.stringify(prev.observations.find((r) => r.id === editId)) !==
            JSON.stringify(editBaseline.current)
        )
          throw new Error(
            "다른 작업에서 관찰 기록이 바뀌었어요. 기록 수정을 다시 눌러 최신 내용을 불러와주세요.",
          );
        return {
          ...prev,
          observations: editId
            ? prev.observations.map((r) => (r.id === editId ? record : r))
            : [record, ...prev.observations],
          documents: editId ? invalidateDependents(prev.documents, editId) : prev.documents,
        };
      })
    ) {
      setFact("");
      setContext("");
      setEditId("");
      setMessage(
        editId
          ? "수정했어요. 이 기록을 사용한 문서는 재검토 상태로 전환됩니다."
          : "관찰 기록을 저장했어요. 문서 보관함에서 초안으로 이어갈 수 있어요.",
      );
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
          ["누적 관찰 기록", data.observations.length],
          ["오늘 남긴 기록", data.observations.filter((r) => r.date === today()).length],
          ["기록한 아동", new Set(data.observations.map((r) => `${r.classId}:${r.childId}`)).size],
        ].map(([label, value]) => (
          <div className={ws.card} key={label}>
            <p className={ws.muted}>{label}</p>
            <strong className={ws.count}>{value}</strong>
          </div>
        ))}
      </div>
      <Message error>{error}</Message>
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
            기록은 이 브라우저에 저장됩니다. 중요한 기록은 문서로 내려받아 보관해주세요.
          </p>
          {!classes.some((c) => c.children.length) ? (
            <Empty title="먼저 우리 반과 아동을 등록해주세요">
              <Link href="/onboarding">반·아동 등록하기 →</Link>
            </Empty>
          ) : (
            <form className={ws.form} onSubmit={submit}>
              <div className={ws.row}>
                <label className={ws.field}>
                  담당 반
                  <select
                    required
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
                  <select required value={childId} onChange={(e) => setChildId(e.target.value)}>
                    <option value="">아동 선택</option>
                    {classroom?.children.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
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
                  maxLength={200}
                  value={context}
                  onChange={(e) => setContext(e.target.value)}
                  placeholder="예: 오전 자유놀이 · 쌓기 영역"
                />
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
                <button className={ws.primary} disabled={!ready || blocked}>
                  {editId ? "수정 저장" : "관찰 기록 저장"}
                </button>
                {editId && (
                  <button
                    type="button"
                    className={ws.secondary}
                    onClick={() => {
                      setEditId("");
                      setFact("");
                      setContext("");
                    }}
                  >
                    수정 취소
                  </button>
                )}
              </div>
            </form>
          )}
        </section>
        <section className={ws.stack}>
          <div className={ws.between}>
            <h2>
              차곡차곡 쌓인 기록 <span className={ws.muted}>{records.length}</span>
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
          {!records.length ? (
            <Empty title="아직 남긴 기록이 없어요">
              첫 관찰을 입력하고 아이의 이야기를 시작해보세요.
            </Empty>
          ) : (
            <div className={ws.list}>
              {records.map((r) => (
                <article key={r.id} className={ws.item}>
                  <div className={ws.between}>
                    <h3>
                      {r.childName} <span className={ws.muted}>· {r.className}</span>
                    </h3>
                    <span className={ws.badge}>{r.domain}</span>
                  </div>
                  <p className={ws.muted}>
                    {r.date} {r.context && `· ${r.context}`}
                  </p>
                  <p>{r.fact}</p>
                  <div className={ws.actions}>
                    <button
                      className={ws.secondary}
                      onClick={() => {
                        editBaseline.current = r;
                        setEditId(r.id);
                        setClassId(r.classId);
                        setChildId(r.childId);
                        setDate(r.date);
                        setDomain(r.domain);
                        setContext(r.context);
                        setFact(r.fact);
                        setMessage("");
                        window.scrollTo({ top: 0, behavior: "smooth" });
                      }}
                    >
                      기록 수정
                    </button>
                    <Link
                      className={ws.secondary}
                      href={`/documents?record=${encodeURIComponent(r.id)}`}
                    >
                      문서로 작성 →
                    </Link>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
    </WorkspacePage>
  );
}
