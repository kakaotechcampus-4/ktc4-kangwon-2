"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { deleteAnnualPlan, getAnnualPlan, unconfirmAnnualPlan } from "@/lib/api/plans";
import { deleteMonthlyPlan, getMonthlyPlan, unconfirmMonthlyPlan } from "@/lib/api/monthly";
import { deletePlayMonthly, getPlayMonthly, unconfirmPlayMonthly } from "@/lib/api/playMonthly";
import { deleteWeeklyPlan, getWeeklyPlan, unconfirmWeeklyPlan } from "@/lib/api/weekly";
import { errorCode } from "@/lib/api/client";
import PlayMonthlyConfirm from "@/components/plan-generator/PlayMonthlyConfirm";
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
  /** 없으면 편집 단추를 그리지 않는다 — 승인받은 남의 반은 보기만 한다 (ADR-059). */
  onEdit?: () => void;
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
      {onEdit && (
        <button type="button" className={ws.primary} onClick={onEdit}>
          {document.status === "confirmed" ? "문서 열기" : "편집하기"}
        </button>
      )}
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
  /** 비면 「문서 열기」를 그리지 않는다 — 승인받은 남의 반 계획안은 편집 화면으로 보내지 않는다. */
  href: string;
  /** 놀이 중심 월간(`kind` 는 monthly). 읽기 · 지우기 경로가 다르다. */
  play?: boolean;
};

/** 지운다. 이 계획안으로 만든 하위가 있으면 서버가 409 `IN_USE` 다(ADR-062). */
function deletePlan(target: PlanPreviewTarget) {
  if (target.kind === "annual") return deleteAnnualPlan(target.id);
  if (target.kind === "weekly") return deleteWeeklyPlan(target.id);
  return target.play ? deletePlayMonthly(target.id) : deleteMonthlyPlan(target.id);
}
/** 확정을 풀어 초안으로 되돌린다. 딸린 하위가 있어도 풀린다(하위는 부모 스냅샷을 그대로 가진다). */
function unconfirmPlan(target: PlanPreviewTarget, revision: number | undefined) {
  if (target.kind === "annual") return unconfirmAnnualPlan(target.id, revision);
  if (revision === undefined) throw new Error("계획안 판이 없어요. 다시 열어 주세요.");
  if (target.kind === "weekly") return unconfirmWeeklyPlan(target.id, revision);
  return target.play
    ? unconfirmPlayMonthly(target.id, revision)
    : unconfirmMonthlyPlan(target.id, revision);
}
const IN_USE_MESSAGE: Record<PlanPreviewTarget["kind"], string> = {
  annual: "이 계획안으로 만든 월간계획안이 있어요. 먼저 지워주세요.",
  monthly: "이 계획안으로 만든 주간계획안이 있어요. 먼저 지워주세요.",
  weekly: "계획안을 지우지 못했어요.",
};

/**
 * 권한 검사는 기존 GET API가 한다. 이동/해제 뒤 늦은 응답은 버린다.
 * `onDeleted` 가 있으면 「삭제」를 그린다(상태 무관, 확정본도 — ADR-062). 남의 반은 넘기지 않는다.
 * 확정본이고 편집 화면이 있으면 「수정하기」(누르면 확정을 풀고 편집 화면으로 간다)도 그린다 — 계획안 화면에는 확정 취소가 없다(ADR-062).
 */
export function PlanArchivePreview({
  target,
  onDeleted,
}: {
  target: PlanPreviewTarget;
  onDeleted?: () => void;
}) {
  const key = `${target.kind}:${target.classId}:${target.id}`;
  const router = useRouter();
  const [request, setRequest] = useState<{
    key: string;
    content?: Content;
    revision?: number;
    error?: string;
  } | null>(null);
  const [retry, setRetry] = useState(0);
  const [asking, setAsking] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  async function unconfirm() {
    setDeleting(true);
    setDeleteError("");
    try {
      await unconfirmPlan(target, request?.revision);
      router.push(target.href);
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : "확정을 풀지 못했어요.");
      setDeleting(false);
    }
  }
  async function remove() {
    setDeleting(true);
    setDeleteError("");
    try {
      await deletePlan(target);
      setAsking(false);
      onDeleted?.();
    } catch (e) {
      setAsking(false);
      setDeleteError(
        errorCode(e) === "IN_USE"
          ? IN_USE_MESSAGE[target.kind]
          : e instanceof Error
            ? e.message
            : "계획안을 지우지 못했어요.",
      );
    } finally {
      setDeleting(false);
    }
  }
  useEffect(() => {
    let live = true;
    const controller = new AbortController();
    async function load() {
      let plan;
      let sections: Content["sections"];
      if (target.play) {
        const play = await getPlayMonthly(target.id, controller.signal);
        plan = play;
        sections = [
          { heading: "주제", body: play.theme.value },
          { heading: "주제선정이유", body: play.rationale.value },
          ...play.together.map((a) => ({
            heading: `함께 하는 활동 · ${a.name.value}`,
            body: a.description.value,
          })),
          ...play.free_play.map((a) => ({
            heading: `유아 예상 자유놀이 · ${a.name.value}`,
            body: a.description.value,
          })),
        ];
      } else if (target.kind === "annual") {
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
          revision: "revision" in plan ? plan.revision : undefined,
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
      {target.href && (
        <Link className={ws.primary} href={target.href}>
          문서 열기
        </Link>
      )}
      {onDeleted && target.href && current.content.status === "confirmed" && (
        <button type="button" className={ws.secondary} disabled={deleting} onClick={unconfirm}>
          수정하기
        </button>
      )}
      {onDeleted && (
        <button
          type="button"
          className={ws.secondary}
          disabled={deleting}
          onClick={() => setAsking(true)}
        >
          삭제
        </button>
      )}
      {asking && (
        <PlayMonthlyConfirm
          message="이 계획안을 지울까요? 되돌릴 수 없어요."
          yes={deleting ? "지우는 중…" : "지우기"}
          no="그대로 두기"
          disabled={deleting}
          onYes={remove}
          onNo={() => setAsking(false)}
        />
      )}
      {deleteError && <p role="alert">{deleteError}</p>}
    </>
  );
}
