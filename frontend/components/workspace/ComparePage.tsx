"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { DOMAINS, type Section } from "@/lib/workspace/model";
import { useWorkspace } from "@/lib/workspace/store";
import { requestAI } from "@/lib/workspace/ai-client";
import { WorkspacePage, Empty, Message, useClasses, useAIStatus, ws } from "./WorkspaceUI";
export default function ComparePage() {
  const controllerRef = useRef<AbortController | null>(null);
  const { data, error } = useWorkspace();
  const classes = useClasses();
  const available = useAIStatus();
  const [classId, setClassId] = useState("");
  const [childId, setChildId] = useState("");
  const [domain, setDomain] = useState("");
  const [beforeId, setBeforeId] = useState("");
  const [afterId, setAfterId] = useState("");
  const [result, setResult] = useState<{ sections: Section[]; notes: string[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const records = data.observations
    .filter(
      (r) => r.classId === classId && r.childId === childId && (!domain || r.domain === domain),
    )
    .sort((a, b) => a.date.localeCompare(b.date));
  const before = records.find((r) => r.id === beforeId);
  const after = records.find((r) => r.id === afterId);
  const pairValid = !!before && !!after && before.id !== after.id && before.date <= after.date;
  // 선택(또는 저장소 내용)이 바뀌면 이전 AI 결과는 더 이상 유효하지 않다 — 렌더 중에 정리한다.
  const selection = { data, classId, childId, domain, beforeId, afterId };
  const [shown, setShown] = useState(selection);
  if (
    shown.data !== data ||
    shown.classId !== classId ||
    shown.childId !== childId ||
    shown.domain !== domain ||
    shown.beforeId !== beforeId ||
    shown.afterId !== afterId
  ) {
    setShown(selection);
    setResult(null);
    setBusy(false);
  }
  // 진행 중인 요청 취소는 외부 시스템 정리라 effect에 남긴다(의존성이 바뀌거나 언마운트될 때 실행).
  useEffect(
    () => () => controllerRef.current?.abort(),
    [data, classId, childId, domain, beforeId, afterId],
  );
  function reset() {
    setBeforeId("");
    setAfterId("");
    setResult(null);
    setMessage("");
  }
  async function compare() {
    if (!pairValid || busy) return;
    const controller = new AbortController();
    controllerRef.current = controller;
    setBusy(true);
    setMessage("");
    try {
      const result = await requestAI<{ sections: Section[]; notes: string[] }>(
        "compare",
        {
          sources: [before, after].map((r) => ({
            id: r.id,
            classId: r.classId,
            childId: r.childId,
            date: r.date,
            text: r.fact,
            context: r.context,
            domain: r.domain,
          })),
        },
        controller.signal,
      );
      if (!controller.signal.aborted) setResult(result);
    } catch (e) {
      if (!controller.signal.aborted)
        setMessage(e instanceof Error ? e.message : "비교하지 못했어요.");
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }
  return (
    <WorkspacePage
      title="기록 간 비교"
      description="같은 아이의 서로 다른 순간을 나란히 살펴보고, 다음 관찰을 준비해요."
    >
      <section className={ws.hero}>
        <div>
          <div className={ws.eyebrow}>GROWTH · 이어지는 아이의 이야기</div>
          <h2>
            이전의 순간과 오늘,
            <br />
            어떤 점이 달라졌을까요?
          </h2>
          <p>원문 기록을 나란히 비교합니다. 기록되지 않은 행동을 없었다고 판단하지 않아요.</p>
        </div>
        <Link href="/documents" className={ws.primary}>
          누적 기록으로 평가 작성 →
        </Link>
      </section>
      <Message error>{error || message}</Message>
      <section className={ws.card}>
        <div className={ws.row}>
          <label className={ws.field}>
            담당 반
            <select
              disabled={busy}
              value={classId}
              onChange={(e) => {
                setClassId(e.target.value);
                setChildId("");
                reset();
              }}
            >
              <option value="">반 선택</option>
              {classes.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.className}
                </option>
              ))}
            </select>
          </label>
          <label className={ws.field}>
            아동
            <select
              disabled={busy}
              value={childId}
              onChange={(e) => {
                setChildId(e.target.value);
                reset();
              }}
            >
              <option value="">아동 선택</option>
              {classes
                .find((c) => c.id === classId)
                ?.children.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
            </select>
          </label>
          <label className={ws.field}>
            관찰 영역
            <select
              disabled={busy}
              value={domain}
              onChange={(e) => {
                setDomain(e.target.value);
                reset();
              }}
            >
              <option value="">모든 영역</option>
              {DOMAINS.map((d) => (
                <option key={d}>{d}</option>
              ))}
            </select>
          </label>
        </div>
      </section>
      {!childId ? (
        <Empty title="비교할 아동을 선택해주세요">
          아동별 누적 기록과 이전·현재 기록을 확인할 수 있어요.
        </Empty>
      ) : records.length < 2 ? (
        <Empty title="비교하려면 기록이 두 건 이상 필요해요">
          <Link href="/records">새 관찰 기록 입력하기 →</Link>
        </Empty>
      ) : (
        <>
          <div className={ws.equalGrid} style={{ marginTop: 22 }}>
            {[
              ["이전 기록", beforeId, setBeforeId, before],
              ["현재 기록", afterId, setAfterId, after],
            ].map(([label, value, setValue, record]) => {
              const r = record as typeof before;
              return (
                <section className={ws.card} key={label as string}>
                  <label className={ws.field}>
                    {label as string}
                    <select
                      disabled={busy}
                      value={value as string}
                      onChange={(e) => {
                        (setValue as (s: string) => void)(e.target.value);
                        setResult(null);
                      }}
                    >
                      <option value="">기록 선택</option>
                      {records.map((r) => (
                        <option key={r.id} value={r.id}>
                          {r.date} · {r.domain} · {r.fact.slice(0, 25)}
                        </option>
                      ))}
                    </select>
                  </label>
                  {r ? (
                    <>
                      <p className={ws.muted} style={{ marginTop: 18 }}>
                        {r.context || "상황 메모 없음"}
                      </p>
                      <blockquote className={ws.quote}>{r.fact}</blockquote>
                    </>
                  ) : (
                    <Empty title="기록을 선택해주세요" />
                  )}
                </section>
              );
            })}
          </div>
          {before && after && !pairValid && (
            <Message error>
              서로 다른 기록을 선택하고, 이전 기록이 현재 기록보다 늦지 않도록 설정해주세요.
            </Message>
          )}
          <div className={ws.actions}>
            <button
              className={ws.primary}
              disabled={!pairValid || !available || busy}
              onClick={compare}
            >
              {busy ? "근거를 비교하고 있어요…" : "AI로 변화 탐색"}
            </button>
          </div>
          <p className={ws.hint}>
            {available
              ? "두 기록의 관찰 내용과 상황을 비교해 탐색 의견을 제안합니다. 발달 진단이나 확정적인 평가는 제공하지 않아요."
              : "AI 연결 전에는 원문을 나란히 비교할 수 있어요. 변화에 대한 의미 해석은 교사가 검토해주세요."}
          </p>
          {result && (
            <section className={ws.card}>
              <h2>기록에서 살펴볼 점</h2>
              {result.sections.map((s, i) => (
                <section key={i} style={{ marginTop: 20 }}>
                  <h3>{s.heading}</h3>
                  <p>{s.body}</p>
                  <small className={ws.source}>
                    근거:{" "}
                    {s.sourceIds
                      .map((id) => records.find((r) => r.id === id)?.date || "근거 확인 필요")
                      .join(" · ")}
                  </small>
                </section>
              ))}
              <Message>{result.notes.join("\n")}</Message>
            </section>
          )}
          <h2 style={{ margin: "28px 0 20px" }}>
            누적 관찰 흐름{" "}
            <span className={ws.muted}>
              {records.length}건 · {records[0].date} ~ {records[records.length - 1].date}
            </span>
          </h2>
          <div className={ws.timeline}>
            {records.map((r) => (
              <article className={ws.item} key={r.id}>
                <div className={ws.between}>
                  <h3>{r.date}</h3>
                  <span className={ws.badge}>{r.domain}</span>
                </div>
                <p>{r.fact}</p>
              </article>
            ))}
          </div>
        </>
      )}
    </WorkspacePage>
  );
}
