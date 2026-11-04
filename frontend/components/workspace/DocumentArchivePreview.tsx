"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { downloadDocumentHwpx } from "@/lib/api/documents";
import { downloadAnnualHwpx, getAnnualPlan } from "@/lib/api/plans";
import { downloadMonthlyHwpx, getMonthlyPlan } from "@/lib/api/monthly";
import { downloadWeeklyHwpx, getWeeklyPlan } from "@/lib/api/weekly";
import { useHwpxDownload } from "@/lib/hooks/use-hwpx-download";
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

/** 단락 이름별 왼쪽 띠 색. 그 밖의 단락(계획안 칸 등)은 기본 선 색이다. */
const SECTION_TONES: Record<string, string> = { 사실: "fact", 해석: "read", 지원: "support" };

/** 입력 요소나 변경 요청을 갖지 않는, 실제 조회 값만 그리는 본문.
 *  children 은 머리 쪽지 바로 아래에 붙는 안내(테스트 초안 · 근거 변경)다. */
export function PreviewContent({
  content,
  kind,
  children,
}: {
  content: Content;
  kind: string;
  children?: ReactNode;
}) {
  return (
    <article className={styles.previewContent}>
      <header className={styles.previewHead}>
        <div className={styles.previewMeta}>
          <span className={styles.previewKind}>읽기 전용 · {kind}</span>
          <span className={styles.previewStatus} data-status={content.status}>
            {content.status === "confirmed" ? "확정" : "검토 중"}
          </span>
        </div>
        <h2>{content.title}</h2>
        <dl className={styles.previewFacts}>
          <div>
            <dt>{content.childName ? "반 · 아이" : "반"}</dt>
            <dd>
              {content.className}
              {content.childName ? ` · ${content.childName}` : ""}
            </dd>
          </div>
          <div>
            <dt>기간</dt>
            <dd>{content.period}</dd>
          </div>
          {content.createdAt && (
            <div>
              <dt>작성</dt>
              <dd>{localDate(content.createdAt)}</dd>
            </div>
          )}
        </dl>
      </header>
      {children}
      {!content.sections.some((s) => s.body.trim()) && (
        <p className={styles.previewNotice}>아직 작성된 본문이 없어요.</p>
      )}
      {content.sections.map((section, i) => (
        <section
          key={i}
          className={styles.previewSection}
          data-tone={SECTION_TONES[section.heading]}
        >
          <h3>{section.heading}</h3>
          {section.body ? (
            <p>{section.body}</p>
          ) : (
            <p className={styles.previewEmpty}>아직 작성된 내용이 없어요.</p>
          )}
        </section>
      ))}
      {content.classNote && (
        <section className={styles.previewSection}>
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
  /** 없으면 열람 전용이다 — 담임이 다른 반의 문서 (DocumentsPage 의 `readOnlyClass`). */
  onEdit?: () => void;
}) {
  if (status === "loading") return <p role="status">문서 미리보기를 불러오고 있어요.</p>;
  if (status === "error") return <PreviewError error={error} onRetry={onRetry} />;
  if (!document)
    return <PreviewError error="문서가 삭제되었거나 목록이 변경되었어요." onRetry={onRetry} />;
  return (
    <>
      <PreviewContent
        kind={DOCUMENT_KINDS[document.kind]}
        content={{
          ...document,
          period:
            document.start === document.end
              ? document.start
              : `${document.start} ~ ${document.end}`,
        }}
      >
        {document.mockDraft && (
          <p className={styles.previewNotice}>테스트 모드(mock)로 만든 초안이에요.</p>
        )}
        {"stale" in document && document.stale === true && (
          <p className={styles.previewNotice} data-tone="warn">
            원본 근거가 변경되었어요. 문서를 열어 재검토해 주세요.
          </p>
        )}
      </PreviewContent>
      {document.reviewNote && (
        <section className={styles.previewMemo}>
          <h3>검토 메모</h3>
          <p>{document.reviewNote}</p>
        </section>
      )}
      {onEdit ? (
        <div className={styles.previewActions}>
          <button type="button" className={ws.primary} onClick={onEdit}>
            {document.status === "confirmed" ? "문서 열기" : "편집하기"}
          </button>
        </div>
      ) : (
        document.status === "confirmed" && (
          <ReadOnlyDownload fetchFile={() => downloadDocumentHwpx(document.id)} />
        )
      )}
    </>
  );
}

/**
 * 담임이 다른 반은 편집 화면을 열지 않고 내려받기만 둔다. 서버는 확정본만 내보낸다
 * (documents/export.py · plans/export.py) — 그래서 확정본에만 보인다.
 */
function ReadOnlyDownload({ fetchFile }: { fetchFile: () => Promise<void> }) {
  const [message, setMessage] = useState("");
  const hwpx = useHwpxDownload(setMessage);
  return (
    <div className={styles.previewActions}>
      <button
        type="button"
        className={ws.primary}
        disabled={hwpx.exporting}
        onClick={() => void hwpx.download(fetchFile)}
      >
        {hwpx.exporting ? "파일 만드는 중…" : "한글 파일로 내려받기"}
      </button>
      {message && <p role="status">{message}</p>}
    </div>
  );
}

const PLAN_DOWNLOAD = {
  annual: downloadAnnualHwpx,
  monthly: downloadMonthlyHwpx,
  weekly: downloadWeeklyHwpx,
} as const;

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
export function PlanArchivePreview({
  target,
  readOnly = false,
}: {
  target: PlanPreviewTarget;
  /** 담임이 다른 반. 편집 화면(문서 열기)으로 보내지 않는다. */
  readOnly?: boolean;
}) {
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
        if (annual.format === "PLAY_PROJECT") {
          sections = annual.periods.flatMap((period) =>
            period.selected.flatMap((key) => {
              const row = period.candidates.find((candidate) => candidate.row_key === key);
              if (!row) return [];
              return [
                {
                  heading: `${period.label} · ${row.play_name.value}`,
                  body: [row.materials.value, row.support_direction.value, row.learning.value].join(
                    "\n",
                  ),
                },
              ];
            }),
          );
        } else {
          sections = annual.months.map((m) => ({
            heading: `${m.month}월`,
            body: [m.theme, ...m.sub_themes].join("\n"),
          }));
        }
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
      <PreviewContent kind={DOCUMENT_KINDS[target.kind]} content={current.content} />
      {!readOnly ? (
        <div className={styles.previewActions}>
          <Link className={ws.primary} href={target.href}>
            문서 열기
          </Link>
        </div>
      ) : (
        current.content.status === "confirmed" && (
          <ReadOnlyDownload fetchFile={() => PLAN_DOWNLOAD[target.kind](target.id)} />
        )
      )}
    </>
  );
}
