"use client";
import { useEffect, useRef, useState } from "react";
import {
  getSourceComparison,
  type ReconfirmInput,
  type SourceComparison,
  type SourceResolution,
} from "@/lib/api/documents";
import { routineLocalId } from "@/lib/api/routines";
import type { SavedDocument } from "@/lib/workspace/model";
import { Message, ws } from "./WorkspaceUI";

/** `[이름 09:20~10:40] 기록` 을 머리말과 본문으로 가른다. 모양이 다르면 통째로 본문이다. */
function splitFact(text: string) {
  const match = /^\[([^\]]*)\]\s*([\s\S]*)$/.exec(text);
  return match ? { head: match[1], body: match[2] } : { head: "삭제된 일과 기록", body: text };
}

type Plan = { action: "drop" | "replace"; replacementId: number | null };

/**
 * 재확정 뒤 남을 근거를 비교 응답 순서대로 만든다.
 *
 * 고르지 않은 삭제 근거는 아직 남길지 뺄지 모르므로 여기서 빠진다 — `ready` 가 막는다.
 */
function survivorsOf(comparison: SourceComparison, plans: Record<number, Plan>) {
  const candidates = comparison.candidates ?? [];
  const rows: { id: number; text: string }[] = [];
  for (const source of comparison.sources) {
    const plan = source.state === "missing" ? plans[source.id] : undefined;
    if (!plan) {
      if (source.state !== "missing") rows.push({ id: source.id, text: source.after ?? "" });
      continue;
    }
    if (plan.action === "drop" || plan.replacementId === null) continue;
    const pick = candidates.find((c) => c.id === plan.replacementId);
    if (pick) rows.push({ id: pick.id, text: pick.text });
  }
  return rows;
}

/**
 * 바뀌거나 사라진 근거를 교사가 보고 처리한다. 서버 변경은 마지막 한 요청뿐이다.
 *
 * 확정본이면 비교 → 해석·지원 검토 → 단일 확인 → 원자적 재확정이다.
 * 초안이면 **사라진 근거가 있을 때만** 뜬다 — 빼거나 바꿀 것을 고르고 `refresh` 로 반영한다.
 * 초안은 그대로 초안으로 남는다. 확정은 교사가 평소대로 아래에서 한다.
 */
