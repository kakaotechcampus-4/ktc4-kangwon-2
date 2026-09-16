"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  compareEvidence,
  DOCUMENT_KINDS,
  downloadText,
  today,
  validPeriod,
  validateDocument,
  type DocumentKind,
  type SavedDocument,
} from "@/lib/workspace/model";
import { useWorkspace } from "@/lib/workspace/store";
import { requestAI } from "@/lib/workspace/ai-client";
import { WorkspacePage, Empty, Message, useClasses, useAIStatus, ws } from "./WorkspaceUI";
const MANUAL =
  "https://www.kicece.or.kr/kce/front/keyword?keyword=%EB%A7%A4%EB%89%B4%EC%96%BC&x=0&y=0";
export default function EvaluationPage() {
  const available = useAIStatus();
  const [checking, setChecking] = useState(false);
  const reviewController = useRef<AbortController | null>(null);
  const [aiResults, setAiResults] = useState<
    { criterionId: string; verdict: string; quote: string; reason: string }[] | null
  >(null);
  const [crossResults, setCrossResults] = useState<{
    issues: { documentId: string; quote: string; reason: string }[];
    notes: string[];
  } | null>(null);
  const { data, error, save } = useWorkspace();
  const classes = useClasses();
  const [active, setActive] = useState("");
  const [tab, setTab] = useState("items");
  const [label, setLabel] = useState("");
  const [terms, setTerms] = useState("");
  const [source, setSource] = useState("");
  const [message, setMessage] = useState("");
  const [checked, setChecked] = useState(false);
  const [importing, setImporting] = useState(false);
  const [classId, setClassId] = useState("");
  const [childId, setChildId] = useState("");
  const [kind, setKind] = useState<DocumentKind>("dailyLog");
  const [start, setStart] = useState(today);
  const [end, setEnd] = useState(today);
  const [fileText, setFileText] = useState("");
  const [filename, setFilename] = useState("");
  const [busy, setBusy] = useState(false);
  const [reviewed, setReviewed] = useState(false);
  const doc = data.documents.find((d) => d.id === active);
  const evidence = doc ? compareEvidence(doc, data.documents, data.observations) : null;
  const checks = doc
    ? data.criteria.map((c) => {
        const words = c.terms
          .split(",")
          .map((w) => w.trim())
          .filter(Boolean);
        const matches = doc.sections.filter((s) =>
          words.some((w) => s.body.includes(w) || s.heading.includes(w)),
        );
        return { criterion: c, matches };
      })
    : [];
  // 선택한 문서나 저장소 내용이 바뀌면 이전 점검 결과를 렌더 중에 정리한다.
  const [shown, setShown] = useState({ active, data });
  if (shown.active !== active || shown.data !== data) {
    setShown({ active, data });
    setAiResults(null);
    setCrossResults(null);
    setChecked(false);
    setChecking(false);
  }
  // 진행 중인 요청 취소만 effect에 남긴다.
  useEffect(() => () => reviewController.current?.abort(), [active, data]);
  async function semanticCheck(cross: boolean) {
    if (!doc || !evidence || checking) return;
    const controller = new AbortController();
    reviewController.current = controller;
    setChecking(true);
    setMessage("");
    try {
      if (cross) {
        const result = await requestAI<NonNullable<typeof crossResults>>(
          "evidence",
          { document: doc, evidence: evidence.matches },
          controller.signal,
        );
        if (!controller.signal.aborted) setCrossResults(result);
      } else {
        const result = await requestAI<{ results: NonNullable<typeof aiResults> }>(
          "evaluation",
          { document: doc, criteria: data.criteria },
          controller.signal,
        );
        if (!controller.signal.aborted) setAiResults(result.results);
      }
    } catch (e) {
      if (!controller.signal.aborted)
        setMessage(e instanceof Error ? e.message : "내용을 점검하지 못했어요.");
    } finally {
      if (!controller.signal.aborted) setChecking(false);
    }
  }
  async function upload(file?: File) {
    if (!file) return;
    setBusy(true);
    setMessage("");
    setFileText("");
    setReviewed(false);
    try {
      const form = new FormData();
      form.append("file", file);
      const response = await fetch("/api/templates/extract", { method: "POST", body: form });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error);
      setFileText(result.text);
      setFilename(file.name);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "파일을 읽지 못했어요.");
    } finally {
      setBusy(false);
    }
  }
  function registerEvidence() {
    const c = classes.find((c) => c.id === classId);
    if (!c || !fileText || !validPeriod(start, end) || !reviewed) {
      setMessage("반·작성 기간과 원문 확인 여부를 확인해주세요.");
      return;
    }
    const now = new Date().toISOString();
    const document: SavedDocument = {
      id: crypto.randomUUID(),
      title: filename,
      kind,
      classId,
      className: c.className,
      childId,
      childName: c.children.find((c) => c.id === childId)?.name || "",
      start,
      end,
      sections: [{ heading: "첨부 원문", body: fileText, sourceIds: [] }],
      sources: [],
      status: "confirmed",
      origin: "import",
      createdAt: now,
      updatedAt: now,
      reviewNote:
        "교사가 원문과 기간을 확인하여 등록한 기존 증빙. AI 내용 검증과 공식 평가 판정은 별도.",
    };
    const issues = validateDocument(document);
    if (issues.length) {
      setMessage(issues.join("\n"));
      return;
    }
    if (save((prev) => ({ ...prev, documents: [document, ...prev.documents] }))) {
      setActive(document.id);
      setChecked(false);
      setImporting(false);
      setFileText("");
      setMessage("기존 증빙을 등록했어요. 문서 유형·기간·내용을 기준으로 대조할 수 있어요.");
    }
  }
  function exportReport() {
    if (!doc || !evidence) return;
    downloadText(
      `${doc.title} 점검 결과`,
      [
        "쓱싹요정 · 문서 사전점검 (공식 평가 결과 아님)",
        doc.title,
        `${doc.start} ~ ${doc.end}`,
        `확인일: ${today()}`,
        "",
        ...checks.map(
          (c) =>
            `${c.criterion.label}: ${c.matches.length ? "관련 내용 발견 · 교사 확인 필요" : "근거를 찾지 못함"}\n근거: ${c.matches.map((s) => s.heading + ": " + s.body).join("\n")}\n기준 출처: ${c.criterion.source}`,
        ),
        "",
        ...evidence.required.map(
          (r) => `${DOCUMENT_KINDS[r.kind]}: ${r.documents.length}건 (기간 일부 중첩 기준)`,
        ),
        ...evidence.linked.map((r) => `${r.source.date} 원본: ${r.state}`),
        "키워드 일치는 요구사항 충족을 의미하지 않습니다. 실제 내용과 공식 기준을 확인해주세요.",
      ].join("\n"),
    );
  }
  return (
    <WorkspacePage
      title="평가제 · 증빙자료 점검"
      description="문서의 내용, 작성 기간과 연결된 근거를 함께 살펴보세요."
    >
      <section className={ws.hero}>
        <div>
          <div className={ws.eyebrow}>REVIEW · 근거가 이어지는 기록</div>
          <h2>
            빠진 항목은 없는지,
            <br />
            기록의 연결은 맞는지.
          </h2>
          <p>기관에서 확인한 평가 기준을 등록하고, 실제 문서와 증빙을 대조해요.</p>
        </div>
        <button className={ws.primary} onClick={() => setImporting(!importing)}>
          ＋ 기존 증빙 등록
        </button>
      </section>
      <Message error>{error}</Message>
      <Message>{message}</Message>
      {importing && (
        <section className={ws.card} style={{ marginBottom: 22 }}>
          <h2>기존 보육일지·관찰기록·영유아 평가 등록</h2>
          <p className={ws.hint}>
            원문을 읽은 후 문서 종류, 반·아동과 실제 작성 기간을 지정해주세요.
          </p>
          <div className={ws.row}>
            <label className={ws.field}>
              문서 종류
              <select
                value={kind}
                onChange={(e) => {
                  setKind(e.target.value as DocumentKind);
                  setReviewed(false);
                }}
              >
                {Object.entries(DOCUMENT_KINDS).map(([key, value]) => (
                  <option value={key} key={key}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
            <label className={ws.field}>
              반
              <select
                value={classId}
                onChange={(e) => {
                  setClassId(e.target.value);
                  setChildId("");
                  setReviewed(false);
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
                value={childId}
                onChange={(e) => {
                  setChildId(e.target.value);
                  setReviewed(false);
                }}
              >
                <option value="">반 전체</option>
                {classes
                  .find((c) => c.id === classId)
                  ?.children.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
              </select>
            </label>
          </div>
          <div className={ws.row} style={{ marginTop: 16 }}>
            <label className={ws.field}>
              시작일
              <input
                type="date"
                value={start}
                onChange={(e) => {
                  setStart(e.target.value);
                  setReviewed(false);
                }}
              />
            </label>
            <label className={ws.field}>
              종료일
              <input
                type="date"
                value={end}
                onChange={(e) => {
                  setEnd(e.target.value);
                  setReviewed(false);
                }}
              />
            </label>
          </div>
          <label className={ws.field} style={{ marginTop: 16 }}>
            증빙 파일 · PDF / DOCX / TXT / MD / CSV · 5MB
            <input
              type="file"
              disabled={busy}
              accept=".pdf,.docx,.txt,.md,.csv"
              onChange={(e) => {
                void upload(e.target.files?.[0]);
                e.target.value = "";
              }}
            />
          </label>
          {fileText && <div className={ws.preview}>{fileText}</div>}
          <label className={ws.check}>
            <input
              type="checkbox"
              checked={reviewed}
              onChange={(e) => setReviewed(e.target.checked)}
            />
            원문과 등록할 아동·반·기간이 일치하는지 확인했어요.
          </label>
          <button
            className={ws.primary}
            disabled={busy || !fileText || !reviewed}
            onClick={registerEvidence}
          >
            {busy ? "문서를 읽는 중…" : "증빙 등록"}
          </button>
        </section>
      )}
      <div className={ws.grid}>
        <aside className={ws.stack}>
          <section className={ws.card}>
            <h2>점검할 문서</h2>
            <label className={ws.field}>
              문서 선택
              <select
                disabled={checking}
                value={active}
                onChange={(e) => {
                  setActive(e.target.value);
                  setChecked(false);
                }}
              >
                <option value="">문서 선택</option>
                {data.documents.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.title}
                  </option>
                ))}
              </select>
            </label>
            <button
              className={ws.primary}
              style={{ marginTop: 16 }}
              disabled={!doc}
              onClick={() => setChecked(true)}
            >
              항목·증빙 점검하기
            </button>
            <p className={ws.hint}>
              확정 문서를 증빙으로 대조해요. 작성 기간이 일부 겹치는 자료도 표시하며, 기간 전체 충족
              여부는 별도 확인이 필요해요.
            </p>
          </section>
          <section className={ws.card}>
            <h2>평가 요구 항목 등록</h2>
            <p className={ws.hint}>
              매뉴얼에서 기관에 적용되는 요구사항과 찾아볼 단어를 직접 등록해주세요.
            </p>
            <a href={MANUAL} target="_blank" rel="noreferrer" className={ws.link}>
              2026년 평가 매뉴얼 안내 ↗
            </a>
            <form
              className={ws.form}
              style={{ marginTop: 18 }}
              onSubmit={(e) => {
                e.preventDefault();
                if (!label.trim() || !terms.split(",").some((t) => t.trim()) || !source.trim())
                  return;
                if (
                  save((prev) => ({
                    ...prev,
                    criteria: [
                      ...prev.criteria,
                      {
                        id: crypto.randomUUID(),
                        label: label.trim(),
                        terms: terms.trim(),
                        source: source.trim(),
                      },
                    ],
                  }))
                ) {
                  setLabel("");
                  setTerms("");
                  setSource("");
                  setChecked(false);
                }
              }}
            >
              <label className={ws.field}>
                확인할 요구사항
                <input
                  required
                  maxLength={300}
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                  placeholder="매뉴얼의 확인할 항목을 입력"
                />
              </label>
              <label className={ws.field}>
                관련 단어 · 쉼표로 구분
                <input
                  required
                  maxLength={200}
                  value={terms}
                  onChange={(e) => setTerms(e.target.value)}
                  placeholder="예: 놀이, 지원, 관찰"
                />
              </label>
              <label className={ws.field}>
                기준 출처 / 페이지
                <input
                  required
                  maxLength={300}
                  value={source}
                  onChange={(e) => setSource(e.target.value)}
                  placeholder="매뉴얼명, 적용 연도, 페이지"
                />
              </label>
              <button className={ws.secondary}>점검 항목 추가</button>
            </form>
            <p className={ws.hint}>{data.criteria.length}개의 점검 항목이 등록되어 있어요.</p>
          </section>
        </aside>
        <section className={ws.stack}>
          {!checked || !doc || !evidence ? (
            <Empty title="문서를 선택하고 점검을 시작해주세요">
              원문 근거를 찾아 보여드리고, 부족한 증빙을 함께 확인합니다.
            </Empty>
          ) : (
            <>
              <div className={ws.pills}>
                {[
                  ["items", "평가 항목"],
                  ["evidence", "증빙서류 대조"],
                  ["consistency", "기간·내용 정합성"],
                ].map(([id, label]) => (
                  <button
                    key={id}
                    className={tab === id ? ws.selected : undefined}
                    onClick={() => setTab(id)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <section className={ws.card}>
                <div className={ws.between}>
                  <h2>{doc.title}</h2>
                  <span className={ws.badge}>
                    {doc.status === "confirmed" ? "확정 / 등록 문서" : "초안 · 검토 필요"}
                  </span>
                </div>
                <p className={ws.muted}>
                  {doc.className} {doc.childName} · {doc.start} ~ {doc.end}
                </p>
                <p className={ws.hint}>
                  문서 사전점검입니다. 단어 발견은 항목 충족을 의미하지 않으며, 공식 평가 판정은
                  제공하지 않습니다.
                </p>
              </section>
              <section className={ws.card}>
                <h3>AI 내용 대조</h3>
                <p className={ws.hint}>
                  {available
                    ? "단어 검색을 넘어 요구사항과 문서 내용, 여러 증빙 사이의 서술을 대조해요."
                    : "AI 연결 후 의미 단위의 요구사항 점검과 증빙 간 내용 대조를 사용할 수 있어요."}
                </p>
                <div className={ws.actions}>
                  <button
                    className={ws.secondary}
                    disabled={!available || checking || !data.criteria.length}
                    onClick={() => semanticCheck(false)}
                  >
                    {checking ? "대조 중…" : "평가 항목 내용 점검"}
                  </button>
                  <button
                    className={ws.secondary}
                    disabled={!available || checking || !evidence.matches.length}
                    onClick={() => semanticCheck(true)}
                  >
                    증빙 간 내용 정합성 검사
                  </button>
                </div>
                {aiResults?.map((r, i) => (
                  <div key={i} className={ws.quote}>
                    <b>
                      {data.criteria.find((c) => c.id === r.criterionId)?.label} · {r.verdict}
                    </b>
                    <p>{r.reason}</p>
                    {r.quote && <p>원문 근거: {r.quote}</p>}
                  </div>
                ))}
                {crossResults && (
                  <>
                    <Message error={crossResults.issues.length > 0}>
                      {crossResults.issues.length
                        ? `${crossResults.issues.length}개의 확인할 차이가 있어요.`
                        : "AI가 검증 가능한 상충 근거를 찾지 못했어요. 교사가 원문을 최종 확인해주세요."}
                    </Message>
                    {crossResults.issues.map((r, i) => (
                      <div className={ws.quote} key={i}>
                        <b>{data.documents.find((d) => d.id === r.documentId)?.title}</b>
                        <p>{r.quote}</p>
                        <p>{r.reason}</p>
                      </div>
                    ))}
                    <p className={ws.hint}>{crossResults.notes.join(" ")}</p>
                  </>
                )}
              </section>
              {tab === "items" &&
                (!checks.length ? (
                  <Empty title="확인할 평가 항목을 등록해주세요">
                    공식 매뉴얼의 적용 기준과 페이지를 기록하면 문서에서 관련 내용을 찾아요.
                  </Empty>
                ) : (
                  checks.map((c) => (
                    <article className={ws.card} key={c.criterion.id}>
                      <span className={ws.badge}>
                        {c.matches.length
                          ? "관련 내용 발견 · 확인 필요"
                          : "근거 미발견 · 보완 필요"}
                      </span>
                      <h3 style={{ marginTop: 15 }}>{c.criterion.label}</h3>
                      <p className={ws.muted}>기준: {c.criterion.source}</p>
                      {c.matches.map((s, i) => (
                        <blockquote className={ws.quote} key={i}>
                          <b>{s.heading}</b>
                          <br />
                          {s.body}
                        </blockquote>
                      ))}
                      {!c.matches.length && (
                        <p>
                          관련 단어를 찾지 못했어요. 원문에서 충족 여부를 직접 확인하고 필요한
                          내용을 보완해주세요.
                        </p>
                      )}
                    </article>
                  ))
                ))}
              {tab === "evidence" && (
                <>
                  {evidence.required.map((r) => (
                    <article className={ws.card} key={r.kind}>
                      <div className={ws.between}>
                        <h3>{DOCUMENT_KINDS[r.kind]}</h3>
                        <span className={ws.badge}>
                          {r.documents.length ? `${r.documents.length}건 발견` : "자료 없음"}
                        </span>
                      </div>
                      {r.documents.length ? (
                        r.documents.map((d) => (
                          <div className={ws.quote} key={d.id}>
                            <b>{d.title}</b>
                            <br />
                            {d.start} ~ {d.end}
                            <br />
                            <small>
                              대상: {d.childName || "반 전체 · 개별 아동 내용 확인 필요"}
                            </small>
                          </div>
                        ))
                      ) : (
                        <p className={ws.muted}>
                          같은 반·아동과 기간에 해당하는 확정 증빙이 없어요. 문서를 작성·확정하거나
                          기존 증빙을 등록해주세요.
                        </p>
                      )}
                    </article>
                  ))}
                  <Link href="/documents" className={ws.secondary}>
                    문서 보관함에서 보완 →
                  </Link>
                </>
              )}
              {tab === "consistency" && (
                <>
                  <article className={ws.card}>
                    <h3>원본과 내용 일치</h3>
                    {evidence.linked.length ? (
                      evidence.linked.map((r, i) => (
                        <div className={ws.quote} key={r.source.id}>
                          <b>
                            근거 {i + 1} · {r.source.date} · {r.state}
                          </b>
                          <br />
                          {r.source.text}
                        </div>
                      ))
                    ) : (
                      <p>
                        연결된 원본 관찰이 없어요. 등록 문서는 원문과 아동·기간을 직접 대조해주세요.
                      </p>
                    )}
                  </article>
                  <article className={ws.card}>
                    <h3>작성 기간 대조</h3>
                    {evidence.matches.length ? (
                      evidence.matches.map((d) => (
                        <p key={d.id}>
                          {d.title} · {d.start} ~ {d.end}{" "}
                          <span className={ws.badge}>
                            {d.start <= doc.start && d.end >= doc.end
                              ? "대상 기간 포함"
                              : "기간 일부 중첩"}
                          </span>
                        </p>
                      ))
                    ) : (
                      <p>기간이 겹치는 확정 문서가 없어요.</p>
                    )}
                    <p className={ws.hint}>
                      날짜가 겹쳐도 실제 내용의 일관성을 보장하지 않아요. 관찰 대상과 활동,
                      해석·지원의 연결을 원문으로 확인해주세요.
                    </p>
                  </article>
                </>
              )}
              <button className={ws.secondary} onClick={exportReport}>
                점검 결과 내려받기
              </button>
            </>
          )}
        </section>
      </div>
    </WorkspacePage>
  );
}
