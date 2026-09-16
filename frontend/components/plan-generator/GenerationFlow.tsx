"use client";

import { useEffect, useRef, useState } from "react";
import {
  AGE_LABEL,
  GENERATION_STEPS,
  PLAN_TYPE_LABEL,
  type AgeGroup,
  type PeriodState,
  type PlanType,
} from "@/lib/plan-generator/types";
import { formatDateLabel } from "@/lib/plan-generator/date";
import styles from "./GenerationFlow.module.css";
import { planPeriod, type PlanContent, type PlanRow } from "@/lib/workspace/plans";
import { updateWorkspace } from "@/lib/workspace/store";
import {
  assertDocumentUnchanged,
  invalidateDependents,
  type SavedDocument,
} from "@/lib/workspace/model";
import Link from "next/link";
import { API_STORAGE_CONTEXT } from "@/lib/api/storage-context";
import { patchAnnualMonth, confirmAnnualPlan } from "@/lib/api/plans";

type Request = {
  age: AgeGroup;
  ageLabel?: string;
  selectedTypes: PlanType[];
  period: PeriodState;
  memo: string;
};

function periodLabel(type: PlanType, period: PeriodState) {
  return type === "annual"
    ? `${period.annual.year}학년도`
    : type === "monthly"
      ? `${period.annual.year}년 ${period.monthly.month}월`
      : type === "weekly"
        ? `${period.annual.year}년 ${period.weekly.month}월 ${period.weekly.week}주차`
        : formatDateLabel(period.daily.date);
}

function Sprout({ complete = false }: { complete?: boolean }) {
  return (
    <div className={`${styles.sprout} ${complete ? styles.complete : ""}`} aria-hidden="true">
      <svg width="66" height="66" viewBox="0 0 66 66" fill="none">
        <path d="M33 49V28" stroke="var(--pg-success)" strokeWidth="3" strokeLinecap="round" />
        <path d="M33 34C17 36 12 26 15 17C29 16 35 23 33 34Z" fill="var(--pg-sage)" />
        <path d="M33 28C32 14 43 10 53 13C52 25 45 31 33 28Z" fill="var(--pg-sage-ink)" />
        <path d="M23 51H44" stroke="var(--pg-success)" strokeWidth="3" strokeLinecap="round" />
      </svg>
      {complete && <span className={styles.check}>✓</span>}
    </div>
  );
}

