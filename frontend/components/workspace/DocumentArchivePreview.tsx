"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getAnnualPlan } from "@/lib/api/plans";
import { getMonthlyPlan } from "@/lib/api/monthly";
import { getWeeklyPlan } from "@/lib/api/weekly";
import { DOCUMENT_KINDS, localDate, type SavedDocument, type Section } from "@/lib/workspace/model";
import { ws } from "./WorkspaceUI";
import styles from "./DocumentArchive.module.css";

type Content = {
  title: string;
  className: string;
  childName?: string;
  period: string;
  status: "draft" | "confirmed";
  createdAt: string;
  sections: Pick<Section, "heading" | "body">[];
  classNote?: string;
};

/** 입력 요소나 변경 요청을 갖지 않는, 실제 조회 값만 그리는 본문. */
export function PreviewContent({ content }: { content: Content }) {
  return (
    <article className={styles.previewContent}>
      <h2>{content.title}</h2>
      <p>
        {content.className}
        {content.childName ? ` · ${content.childName}` : ""}
      </p>
      <p>{content.period}</p>
      <p>
        {content.status === "confirmed" ? "확정" : "검토 중"}
        {content.createdAt ? ` · 작성 ${localDate(content.createdAt)}` : ""}
      </p>
      {!content.sections.some((s) => s.body.trim()) && <p>아직 작성된 본문이 없어요.</p>}
      {content.sections.map((section, i) => (
        <section key={i}>
          <h3>{section.heading}</h3>
          <p>{section.body || "아직 작성된 내용이 없어요."}</p>
        </section>
      ))}
      {content.classNote && (
        <section>
          <h3>반 운영 특이사항</h3>
          <p>{content.classNote}</p>
        </section>
      )}
    </article>
  );
}

function PreviewError({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <div>
      <p role="alert">미리보기를 불러오지 못했어요. {error}</p>
      <button type="button" className={ws.secondary} onClick={onRetry}>
        미리보기 다시 시도
      </button>
    </div>
  );
}

/** 기존 선택 컨트롤러가 조회한 문서를 읽기만 한다. 편집기는 여기서 마운트하지 않는다. */
export default function DocumentArchivePreview({
  document,
  status,
  error,
  onRetry,
  onEdit,
}: {
  document: SavedDocument | null;
  status: "loading" | "ready" | "error";
  error: string;
  onRetry: () => void;
  onEdit: () => void;
}) {
  if (status === "loading") return <p role="status">문서 미리보기를 불러오고 있어요.</p>;
  if (status === "error") return <PreviewError error={error} onRetry={onRetry} />;
  if (!document)
    return <PreviewError error="문서가 삭제되었거나 목록이 변경되었어요." onRetry={onRetry} />;
  return (
    <>
      <p className={ws.muted}>읽기 전용 · {DOCUMENT_KINDS[document.kind]}</p>
      {document.mockDraft && <p>테스트 모드(mock)로 만든 초안이에요.</p>}
      {"stale" in document && document.stale === true && (
        <p>원본 근거가 변경되었어요. 문서를 열어 재검토해 주세요.</p>
      )}
      <PreviewContent
        content={{
          ...document,
          period:
            document.start === document.end
              ? document.start
              : `${document.start} ~ ${document.end}`,
        }}
      />
      {document.reviewNote && (
        <section>
          <h3>검토 메모</h3>
          <p>{document.reviewNote}</p>
        </section>
      )}
      <button type="button" className={ws.primary} onClick={onEdit}>
        {document.status === "confirmed" ? "문서 열기" : "편집하기"}
      </button>
    </>
  );
}

export type PlanPreviewTarget = {
  kind: "annual" | "monthly" | "weekly";
  id: number;
  classId: number;
  className: string;
  title: string;
  period: string;
  periodKey: string;
  createdAt: string;
  href: string;
};

/** 권한 검사는 기존 GET API가 한다. 이동/해제 뒤 늦은 응답은 버린다. */
export function PlanArchivePreview({ target }: { target: PlanPreviewTarget }) {
  const key = `${target.kind}:${target.classId}:${target.id}`;
  const [request, setRequest] = useState<{ key: string; content?: Content; error?: string } | null>(
    null,
  );
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let live = true;
    const controller = new AbortController();
    async function load() {
      let plan;
      let sections: Content["sections"];
      if (target.kind === "annual") {
        const annual = await getAnnualPlan(target.id, controller.signal);
        plan = annual;
        sections = annual.months.map((m) => ({
          heading: `${m.month}월`,
          body: [m.theme, ...m.sub_themes].join("\n"),
        }));
      } else {
        const matrix =
          target.kind === "monthly"
            ? await getMonthlyPlan(target.id, controller.signal)
            : await getWeeklyPlan(target.id, controller.signal);
        plan = matrix;
        sections = matrix.sections
          .filter((s) => s.visible && s.role === "CONTENT")
          .flatMap((s) =>
            s.cells.map((c) => ({
              heading: s.label || "본문",
              body: ("week_id" in c && c.week_id ? `${c.week_id}\n` : "") + c.value,
            })),
          );
      }
      if (plan.id !== target.id || plan.class_id !== target.classId)
        throw new Error("선택한 반의 문서가 아니에요.");
      if (live)
        setRequest({
          key,
          content: {
            title: target.title,
            className: target.className,
            period: target.period,
            createdAt: target.createdAt,
            status: plan.status === "CONFIRMED" ? "confirmed" : "draft",
            sections,
          },
        });
    }
    void load().catch((e: unknown) => {
      if (live)
        setRequest({ key, error: e instanceof Error ? e.message : "문서를 조회할 수 없어요." });
    });
    return () => {
      live = false;
      controller.abort();
    };
  }, [key, retry, target]);
  const current = request?.key === key ? request : null;
  if (!current) return <p role="status">계획안 미리보기를 불러오고 있어요.</p>;
  if (current.error)
    return (
      <PreviewError
        error={current.error}
        onRetry={() => {
          setRequest(null);
          setRetry((n) => n + 1);
        }}
      />
    );
  if (!current.content) return null;
  return (
    <>
      <p className={ws.muted}>읽기 전용 · {DOCUMENT_KINDS[target.kind]}</p>
      <PreviewContent content={current.content} />
      <Link className={ws.primary} href={target.href}>
        문서 열기
      </Link>
    </>
  );
}
