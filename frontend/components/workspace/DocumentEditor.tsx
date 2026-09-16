"use client";
import { useEffect, useRef, useState } from "react";
import {
  DOCUMENT_KINDS,
  downloadText,
  validateDocument,
  type SavedDocument,
} from "@/lib/workspace/model";
import { requestAI } from "@/lib/workspace/ai-client";
import { AIHint, Message, useAIStatus, ws } from "./WorkspaceUI";

import { API_STORAGE_CONTEXT } from "@/lib/api/storage-context";
import { getAnnualPlan, patchAnnualMonth, confirmAnnualPlan } from "@/lib/api/plans";
import type { AnnualPlan } from "@/lib/api/types";

export default function DocumentEditor({
  initial,
  onSave,
}: {
  initial: SavedDocument;
  onSave: (doc: SavedDocument, expected: SavedDocument) => boolean;
}) {
  const [baseline, setBaseline] = useState(initial);
  const [doc, setDoc] = useState(initial);
  const [checks, setChecks] = useState([false, false, false]);
  const [issues, setIssues] = useState<string[] | null>(null);
  const [verified, setVerified] = useState(false);
  const annualPlanId =
    initial.annualApiSource === API_STORAGE_CONTEXT ? initial.annualPlanId : undefined;
  // 연간계획안을 불러와야 하는 문서라면 처음부터 로딩 상태로 시작한다(effect에서 setBusy(true) 하지 않기 위함).
  const [busy, setBusy] = useState(!!annualPlanId);
  const [message, setMessage] = useState("");
  const available = useAIStatus();
  const annual = useRef<AnnualPlan | null>(null);
  const [annualError, setAnnualError] = useState(false);
  useEffect(() => {
    if (!annualPlanId) return;
    let live = true;
    getAnnualPlan(annualPlanId)
      .then((plan) => {
        if (!live) return;
        annual.current = plan;
        setDoc((prev) => ({
          ...prev,
          status: plan.status === "CONFIRMED" ? "confirmed" : "draft",
          sections: plan.months.map((m) => ({
            heading: m.month + "월 · " + m.theme,
            body: m.sub_themes.join("\n"),
            sourceIds: [],
          })),
        }));
      })
      .catch((e) => {
        if (live) {
          setAnnualError(true);
          setMessage(e instanceof Error ? e.message : "연간계획안을 불러오지 못했어요.");
        }
      })
      .finally(() => {
        if (live) setBusy(false);
      });
    return () => {
      live = false;
    };
  }, [annualPlanId]);
  const imported = doc.origin === "import";
  const stale = JSON.stringify(initial) !== JSON.stringify(baseline);
  const recordDocument =
    !imported && ["dailyLog", "weeklyLog", "observation", "assessment"].includes(doc.kind);
  const editable = doc.status !== "confirmed";
  function change(index: number, body: string) {
    setDoc((prev) => ({
      ...prev,
      status: "draft",
      sections: prev.sections.map((s, i) => (i === index ? { ...s, body } : s)),
    }));
    setChecks([false, false, false]);
    setVerified(false);
    setIssues(null);
  }
  async function verify() {
    if (busy || stale || available === null) return;
    const local = validateDocument(doc);
    setIssues(local);
    setMessage("");
    setVerified(false);
    if (local.length || !available || !recordDocument) return;
    setBusy(true);
    try {
      const result = await requestAI<{ issues: string[] }>("verify", doc);
      setIssues(result.issues);
      setVerified(!result.issues.length);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "검증에 실패했어요.");
    } finally {
      setBusy(false);
    }
  }
  async function persist(confirm: boolean) {
    if (stale || busy) return;
    const local = validateDocument(doc);
    if (
      confirm &&
      (available === null ||
        local.length ||
        !checks.every(Boolean) ||
        (available && recordDocument && !verified))
    ) {
      setIssues(local);
      setMessage("원본 대조와 교사 검토를 마쳐주세요. AI 연결 시 AI 검증 통과도 필요해요.");
      return;
    }
    if (annualPlanId) {
      if (annualError || !annual.current) {
        setMessage("서버 계획안을 불러온 뒤 저장해주세요.");
        return;
      }
      setBusy(true);
      try {
        for (let i = 0; i < doc.sections.length; i++) {
          const m = annual.current.months[i],
            section = doc.sections[i];
          if (m.sub_themes.join("\n") !== section.body) {
            const saved = await patchAnnualMonth(annualPlanId, m.month, {
              theme: m.theme,
              sub_themes: section.body.split("\n"),
            });
            annual.current.months[i] = saved;
          }
        }
        if (confirm) await confirmAnnualPlan(annualPlanId);
      } catch (e) {
        setMessage(e instanceof Error ? e.message : "서버 저장 실패");
        setBusy(false);
        return;
      }
      setBusy(false);
    }
    const next: SavedDocument = {
      ...doc,
      status: confirm ? "confirmed" : "draft",
      updatedAt: new Date().toISOString(),
      reviewNote: confirm
        ? imported
          ? "기존 증빙 원문·대상·기간 검토 완료 (공식 평가 판정 별도)"
          : `${available && verified ? "AI 검증 + " : ""}교사 사실·해석·지원 검토 완료`
        : "교사 검토 전",
    };
    if (onSave(next, baseline)) {
      setBaseline(next);
      setDoc(next);
      setMessage(confirm ? "검토한 문서를 확정했어요." : "작성 중인 초안을 저장했어요.");
    }
  }
  return (
    <section className={`${ws.card} ${ws.document}`}>
      {stale && (
        <>
          <Message error>
            원본 또는 문서가 다른 작업에서 변경되었어요. 현재 수정 내용은 복사해 보관한 뒤 최신
            문서를 불러와주세요.
          </Message>
          <button
            className={ws.secondary}
            onClick={() => {
              setBaseline(initial);
              setDoc(initial);
              setChecks([false, false, false]);
              setVerified(false);
              setIssues(null);
              setMessage("");
            }}
          >
            최신 문서 불러오기
          </button>
        </>
      )}
      <header>
        <div className={ws.between}>
          <span className={ws.badge}>
            {doc.status === "confirmed" ? "교사 확정" : "검토 중인 초안"}
          </span>
          <span className={ws.muted}>
            {doc.origin === "import"
              ? "등록 증빙"
              : doc.origin === "ai"
                ? "AI 초안"
                : doc.origin === "template"
                  ? "양식 기반"
                  : "교사 작성"}
          </span>
        </div>
        <h2>{doc.title}</h2>
        <p className={ws.muted}>
          {doc.className || "반 미지정"}
          {doc.childName && ` · ${doc.childName}`} · {doc.start} ~ {doc.end}
        </p>
        <p className={ws.muted}>{DOCUMENT_KINDS[doc.kind]}</p>
      </header>
      {doc.sections.map((section, index) => (
        <section key={`${section.heading}-${index}`}>
          <h3>{section.heading}</h3>
          {editable && !(recordDocument && section.heading === "사실") ? (
            <label className={ws.field}>
              <span className={ws.muted}>우리 반의 기록에 맞게 다듬어주세요</span>
              <textarea
                aria-label={`${section.heading} 내용`}
                maxLength={15000}
                disabled={busy || stale}
                value={section.body}
                onChange={(e) => change(index, e.target.value)}
              />
            </label>
          ) : (
            <p className={section.heading === "사실" ? ws.quote : undefined}>
              {section.body || "아직 작성하지 않았어요."}
            </p>
          )}
          {section.sourceIds.length > 0 && (
            <small className={ws.source}>
              근거:{" "}
              {section.sourceIds
                .map((id) => doc.sources.find((s) => s.id === id)?.date || "원본 없음")
                .join(" · ")}
            </small>
          )}
        </section>
      ))}
      {doc.sources.length > 0 && (
        <details>
          <summary className={ws.link}>원본 근거 {doc.sources.length}건 펼쳐보기</summary>
          {doc.sources.map((source, i) => (
            <blockquote key={source.id} className={ws.quote}>
              <small className={ws.muted}>
                근거 {i + 1} · {source.date}
              </small>
              <br />
              {source.text}
            </blockquote>
          ))}
        </details>
      )}
      {editable && (
        <>
          <hr className={ws.divider} />
          <h3>사실 · 해석 · 지원 검증</h3>
          <AIHint available={available} />
          <button className={ws.secondary} disabled={busy || stale} onClick={verify}>
            {busy
              ? "근거를 대조하고 있어요…"
              : available && recordDocument
                ? "AI 검증하기"
                : "기본 항목 검사"}
          </button>
          {issues && (
            <Message error={issues.length > 0}>
              {issues.length
                ? `반려 · 수정이 필요해요\n${issues.map((s) => `• ${s}`).join("\n")}`
                : available && verified
                  ? "AI 검증에서 문제를 찾지 못했어요. 교사 최종 검토를 진행해주세요."
                  : "형식·원문 대조를 통과했어요. 의미의 정확성은 교사가 확인해주세요."}
            </Message>
          )}
          {[
            "사실이 원본 기록과 일치하며, 관찰하지 않은 내용이 없는지 확인했어요.",
            "해석이 기록의 근거를 벗어나지 않으며, 성향·발달을 단정하지 않는지 확인했어요.",
            "지원에 구체적인 교사 행동과 방법이 있으며, 이후 제안임을 확인했어요.",
          ].map((label, index) => (
            <label className={ws.check} key={label}>
              <input
                type="checkbox"
                checked={checks[index]}
                disabled={busy || stale}
                onChange={(e) =>
                  setChecks((prev) => prev.map((v, i) => (i === index ? e.target.checked : v)))
                }
              />
              {recordDocument
                ? label
                : imported
                  ? [
                      "등록한 증빙의 원문 내용이 실제 문서와 일치하는지 확인했어요.",
                      "문서 종류·반·아동·작성 기간이 일치하는지 확인했어요.",
                      "이 자료의 등록이 공식 평가 통과를 의미하지 않음을 확인했어요.",
                    ][index]
                  : [
                      "입력한 연령과 기간에 맞는 계획인지 확인했어요.",
                      "계획한 활동이 실제 관찰 사실로 표현되지 않았는지 확인했어요.",
                      "안전, 놀이 자료와 교사 지원 내용을 확인했어요.",
                    ][index]}
            </label>
          ))}
        </>
      )}
      <Message>{message}</Message>
      <div className={ws.actions}>
        {editable ? (
          <>
            <button
              className={ws.secondary}
              disabled={busy || stale}
              onClick={() => persist(false)}
            >
              초안 저장
            </button>
            <button
              className={ws.primary}
              disabled={busy || stale || available === null || !checks.every(Boolean)}
              onClick={() => persist(true)}
            >
              검토 완료 · 문서 확정
            </button>
          </>
        ) : (
          !annualPlanId && (
            <button
              className={ws.secondary}
              onClick={() => {
                setDoc({ ...doc, status: "draft" });
                setChecks([false, false, false]);
                setVerified(false);
                setMessage("수정 후 다시 검토하고 저장해주세요.");
              }}
            >
              문서 수정
            </button>
          )
        )}
        <button
          className={ws.secondary}
          disabled={stale}
          onClick={() =>
            downloadText(
              doc.title,
              `${doc.title}\n${doc.className} ${doc.childName}\n${doc.start} ~ ${doc.end}\n상태: ${doc.status === "confirmed" ? "교사 확정" : "검토 전 초안"}\n\n${doc.sections.map((s) => `${s.heading}\n${s.body}`).join("\n\n")}\n\n${doc.reviewNote}`,
            )
          }
        >
          텍스트 내려받기
        </button>
      </div>
    </section>
  );
}
