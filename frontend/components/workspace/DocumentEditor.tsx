"use client";
import { useEffect, useRef, useState } from "react";
import {
  DOCUMENT_KINDS,
  downloadText,
  validateDocument,
  type SavedDocument,
  type Section,
} from "@/lib/workspace/model";
import { requestAI } from "@/lib/workspace/ai-client";
import { AIHint, Message, useAIStatus, ws } from "./WorkspaceUI";
import { serverIssues } from "./document-selection";
import { isStaleWrite } from "@/lib/api/documents";
import { withoutChildMetadata } from "@/lib/privacy/browser-storage";

import { API_STORAGE_CONTEXT } from "@/lib/api/storage-context";
import { getAnnualPlan, putAnnualMonth, confirmAnnualPlan } from "@/lib/api/plans";
import type { AnnualPlan } from "@/lib/api/types";

/** `server` 가 있으면 §11 서버 문서다 — 저장·확정·삭제를 서버가 맡는다. */
export interface ServerDocumentActions {
  stale: boolean;
  /** 저장·확정·삭제·최신 조회 중 하나라도 진행 중. 요청은 서로 섞이면 안 된다. */
  pending: boolean;
  /** 최신 조회 중 다른 문서로 옮겼으면 null 이며 현재 편집기를 바꾸지 않는다. */
  reload: () => Promise<SavedDocument | null>;
  save: (sections: Section[], reviewNote: string) => Promise<SavedDocument>;
  /** 저장과 확정은 한 작업이다 — 대상 문서가 중간에 바뀌지 않는다. */
  saveAndConfirm: (sections: Section[], reviewNote: string) => Promise<SavedDocument>;
  /** 확정을 되돌린다. 근거를 다시 반영하지는 않는다 — 교사가 따로 누른다. */
  unconfirm: () => Promise<SavedDocument>;
  /** 바뀐 근거로 `사실` 을 다시 받는다. 초안이면서 stale 일 때만 부른다. */
  refresh: () => Promise<SavedDocument>;
  remove: () => Promise<void>;
}