export default function SourceReview({
  doc,
  pending,
  reconfirm,
  refresh,
  onComplete,
  onRecovery,
  onReload,
}: {
  doc: SavedDocument;
  pending: boolean;
  reconfirm: (input: ReconfirmInput) => Promise<SavedDocument>;
  refresh: (resolutions?: SourceResolution[]) => Promise<SavedDocument>;
  onComplete: (next: SavedDocument, note: string) => void;
  onRecovery: (open: boolean) => void;
  onReload: () => void;
}) {
  const draft = doc.status !== "confirmed";
  const [comparison, setComparison] = useState<SourceComparison | null>(null);
  const [error, setError] = useState("");
  const [visit, setVisit] = useState(0);
  const [sections, setSections] = useState(doc.sections);
  const [checked, setChecked] = useState(false);
  const [plans, setPlans] = useState<Record<number, Plan>>({});
  const [busy, setBusy] = useState(false);
  const running = useRef(false);
  useEffect(() => {
    let live = true;
    getSourceComparison(doc.id)
      .then((next) => {
        if (!live) return;
        setComparison(next);
        setError("");
        // 초안은 사라진 근거가 있을 때만 이 화면을 쓴다 — 부모가 옛 버튼을 숨길 수 있게 알린다.
        onRecovery(draft && next.sources.some((s) => s.state === "missing"));
      })
      .catch((e) => {
        if (live) setError(e instanceof Error ? e.message : "근거를 비교하지 못했어요.");
      });
    return () => {
      live = false;
      onRecovery(false);
    };
    // onRecovery 는 부모의 setState 라 안정적이다. 비교를 다시 부르는 조건만 본다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doc.id, visit, draft]);
  function reload() {
    setComparison(null);
    setChecked(false);
    setPlans({});
    setError("");
    setVisit((n) => n + 1);
  }
  function choose(sourceId: number, plan: Plan) {
    setPlans((prev) => ({ ...prev, [sourceId]: plan }));
    // 근거 구성이 달라지면 교사가 본 사실도 달라진다. 확인을 다시 받는다.
    setChecked(false);
  }

  const working = pending || busy;
  const changedDocument =
    comparison !== null && Date.parse(comparison.updated_at) !== Date.parse(doc.updatedAt);
  const deleted = comparison?.sources.filter((s) => s.state === "missing") ?? [];
  const candidates = comparison?.candidates ?? [];
  const survivors = comparison ? survivorsOf(comparison, plans) : [];
  const facts = survivors.map((s) => s.text).join("\n\n");
  const picked = deleted
    .map((s) => plans[s.id])
    .filter((p): p is Plan => p?.action === "replace" && p.replacementId !== null)
    .map((p) => p.replacementId);
  const resolved =
    deleted.every((s) => {
      const plan = plans[s.id];
      return plan?.action === "drop" || (plan?.action === "replace" && plan.replacementId !== null);
    }) && new Set(picked).size === picked.length;
  const emptied = deleted.length > 0 && resolved && survivors.length === 0;
  const ready =
    comparison !== null &&
    !changedDocument &&
    survivors.length > 0 &&
    (deleted.length > 0 ? resolved : comparison.can_reconfirm);

  async function submit() {
    if (!comparison || !ready || (!draft && !checked) || running.current || pending) return;
    running.current = true;
    setBusy(true);
    setError("");
    try {
      const resolutions: SourceResolution[] = deleted.map((source) => ({
        source_id: source.id,
        action: plans[source.id].action,
        ...(plans[source.id].action === "replace"
          ? { replacement_id: plans[source.id].replacementId }
          : {}),
      }));
      if (draft) {
        // 초안은 사실과 근거만 서버가 다시 뜬다. 해석·지원은 손대지 않고 초안으로 남는다.
        onComplete(
          await refresh(resolutions),
          "변경사항을 반영했어요. 내용을 확인한 뒤 확정해주세요.",
        );
        return;
      }
      const sourceIds = survivors.map((s) => routineLocalId(s.id));
      const next = await reconfirm({
        comparison,
        updatedAt: doc.updatedAt,
        sections: sections.map((s) => ({
          ...s,
          body: s.heading === "사실" ? facts : s.body,
          sourceIds,
        })),
        resolutions,
      });
      onComplete(next, "변경사항을 반영하고 재확정했어요.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "재확정하지 못했어요.");
    } finally {
      running.current = false;
      setBusy(false);
    }
  }

  if (draft && comparison && deleted.length === 0) return null;
  return (
    <section className={ws.stack} aria-label="변경된 근거 검토" aria-busy={!comparison && !error}>
      <h2>
        {deleted.length > 0 ? "삭제된 근거를 처리해주세요" : "변경된 근거를 먼저 확인해주세요"}
      </h2>
      {draft && comparison && (
        <p className={ws.muted}>
          반영해도 초안 그대로예요. 사실이 바뀌면 해석과 지원을 다시 읽고 아래에서 확정해주세요.
        </p>
      )}
      {!comparison && !error && <p>원본과 문서의 근거 사본을 비교하고 있어요…</p>}
      <Message error>{error}</Message>
      {changedDocument && (
        <>
          <Message error>
            문서가 다른 화면에서 변경되었어요. 최신 문서를 불러온 뒤 다시 검토해주세요.
          </Message>
          <button type="button" className={ws.secondary} disabled={working} onClick={onReload}>
            최신 문서 불러오기
          </button>
        </>
      )}
      {comparison && (
        <>
          {deleted.length > 0 && (
            /* A. 무슨 일이 있었는지 + 지워진 근거가 일지에 어떤 모습으로 남아 있는지 */
            <div className={ws.notice}>
              <strong>보육일지에 사용된 일과 기록 {deleted.length}건이 삭제되었습니다.</strong>
              <p className={ws.muted}>
                삭제된 기록은 되살릴 수 없어요. 이 보육일지를 어떻게 고칠지 아래에서 골라주세요.
              </p>
              {deleted.map((source) => {
                const fact = splitFact(source.before);
                return (
                  <article key={source.id} className={ws.item}>
                    <h3>{fact.head}</h3>
                    <p className={ws.muted}>보육일지에 남아 있는 기존 기록</p>
                    <p className={ws.quote}>{fact.body}</p>
                  </article>
                );
              })}
            </div>
          )}
          {/* B. 삭제된 근거마다 뺄지 바꿀지 고른다. 고른 값은 서버가 다시 검사한다. */}
          {deleted.map((source) => {
            const plan = plans[source.id];
            const name = splitFact(source.before).head;
            return (
              <div
                key={source.id}
                role="radiogroup"
                aria-labelledby={`deleted-source-${source.id}-title`}
              >
                <h3 id={`deleted-source-${source.id}-title`}>
                  {deleted.length > 1 ? `${name} — ` : ""}삭제된 근거를 어떻게 처리할까요?
                </h3>
                <label className={ws.check}>
                  <input
                    type="radio"
                    name={`deleted-source-${source.id}`}
                    checked={plan?.action === "drop"}
                    disabled={working}
                    onChange={() => choose(source.id, { action: "drop", replacementId: null })}
                  />
                  삭제된 근거를 보육일지에서도 제외하기
                </label>
                <label className={ws.check}>
                  <input
                    type="radio"
                    name={`deleted-source-${source.id}`}
                    checked={plan?.action === "replace"}
                    disabled={working || candidates.length === 0}
                    onChange={() => choose(source.id, { action: "replace", replacementId: null })}
                  />
                  다른 일과 기록으로 대체하기
                  {candidates.length === 0 && (
                    <small>같은 반·같은 날짜에 쓸 수 있는 다른 일과 기록이 없어요.</small>
                  )}
                </label>
                {plan?.action === "replace" && (
                  <label className={ws.field}>
                    대체할 일과 기록
                    <select
                      aria-label={`${name} 대체할 일과 기록`}
                      value={plan.replacementId ?? ""}
                      disabled={working}
                      onChange={(e) =>
                        choose(source.id, {
                          action: "replace",
                          replacementId: e.target.value ? Number(e.target.value) : null,
                        })
                      }
                    >
                      <option value="">—</option>
                      {candidates.map((candidate) => (
                        <option key={candidate.id} value={candidate.id}>
                          {candidate.text}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
              </div>
            );
          })}
          {emptied && (
            <Message error>
              근거를 모두 빼면 보육일지를 재확정할 수 없어요. 최소 한 건은 남겨주세요.
            </Message>
          )}
          <p>변경된 일과 기록 {comparison.sources.filter((s) => s.state === "changed").length}건</p>
          {comparison.sources.map((source) => (
            <article key={source.id} className={ws.item}>
              <h3>
                일과 #{source.id} ·{" "}
                {source.state === "missing"
                  ? "원본 없음"
                  : source.state === "unchanged"
                    ? "변경 없음"
                    : "변경됨"}
              </h3>
              <h4>수정 전</h4>
              <p className={ws.sourceText}>{source.before}</p>
              <h4>수정 후</h4>
              <p className={ws.sourceText}>
                {source.after ??
                  (plans[source.id]?.action === "drop"
                    ? "이 보육일지에서 제외합니다."
                    : plans[source.id]?.replacementId
                      ? (candidates.find((c) => c.id === plans[source.id].replacementId)?.text ??
                        "")
                      : "삭제되었습니다. 제외하거나 다른 일과 기록으로 대체해주세요.")}
              </p>
            </article>
          ))}
          {!draft &&
            sections
              .filter((s) => s.heading !== "사실")
              .map((section) => (
                <label key={section.heading} className={ws.field}>
                  기존 {section.heading} · 필요하면 수정해주세요
                  <textarea
                    aria-label={`재검토 ${section.heading}`}
                    value={section.body}
                    disabled={working}
                    onChange={(e) => {
                      setSections((prev) =>
                        prev.map((s) =>
                          s.heading === section.heading ? { ...s, body: e.target.value } : s,
                        ),
                      );
                      setChecked(false);
                    }}
                  />
                </label>
              ))}
          {/* C. 뒷단계 — 고른 뒤에 하는 확인. 얇은 선과 여백으로 B 와 떼어 둔다.
                 초안은 여기서 확정하지 않으므로 확인을 받지 않는다. */}
          {!draft && (
            <div className={ws.confirmStep}>
              <h3>교사 확인</h3>
              <label className={ws.check}>
                <input
                  type="checkbox"
                  checked={checked}
                  disabled={working || !ready}
                  onChange={(e) => setChecked(e.target.checked)}
                />
                원본 기록과 사실이 일치하고, 해석과 지원 내용이 적절한지 확인하셨나요?
              </label>
            </div>
          )}
          {/* D. 하단 액션 */}
          <div className={ws.actions}>
            <button
              type="button"
              className={ws.primary}
              disabled={working || !ready || (!draft && !checked)}
              onClick={submit}
            >
              {working
                ? draft
                  ? "반영 중…"
                  : "재확정 중…"
                : draft
                  ? "변경사항 반영하기"
                  : "변경사항 반영하고 재확정"}
            </button>
            <button type="button" className={ws.secondary} disabled={working} onClick={reload}>
              {deleted.length > 0 ? "취소" : "근거 다시 비교하기"}
            </button>
          </div>
          {!ready && !changedDocument && deleted.length === 0 && !comparison.can_reconfirm && (
            <Message error>
              확정 상태와 재검토 대상을 확인해주세요. 기존 확정본은 유지됩니다.
            </Message>
          )}
        </>
      )}
    </section>
  );
}
