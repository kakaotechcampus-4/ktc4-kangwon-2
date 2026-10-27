"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  DOCUMENT_KINDS,
  downloadText,
  validateDocument,
  type DocumentKind,
  type SavedDocument,
  type Section,
} from "@/lib/workspace/model";
import { requestAI } from "@/lib/workspace/ai-client";
import { AIHint, Message, useAIStatus, ws } from "./WorkspaceUI";
import { serverIssues } from "./document-selection";
import { invalidFields } from "@/lib/api/client";
import {
  downloadDocumentHwpx,
  isStaleWrite,
  type ReconfirmInput,
  type SourceResolution,
} from "@/lib/api/documents";
import { useHwpxDownload } from "@/lib/hooks/use-hwpx-download";
import SourceReview from "./SourceReview";
import { withoutChildMetadata } from "@/lib/privacy/browser-storage";
import { routinesPath } from "@/lib/workspace/routines-route";

import { API_STORAGE_CONTEXT } from "@/lib/api/storage-context";
import {
  getAnnualPlan,
  putAnnualMonth,
  confirmAnnualPlan,
  downloadAnnualHwpx,
} from "@/lib/api/plans";
import type { AnnualPlan } from "@/lib/api/types";

/**
 * 사실 칸의 원본을 고치는 곳. 사실은 여기서 못 고친다 — 서버가 `PUT` 으로 바뀐 사실을 거절한다 (§11).
 * 일일 보육일지는 같은 반·날짜의 일과 기록 화면(S-J1)으로 보낸다.
 */
const FACT_SOURCE: Partial<Record<DocumentKind, string>> = {
  observation: "/records",
  assessment: "/records",
};
const LAYER_HINTS: Record<string, string> = {
  사실: "교사가 입력한 원문 · 읽기 전용",
  해석: "위 사실에서 읽을 수 있는 의미만 적어주세요.",
  지원: "다음 놀이에서 교사가 할 구체적인 지원을 적어주세요.",
};

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
  /** 확정을 되돌린다. 근거를 다시 반영하지는 않는다 — 교사가 따로 누른다.
   *  `newlyStaleCount` 는 이 문서를 근거로 써서 이번에 다시 검토 대상이 된 문서 수다. */
  unconfirm: () => Promise<SavedDocument & { newlyStaleCount?: number }>;
  /** 바뀐 근거로 `사실` 을 다시 받는다. 초안이면서 stale 일 때만 부른다.
   *  사라진 근거가 있으면 교사가 고른 `resolutions` 를 함께 보낸다 — 없으면 서버가 거절한다. */
  refresh: (resolutions?: SourceResolution[]) => Promise<SavedDocument>;
  remove: () => Promise<void>;
  reconfirm?: (input: ReconfirmInput) => Promise<SavedDocument>;
}

/**
 * 서버가 `VALIDATION_FAILED` 로 짚는 칸 이름 → 화면에 보이는 칸 이름.
 *
 * 서버는 `sections.해석` 처럼 돌려주는데 그대로 띄우면 교사가 어디를 고칠지 모른다.
 * 점 뒤가 없는 이름(`sections`)은 칸 셋 모양 자체가 틀린 경우다.
 */