export default function DocumentEditor({
  initial,
  onSave,
  server,
}: {
  initial: SavedDocument;
  onSave: (doc: SavedDocument, expected: SavedDocument) => boolean;
  server?: ServerDocumentActions;
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
  const [staleWrite, setStaleWrite] = useState(false);
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
  // 서버 문서의 동시성 기준은 updated_at 이다 — 로컬 스냅샷 비교를 겹쳐 걸지 않는다.
  const stale = !server && JSON.stringify(initial) !== JSON.stringify(baseline);
  const recordDocument =
    !imported && ["dailyLog", "weeklyLog", "observation", "assessment"].includes(doc.kind);
  const editable = doc.status !== "confirmed";
  // 서버 요청 중에는 입력·저장·확정·삭제가 서로 끼어들지 못한다.
  const working = busy || !!server?.pending;
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
    if (working || stale || available === null) return;
    const local = server ? serverIssues(doc) : validateDocument(doc);
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
    if (stale || working) return;
    if (server) {
      // AI 검증은 서버 확정 조건이 아니다 (§11) — 교사 확인 3개와 서버 게이트가 기준이다.
      const blocking = serverIssues(doc);
      if (confirm && (blocking.length || !checks.every(Boolean))) {
        setIssues(blocking);
        setMessage("원본 대조와 교사 검토를 마쳐주세요.");
        return;
      }
      if (confirm && server.stale) {
        setMessage("근거 기록이 바뀌었어요. 다시 검토한 뒤 확정해주세요.");
        return;
      }
      setBusy(true);
      setMessage("");
      try {
        const note = confirm ? "교사 사실·해석·지원 검토 완료" : "교사 검토 전";
        const next = confirm
          ? await server.saveAndConfirm(doc.sections, note)
          : await server.save(doc.sections, note);
        setBaseline(next);
        setDoc(next);
        setChecks([false, false, false]);
        setStaleWrite(false);
        setMessage(confirm ? "검토한 문서를 확정했어요." : "작성 중인 초안을 저장했어요.");
      } catch (e) {
        // 실패하면 편집 내용을 그대로 둔다.
        if (isStaleWrite(e)) {
          setStaleWrite(true);
        } else {
          setMessage(e instanceof Error ? e.message : "저장하지 못했어요.");
        }
      } finally {
        setBusy(false);
      }
      return;
    }
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
            const saved = await putAnnualMonth(annualPlanId, m.month, {
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
    const next: SavedDocument = withoutChildMetadata({
      ...doc,
      status: confirm ? "confirmed" : "draft",
      updatedAt: new Date().toISOString(),
      reviewNote: confirm
        ? imported
          ? "기존 증빙 원문·대상·기간 검토 완료 (공식 평가 판정 별도)"
          : `${available && verified ? "AI 검증 + " : ""}교사 사실·해석·지원 검토 완료`
        : "교사 검토 전",
    });
    if (onSave(next, baseline)) {
      setBaseline(next);
      setDoc(next);
      setMessage(confirm ? "검토한 문서를 확정했어요." : "작성 중인 초안을 저장했어요.");
    }
  }

  /** 서버가 준 문서로 편집기를 바꾼다. 사실이 달라졌을 수 있어 교사 확인은 다시 받는다. */
  function adopt(next: SavedDocument, note: string) {
    setBaseline(next);
    setDoc(next);
    setChecks([false, false, false]);
    setVerified(false);
    setIssues(null);
    setStaleWrite(false);
    setMessage(note);
  }

  /** 서버 요청 하나를 돌리고 성공하면 그 응답을 그대로 적용한다. 실패하면 입력을 둔다. */
  async function run(
    call: (s: ServerDocumentActions) => Promise<SavedDocument | null>,
    note: string,
    failed: string,
  ) {
    if (!server || working) return;
    setBusy(true);
    setMessage("");
    try {
      const next = await call(server);
      // reload 는 그 사이 다른 문서로 옮기면 null 이다 — 지금 편집기를 바꾸지 않는다.
      if (next) adopt(next, note);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : failed);
    } finally {
      setBusy(false);
    }
  }

  /** 동시 수정 충돌 복구. 서버의 현재 문서를 다시 읽을 뿐 근거를 다시 뜨지 않는다. */
  const reloadLatest = () =>
    run(
      (s) => s.reload(),
      "최신 문서를 불러왔어요. 내용을 확인한 뒤 다시 작성해주세요.",
      "최신 문서를 불러오지 못했어요.",
    );

  /** 확정 취소. 내용은 그대로고 상태만 초안으로 돌아온다. 근거 반영은 하지 않는다. */
  const unconfirm = () =>
    run(
      (s) => s.unconfirm(),
      "확정을 취소했어요. 다시 수정할 수 있어요.",
      "확정을 취소하지 못했어요.",
    );

  /** 바뀐 근거를 반영한다. 해석·지원은 서버가 두고, 교사 확인만 다시 받는다. */
  const refreshSources = () =>
    run(
      (s) => s.refresh(),
      "최신 근거를 불러왔어요. 해석과 지원을 다시 확인해주세요.",
      "최신 근거를 불러오지 못했어요.",
    );
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
      {server && staleWrite && (
        <>
          <Message error>
            다른 곳에서 이 문서가 수정되었어요. 최신 내용을 불러온 뒤 다시 작성해주세요.
          </Message>
          <p className={ws.hint}>
            최신 내용을 불러오면 현재 작성 중인 내용은 서버 최신 내용으로 바뀝니다.
          </p>
          <button className={ws.secondary} disabled={working} onClick={reloadLatest}>
            최신 문서 불러오기
          </button>
        </>
      )}
      {server?.stale && <Message error>근거 기록이 변경되어 다시 검토가 필요합니다.</Message>}
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
                disabled={working || stale}
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
          <button className={ws.secondary} disabled={working || stale} onClick={verify}>
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
                disabled={working || stale}
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
              disabled={working || stale}
              onClick={() => persist(false)}
            >
              초안 저장
            </button>
            <button
              className={ws.primary}
              disabled={
                working || stale || !checks.every(Boolean) || (!server && available === null)
              }
              onClick={() => persist(true)}
            >
              검토 완료 · 문서 확정
            </button>
            {server?.stale && (
              <button className={ws.secondary} disabled={working} onClick={refreshSources}>
                변경된 근거 반영하기
              </button>
            )}
          </>
        ) : server ? (
          <button className={ws.secondary} disabled={working} onClick={unconfirm}>
            확정 취소
          </button>
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
        {server && (
          <button
            className={ws.secondary}
            disabled={working}
            onClick={async () => {
              if (working) return;
              if (!window.confirm("문서를 삭제할까요? 되돌릴 수 없습니다.")) return;
              setMessage("");
              try {
                await server.remove();
              } catch (e) {
                setMessage(e instanceof Error ? e.message : "삭제하지 못했어요.");
              }
            }}
          >
            문서 삭제
          </button>
        )}
      </div>
    </section>
  );
}