export default function GenerationFlow({
  phase,
  stepIndex,
  request,
  contents,
  classId,
  className,
  onBack,
  onRetry,
  initialConfirmed = false,
}: {
  initialConfirmed?: boolean;
  phase: "generating" | "done";
  stepIndex: number;
  request: Request;
  contents: Partial<Record<PlanType, PlanContent>>;
  classId: string;
  className: string;
  onBack: () => void;
  onRetry: () => void;
}) {
  const [active, setActive] = useState<PlanType>(request.selectedTypes[0]);
  const [drafts, setDrafts] = useState<Record<PlanType, PlanRow[]>>(() => ({
    annual: contents.annual?.rows || [],
    monthly: contents.monthly?.rows || [],
    weekly: contents.weekly?.rows || [],
    daily: contents.daily?.rows || [],
  }));
  const savedDocuments = useRef<Partial<Record<PlanType, SavedDocument>>>({});
  const savingLock = useRef(false);
  const [saving, setSaving] = useState(false);
  const [savingRows, setSavingRows] = useState<number[]>([]);
  const [rowErrors, setRowErrors] = useState<Record<number, string>>({});
  const [confirmed, setConfirmed] = useState(initialConfirmed);
  const [confirming, setConfirming] = useState(false);
  const annualBaseline = useRef(contents.annual?.rows || []);
  async function saveAnnualRows() {
    const id = contents.annual?.annualPlanId;
    if (!id) return true;
    if (savingLock.current) return false;
    savingLock.current = true;
    setSaving(true);
    let success = true;
    try {
      for (let i = 0; i < drafts.annual.length; i++) {
        const row = drafts.annual[i];
        if (JSON.stringify(row) === JSON.stringify(annualBaseline.current[i])) continue;
        setSavingRows((prev) => [...prev, i]);
        try {
          const result = await patchAnnualMonth(id, parseInt(row.label), {
            theme: row.title,
            sub_themes: row.detail.split("\n"),
          });
          const saved = {
            label: result.month + "월",
            title: result.theme,
            detail: result.sub_themes.join("\n"),
          };
          annualBaseline.current = annualBaseline.current.map((r, j) => (j === i ? saved : r));
          setRowErrors((prev) => ({ ...prev, [i]: "" }));
        } catch (e) {
          success = false;
          setRowErrors((prev) => ({
            ...prev,
            [i]: e instanceof Error ? e.message : "월 저장 실패",
          }));
          // 실패한 입력은 그대로 남겨 재시도할 수 있게 한다.
        } finally {
          setSavingRows((prev) => prev.filter((j) => j !== i));
        }
      }
      return success;
    } finally {
      savingLock.current = false;
      setSaving(false);
    }
  }
  async function confirmAnnual() {
    if (confirming) return;
    setConfirming(true);
    try {
      if (!(await saveAnnualRows())) return;
      await confirmAnnualPlan(contents.annual!.annualPlanId!);
      setConfirmed(true);
      setEditing(false);
      setNotice("연간계획안이 확정됐어요.");
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "확정하지 못했어요.");
    } finally {
      setConfirming(false);
    }
  }
  const [editing, setEditing] = useState(false);
  const [notice, setNotice] = useState("");
  const heading = useRef<HTMLHeadingElement>(null);
  const done = phase === "done";
  const progress = Math.round((stepIndex / GENERATION_STEPS.length) * 100);
  const title = `${periodLabel(active, request.period)} ${PLAN_TYPE_LABEL[active]} 보육계획안`;
  const origin = contents[active]?.origin || "template";
  useEffect(() => {
    heading.current?.focus({ preventScroll: true });
  }, [phase]);

  function download() {
    const text = [
      title,
      `${request.ageLabel || AGE_LABEL[request.age]}${className ? ` · ${className}` : ""}`,
      "검토 전 초안 · 우리 반 상황에 맞게 검토해주세요.",
      "",
      ...drafts[active].map((row) => `${row.label} · ${row.title}\n${row.detail}`),
      "",
      `추가 요청사항: ${request.memo || "없음"}`,
    ].join("\n");
    const url = URL.createObjectURL(
      new Blob(["\uFEFF", text], { type: "text/plain;charset=utf-8" }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${title}.txt`;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setNotice("현재 계획안을 텍스트 파일로 내려받았어요.");
  }
  async function saveDocument() {
    if (active === "annual" && !(await saveAnnualRows())) return;
    if (!classId) {
      setNotice(
        "반 설정에서 담당 반을 등록한 후 다시 생성하면 보관함에 저장할 수 있어요. 현재 초안은 내려받을 수 있어요.",
      );
      return;
    }
    try {
      const now = new Date().toISOString();
      const previous = savedDocuments.current[active];
      const id = previous?.id || crypto.randomUUID();
      const doc: SavedDocument = {
        id,
        title,
        ...(active === "annual" && contents.annual?.annualPlanId
          ? { annualPlanId: contents.annual.annualPlanId, annualApiSource: API_STORAGE_CONTEXT }
          : {}),
        kind: active,
        classId,
        className,
        childId: "",
        childName: "",
        ...planPeriod(active, request.period),
        sources: [],
        sections: drafts[active].map((r) => ({
          heading: `${r.label} · ${r.title}`,
          body: r.detail,
          sourceIds: [],
        })),
        status: active === "annual" && confirmed ? "confirmed" : "draft",
        origin,
        createdAt: previous?.createdAt || now,
        updatedAt: now,
        reviewNote: "교사 검토 전",
      };
      updateWorkspace((prev) => {
        if (previous)
          assertDocumentUnchanged(
            prev.documents.find((d) => d.id === id),
            previous,
          );
        return {
          ...prev,
          documents: invalidateDependents([doc, ...prev.documents.filter((d) => d.id !== id)], id),
        };
      });
      savedDocuments.current[active] = doc;
      setNotice("문서 보관함에 저장했어요. 검토 후 문서를 확정할 수 있어요.");
    } catch (error) {
      setNotice(
        error instanceof Error
          ? error.message
          : "저장하지 못했어요. 브라우저 저장 공간을 확인하거나 초안을 내려받아주세요.",
      );
    }
  }

  return (
    <main className={styles.flow}>
      <div className={styles.topline}>
        <button className={styles.back} disabled={saving || confirming} onClick={onBack}>
          ← {done ? "조건 수정하기" : "생성 취소"}
        </button>
        <ol className={styles.steps} aria-label="계획안 생성 단계">
          {["조건 입력", "계획안 생성", "완료"].map((label, i) => (
            <li
              key={label}
              aria-current={(done ? i === 2 : i === 1) ? "step" : undefined}
              className={i <= (done ? 2 : 1) ? styles.reached : ""}
            >
              <span>{i < (done ? 2 : 1) ? "✓" : `0${i + 1}`}</span>
              {label}
            </li>
          ))}
        </ol>
      </div>

      {!done ? (
        <div className={styles.loadingLayout}>
          <section className={styles.loadingCard} aria-busy="true">
            <span className={styles.eyebrow}>작은 아이디어가, 하루의 놀이로</span>
            <Sprout />
            <h2 ref={heading} tabIndex={-1}>
              우리 반에 맞는 계획안을
              <br />
              차근차근 만들고 있어요
            </h2>
            <p className={styles.subtitle}>
              선생님의 준비 시간은 줄이고,
              <br />
              아이들과 함께할 시간은 더할게요.
            </p>
            <div className={styles.progressArea}>
              <div className={styles.progressLabel}>
                <span role="status">
                  {GENERATION_STEPS[Math.min(stepIndex, GENERATION_STEPS.length - 1)]}
                </span>
                <b>작성 중</b>
              </div>
              <div className={styles.progress} role="progressbar" aria-label="계획안 작성 중">
                <span style={{ width: `${progress}%` }} />
              </div>
              <ul className={styles.checklist}>
                {GENERATION_STEPS.map((step, i) => (
                  <li key={step} className={i === stepIndex ? styles.currentStep : ""}>
                    <span className={i < stepIndex ? styles.checked : styles.stepDot}>
                      {i < stepIndex ? "✓" : i + 1}
                    </span>
                    {step}
                    <small>{i < stepIndex ? "완료" : i === stepIndex ? "진행 중" : "대기"}</small>
                  </li>
                ))}
              </ul>
            </div>
            <p className={styles.footnote}>
              선택한 계획안을 준비하고 있어요. 완료되면 자동으로 보여드려요.
            </p>
          </section>
          <aside className={styles.summary}>
            <span className={styles.eyebrow}>이번 계획안</span>
            <h3>선생님이 선택한 내용</h3>
            <dl>
              <div>
                <dt>대상 연령</dt>
                <dd>
                  {request.ageLabel || AGE_LABEL[request.age]}
                  {className && ` · ${className}`}
                </dd>
              </div>
              <div>
                <dt>생성할 계획안</dt>
                <dd className={styles.chips}>
                  {request.selectedTypes.map((t) => (
                    <span key={t}>{PLAN_TYPE_LABEL[t]}</span>
                  ))}
                </dd>
              </div>
              <div>
                <dt>선택한 기간</dt>
                <dd>
                  {request.selectedTypes.map((t) => (
                    <p key={t}>
                      {PLAN_TYPE_LABEL[t]} · {periodLabel(t, request.period)}
                    </p>
                  ))}
                </dd>
              </div>
            </dl>
            <div className={styles.memo}>
              <b>추가 요청사항</b>
              <p>{request.memo || "입력한 추가 요청사항이 없어요."}</p>
            </div>
            <div className={styles.tip}>
              <span>🌱</span>
              <p>완성된 초안은 우리 반의 놀이 흐름에 맞춰 자유롭게 수정할 수 있어요.</p>
            </div>
          </aside>
        </div>
      ) : (
        <>
          <section className={styles.successBanner}>
            <Sprout complete />
            <div>
              <span className={styles.eyebrow}>선생님의 다음 하루가 준비됐어요</span>
              <h2 ref={heading} tabIndex={-1}>
                계획안 초안이 완성됐어요
              </h2>
              <p>
                {request.ageLabel || AGE_LABEL[request.age]} · {request.selectedTypes.length}개의
                계획안을 확인해보세요.
              </p>
            </div>
            <button className={styles.secondary} disabled={saving || confirming} onClick={onRetry}>
              ↻ 다시 생성하기
            </button>
          </section>
          <div className={styles.resultLayout}>
            <aside className={styles.resultSidebar}>
              <span className={styles.eyebrow}>
                생성된 계획안 <b>{request.selectedTypes.length}</b>
              </span>
              <div className={styles.tabs} role="tablist" aria-label="생성된 계획안">
                {request.selectedTypes.map((t) => (
                  <button
                    key={t}
                    id={`tab-${t}`}
                    role="tab"
                    disabled={saving || confirming}
                    aria-selected={active === t}
                    aria-controls="plan-document"
                    className={active === t ? styles.activeTab : ""}
                    onClick={() => {
                      setActive(t);
                      setEditing(false);
                      setNotice("");
                    }}
                  >
                    <span className={styles.fileIcon}>▤</span>
                    <span>
                      <b>{PLAN_TYPE_LABEL[t]} 보육계획안</b>
                      <small>{periodLabel(t, request.period)}</small>
                    </span>
                    <span className={styles.tabCheck}>✓</span>
                  </button>
                ))}
              </div>
              <div className={styles.tip}>
                <span>🌱</span>
                <p>좋은 계획안은 아이들과 함께 완성돼요. 반의 상황에 맞게 내용을 다듬어주세요.</p>
              </div>
            </aside>
            <section className={styles.documentWrap}>
              <div className={styles.toolbar}>
                <span className={styles.draftBadge}>
                  {origin === "ai" ? "AI 초안" : "기본 양식 초안"}
                </span>
                <div>
                  <button
                    className={styles.secondary}
                    disabled={(active === "annual" && confirmed) || saving || confirming}
                    onClick={async () => {
                      if (editing && active === "annual" && !(await saveAnnualRows())) return;
                      setEditing(!editing);
                      setNotice(editing ? "수정한 내용을 저장했어요." : "");
                    }}
                  >
                    {editing ? "✓ 수정 완료" : "내용 수정"}
                  </button>
                  <button
                    className={styles.primary}
                    disabled={saving || confirming}
                    onClick={saveDocument}
                  >
                    보관함 저장
                  </button>
                  {active === "annual" && contents.annual?.annualPlanId && (
                    <button
                      className={styles.secondary}
                      disabled={confirmed || confirming || saving}
                      onClick={confirmAnnual}
                    >
                      {confirmed ? "확정됨" : confirming ? "확정 중…" : "연간계획안 확정"}
                    </button>
                  )}
                  <button className={styles.secondary} onClick={download}>
                    ↓ 내려받기
                  </button>
                </div>
              </div>
              <article
                id="plan-document"
                role="tabpanel"
                aria-labelledby={`tab-${active}`}
                className={styles.document}
              >
                <div className={styles.documentHeading}>
                  <span className={styles.eyebrow}>쓱싹요정 · 우리 반 놀이 기록의 시작</span>
                  <h3>{title}</h3>
                  <p>
                    {className || "우리 반"}
                    <span>·</span>
                    {request.ageLabel || AGE_LABEL[request.age]}
                    <span>·</span>
                    {periodLabel(active, request.period)}
                  </p>
                </div>
                <div className={styles.theme}>
                  <span>계획안 작성 기준</span>
                  <b>{request.ageLabel || AGE_LABEL[request.age]} · 우리 반의 놀이 흐름</b>
                  <p>활동은 앞으로 실행할 제안입니다. 실제 관찰 기록과 구분하여 사용해주세요.</p>
                </div>
                <div className={styles.sectionLabel}>
                  <h4>
                    {active === "annual"
                      ? "월별 놀이 계획"
                      : active === "monthly"
                        ? "주차별 놀이 계획"
                        : active === "weekly"
                          ? "요일별 놀이 계획"
                          : "하루 일과와 놀이"}
                  </h4>
                  <span>{editing ? "내용을 직접 수정해보세요" : "놀이 중심 · 유아 중심"}</span>
                </div>
                <div className={styles.rows}>
                  {drafts[active].map((row, index) => (
                    <div
                      key={row.label}
                      className={styles.row}
                      aria-busy={active === "annual" && savingRows.includes(index)}
                    >
                      <span className={styles.rowLabel}>{row.label}</span>
                      <div>
                        {editing ? (
                          <>
                            <input
                              disabled={saving || confirming}
                              aria-label={`${row.label} 활동명`}
                              value={row.title}
                              onChange={(event) =>
                                setDrafts((prev) => ({
                                  ...prev,
                                  [active]: prev[active].map((r, i) =>
                                    i === index ? { ...r, title: event.target.value } : r,
                                  ),
                                }))
                              }
                            />
                            <textarea
                              disabled={saving || confirming}
                              aria-label={`${row.label} 활동 내용`}
                              value={row.detail}
                              onChange={(event) =>
                                setDrafts((prev) => ({
                                  ...prev,
                                  [active]: prev[active].map((r, i) =>
                                    i === index ? { ...r, detail: event.target.value } : r,
                                  ),
                                }))
                              }
                            />
                          </>
                        ) : (
                          <>
                            <h5>{row.title}</h5>
                            <p>{row.detail}</p>
                          </>
                        )}
                        {active === "annual" && rowErrors[index] && (
                          <p role="alert">{rowErrors[index]}</p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
                <div className={styles.teacherNote}>
                  <b>선생님 메모</b>
                  <p>
                    {request.memo ||
                      "아이들의 흥미와 날씨, 하루의 컨디션에 따라 활동 순서와 시간을 조정해주세요."}
                  </p>
                </div>
                <footer className={styles.documentFooter}>
                  <span>쓱싹요정</span>
                  <span>아이들의 매일이 조금 더 자라도록</span>
                </footer>
              </article>
              <p className={styles.disclaimer}>
                {contents[active]?.notes.join(" ") ||
                  "우리 반의 상황과 안전을 검토한 후 사용해주세요."}{" "}
                <Link href="/documents">문서 보관함으로 →</Link>
              </p>
              <p className={styles.notice} role="status">
                {notice}
              </p>
            </section>
          </div>
        </>
      )}
    </main>
  );
}