const SECTION_LABELS: Record<string, string> = {
  sections: "사실 · 해석 · 지원",
  "sections.사실": "사실",
  "sections.해석": "해석",
  "sections.지원": "지원",
};

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
  /** 검사 결과를 펼쳐 두었나. **결과는 지우지 않고 보이기만 접는다** — 접었다고 다시 돌릴
   *  필요가 없다. 본문이 바뀌면 그때는 옛 결과를 현재 문서의 결과로 읽히지 않게 버린다. */
  const [issuesOpen, setIssuesOpen] = useState(false);
  const annualPlanId =
    initial.annualApiSource === API_STORAGE_CONTEXT ? initial.annualPlanId : undefined;
  // 연간계획안을 불러와야 하는 문서라면 처음부터 로딩 상태로 시작한다(effect에서 setBusy(true) 하지 않기 위함).
  const [busy, setBusy] = useState(!!annualPlanId);
  const [message, setMessage] = useState("");
  const [staleWrite, setStaleWrite] = useState(false);
  /** 사라진 근거 복구 화면이 떠 있나. 떠 있으면 초안용 「변경된 근거 반영하기」를 숨긴다. */
  const [recovering, setRecovering] = useState(false);
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
  const factSource = recordDocument
    ? doc.kind === "dailyLog"
      ? routinesPath(doc.classId, doc.start)
      : FACT_SOURCE[doc.kind]
    : undefined;
  const hwpx = useHwpxDownload(setMessage);
  const supportsHwpx =
    !!annualPlanId || (!!server && ["observation", "dailyLog"].includes(doc.kind));
  // 서버 요청 중에는 입력·저장·확정·삭제가 서로 끼어들지 못한다.
  const working = busy || hwpx.exporting || !!server?.pending;
  function change(index: number, body: string) {
    setDoc((prev) => ({
      ...prev,
      status: "draft",
      sections: prev.sections.map((s, i) => (i === index ? { ...s, body } : s)),
    }));
    setChecks([false, false, false]);
    setVerified(false);
    setIssues(null);
    setIssuesOpen(false);
  }
  async function verify() {
    if (working || stale || available === null) return;
    // 같은 버튼을 다시 누르면 펼친 결과를 접는다. **결과 자체는 들고 있는다.**
    if (issuesOpen) {
      setIssuesOpen(false);
      return;
    }
    const local = server ? serverIssues(doc) : validateDocument(doc);
    setIssues(local);
    setIssuesOpen(true);
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
          // 서버가 짚은 칸을 버리지 않는다. 「입력값을 확인해주세요」만 띄우면
          // 교사가 어디가 틀렸는지 알 길이 없다.
          const blocked = invalidFields(e, SECTION_LABELS);
          setIssues(blocked.map((name) => `${name} 칸을 고쳐주세요.`));
          setIssuesOpen(blocked.length > 0);
          setMessage(
            blocked.length
              ? `${blocked.join(" · ")} 칸이 원본과 맞지 않아요.`
              : e instanceof Error
                ? e.message
                : "저장하지 못했어요.",
          );
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
  async function run<T extends SavedDocument>(
    call: (s: ServerDocumentActions) => Promise<T | null>,
    note: string | ((next: T) => string),
    failed: string,
  ) {
    if (!server || working) return;
    setBusy(true);
    setMessage("");
    try {
      const next = await call(server);
      // reload 는 그 사이 다른 문서로 옮기면 null 이다 — 지금 편집기를 바꾸지 않는다.
      if (next) adopt(next, typeof note === "function" ? note(next) : note);
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
      ({ newlyStaleCount }) =>
        "확정을 취소했어요. 다시 수정할 수 있어요." +
        (newlyStaleCount
          ? ` 이 문서를 근거로 쓴 문서 ${newlyStaleCount}건이 다시 검토 대상이 되었어요.`
          : ""),
      "확정을 취소하지 못했어요.",
    );

  /** 확정한 연간계획안을 서버가 만든 hwpx 로 받는다 (§9). 화면이 양식을 흉내 내지 않는다. */
  const exportHwpx = () => {
    if (annualPlanId) void hwpx.download(() => downloadAnnualHwpx(annualPlanId));
    else if (server) void hwpx.download(() => downloadDocumentHwpx(doc.id));
  };

  /**
   * 바뀐 근거를 반영한다. 해석·지원은 서버가 두고, 교사 확인만 다시 받는다.
   *
   * **초안 전용 API 다.** 확정본에 부르면 서버가 409 `ALREADY_CONFIRMED` 로 거절한다 —
   * 확정본은 위쪽 「변경된 근거 검토」(비교 · 원자적 재확정)를 쓴다. 버튼도 초안에만
   * 보이지만, 목록과 상세가 어긋난 순간에도 잘못 나가지 않게 여기서 한 번 더 막는다.
   */
  const refreshSources = () => {
    if (doc.status === "confirmed") {
      setMessage(
        "확정된 문서는 이 버튼으로 반영하지 않아요. 위쪽 「변경된 근거 검토」에서 확인한 뒤 재확정해주세요.",
      );
      return;
    }
    // 호출부가 기다릴 수 있게 그대로 돌려준다.
    return run(
      (s) => s.refresh(),
      "최신 근거를 불러왔어요. 해석과 지원을 다시 확인해주세요.",
      "최신 근거를 불러오지 못했어요.",
    );
  };
  return (
    <section className={`${ws.card} ${ws.document}`}>
      {server?.stale && doc.kind === "dailyLog" && server.reconfirm && (
        <SourceReview
          key={`${doc.id}:${doc.updatedAt}`}
          doc={doc}
          pending={working}
          reconfirm={server.reconfirm}
          refresh={server.refresh}
          onRecovery={setRecovering}
          onReload={reloadLatest}
          onComplete={adopt}
        />
      )}
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
      <header>
        <div className={ws.between}>
          <span className={ws.badge}>
            {doc.status === "confirmed" ? "교사 확정" : "검토 중인 초안"}
          </span>
          {/* 근거가 바뀐 문서는 제목 줄에서 바로 보여야 한다. 아래쪽 안내문만으로는
              문서를 열고 스크롤해야 알 수 있었다 (수린 점검). */}
          {server?.stale && <span className={ws.badge}>다시 검토</span>}
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
        {supportsHwpx && recordDocument && (
          <p className={ws.hint}>
            {editable
              ? "사실을 확인하고 해석·지원을 다듬은 뒤 문서를 확정하면 한글 파일(hwpx)로 내려받을 수 있어요."
              : "아래에서 확정한 문서를 한글 파일(hwpx)로 내려받을 수 있어요."}
          </p>
        )}
        {/* mock LLM 초안이다. **본문에 섞지 않고** 여기서만 알린다 — 제출 문서는 깨끗하게
            두면서도 테스트 초안을 실제 AI 결과로 보이게 하지 않는다. */}
        {doc.mockDraft && (
          <p className={ws.muted}>
            테스트 모드(mock)로 만든 초안이에요. 실제 AI 생성 결과가 아니니 내용을 그대로 쓰지 말고
            교사가 다시 작성해주세요.
          </p>
        )}
      </header>
      {doc.sections.map((section, index) => (
        <section
          className={recordDocument ? ws.documentLayer : undefined}
          key={`${section.heading}-${index}`}
        >
          <h3>{section.heading}</h3>
          {recordDocument && LAYER_HINTS[section.heading] && (
            <p className={ws.hint}>{LAYER_HINTS[section.heading]}</p>
          )}
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
          {factSource && section.heading === "사실" && (
            <p className={ws.hint}>
              교사가 적은 원문입니다. 고치려면{" "}
              <Link className={ws.link} href={factSource}>
                {doc.kind === "dailyLog"
                  ? "일과 기록에서 고쳐 주세요 →"
                  : "관찰 기록에서 고쳐 주세요 →"}
              </Link>
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
      {server?.stale && (
        <Message error>
          {`이 문서의 근거로 사용된 ${doc.kind === "dailyLog" ? "일과 기록" : doc.kind === "weeklyLog" ? "일일 보육일지" : "관찰 기록"}이 변경되었습니다.\n` +
            "변경 내용을 확인한 뒤 문서에 반영해 주세요."}
        </Message>
      )}
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
              : issuesOpen
                ? "검사 결과 접기"
                : available && recordDocument
                  ? "AI 검증하기"
                  : "기본 항목 검사"}
          </button>
          {issues && issuesOpen && (
            <Message error={issues.length > 0}>
              {issues.length
                ? `반려 · 수정이 필요해요\n${issues.map((s) => `• ${s}`).join("\n")}`
                : available && verified
                  ? "AI 검증에서 문제를 찾지 못했어요. 교사 최종 검토를 진행해주세요."
                  : "기본 항목은 통과했어요. 원본 대조는 확정할 때 서버가 합니다."}
            </Message>
          )}
          {/* 일지는 한 번만 묻는다. 세 칸을 따로 받던 때는 교사가 같은 문서를 세 번 훑어야 했다.
              서버 계약의 `checks.fact · interpretation · support` 는 그대로 두고, 교사가 이
              하나를 체크했을 때만 셋을 함께 true 로 보낸다 (§11). */}
          {recordDocument ? (
            <label className={ws.check}>
              <input
                type="checkbox"
                checked={checks.every(Boolean)}
                disabled={working || stale}
                onChange={(e) => setChecks([e.target.checked, e.target.checked, e.target.checked])}
              />
              원본 기록과 사실이 일치하고, 해석과 지원 내용이 적절한지 확인하셨나요?
            </label>
          ) : (
            [
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
                {imported
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
            ))
          )}
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
            {server?.stale && !recovering && (
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
        {supportsHwpx && doc.status === "confirmed" && (
          <button
            className={ws.primary}
            disabled={working || hwpx.exporting || !!server?.stale}
            onClick={exportHwpx}
          >
            {hwpx.exporting ? "파일 만드는 중…" : "한글 파일로 내려받기"}
          </button>
        )}
        {/* 연간을 확정해야 월간을 만들 수 있다 (§9-1 Gate). 확정한 그 자리에서 다음 걸음을 준다 —
            사이드바로 돌아가 찾게 하지 않는다. */}
        {annualPlanId && doc.status === "confirmed" && (
          <Link className={ws.secondary} href="/plans/monthly">
            월간계획안 만들기 →
          </Link>
        )}
        {/* 일지도 같다 — 확정했고 근거가 그대로일 때만. 근거가 바뀐 채로 내보내면
            교사가 확정한 것과 다른 종이가 나간다 (서버도 409 로 거절한다). */}
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
        {/* 확정 문서는 지울 수 없다 — 서버가 409 ALREADY_CONFIRMED 로 거절한다.
            눌러도 실패할 버튼을 보여 주면 교사는 고장으로 읽는다. 확정 취소가 먼저다. */}
        {server && editable && (
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
