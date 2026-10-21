"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { getCurrentUser } from "@/lib/api/auth";
import {
  getEvaluationChecklist,
  saveEvaluationChecks,
  type AutoIndicator,
  type EvaluationChecklist as Checklist,
} from "@/lib/api/evaluation";
import { Message, ws } from "./WorkspaceUI";

const STATUS = {
  SUPPORTED: "기준 건수 충족",
  INSUFFICIENT: "기록 보완 필요",
  NONE: "집계된 문서 없음",
};

/** Official indicators and saved checks come from §12, never from browser-local documents. */
export default function EvaluationChecklist() {
  const [checklist, setChecklist] = useState<Checklist | null>(null);
  const [centerId, setCenterId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [reload, setReload] = useState(0);
  const running = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      try {
        const user = await getCurrentUser();
        if (user.center_id === null) throw new Error("원 정보를 먼저 등록해주세요.");
        const result = await getEvaluationChecklist(user.center_id, controller.signal);
        if (controller.signal.aborted) return;
        setCenterId(user.center_id);
        setChecklist(result);
        setError("");
      } catch (e) {
        if (!controller.signal.aborted)
          setError(e instanceof Error ? e.message : "평가 준비 현황을 불러오지 못했어요.");
      }
    })();
    return () => controller.abort();
  }, [reload]);

  async function check(element: string, checked: boolean) {
    if (centerId === null || running.current) return;
    const previous = checklist;
    running.current = true;
    setBusy(true);
    setError("");
    setMessage("");
    setChecklist(
      (before) =>
        before && {
          ...before,
          items: before.items.map((item) =>
            item.kind === "SELF_CHECK"
              ? {
                  ...item,
                  elements: item.elements.map((value) =>
                    value.element === element ? { ...value, checked } : value,
                  ),
                }
              : item,
          ),
        },
    );
    try {
      setChecklist(await saveEvaluationChecks(centerId, [{ element, checked }]));
      setMessage("자기 점검을 저장했어요.");
    } catch (e) {
      setChecklist(previous);
      setError(e instanceof Error ? e.message : "자기 점검을 저장하지 못했어요.");
    } finally {
      running.current = false;
      setBusy(false);
    }
  }

  if (!checklist) {
    return (
      <>
        <Message error>{error}</Message>
        {error ? (
          <button type="button" className={ws.secondary} onClick={() => setReload((n) => n + 1)}>
            다시 불러오기
          </button>
        ) : (
          <p role="status">평가 준비 현황을 불러오는 중…</p>
        )}
      </>
    );
  }

  return (
    <div className={ws.stack}>
      <p className={ws.hint}>
        {checklist.school_year}학년도 · 확정 문서의 종류·개수·기간과 교사의 자기 점검을 보여줘요.
        문서 내용의 적절성이나 공식 평가 통과를 판정하지 않아요.
      </p>
      <Message error>{error}</Message>
      <Message>{message}</Message>
      <div className={ws.actions}>
        <button
          type="button"
          className={ws.secondary}
          disabled={busy}
          onClick={() => setReload((n) => n + 1)}
        >
          현황 새로고침
        </button>
        <Link href="/documents" className={ws.link}>
          문서 보관함 보기
        </Link>
        <Link href="/plans" className={ws.link}>
          계획 노트 보기
        </Link>
      </div>
      <h2>확정 문서 자동 집계</h2>
      {checklist.items
        .filter((item): item is AutoIndicator => item.kind === "AUTO")
        .map((item) => (
          <section
            key={item.indicator}
            className={ws.card}
            aria-label={`${item.indicator} ${item.title}`}
          >
            <h3>
              {item.indicator} · {item.title}
            </h3>
            <p>{item.content}</p>
            <p>
              <strong>{STATUS[item.verdict]}</strong> · 집계 {item.count}건
            </p>
            <p className={ws.muted}>
              검토 기간 {item.period.from} ~ {item.period.to}
            </p>
            {item.classes && (
              <p>
                기준 건수를 채운 반 {item.classes.met} / {item.classes.total}개
              </p>
            )}
            {item.children && (
              <p>
                기준 건수를 채운 아동 {item.children.met} / {item.children.total}명
              </p>
            )}
            <details>
              <summary>집계 기준과 문서 확인</summary>
              {item.indicator === "4-1" ? (
                <p>
                  반마다 확정 월간계획안과 검토 기간의 평일별 확정 일일 보육일지를 확인해요.
                  공휴일·방학은 반영하지 않아 실제보다 부족하게 보일 수 있어요. 오늘 작성한 일지는
                  내일부터 집계돼요.
                </p>
              ) : (
                <p>
                  아동마다 확정된 영유아 평가 2건을 확인해요. 관찰일지 수로 대신 세지 않아요.
                  입소일을 받지 않아 입소 6개월 미만·6~12개월 아동은 실제보다 부족하게 보일 수
                  있어요.
                </p>
              )}
              <p>
                월간계획안 {item.plan_ids.length}건 · 일지·평가 문서 {item.document_ids.length}건
              </p>
            </details>
          </section>
        ))}
      <h2>교사 자기 점검</h2>
      {checklist.items.map((item) => {
        if (item.kind !== "SELF_CHECK") return null;
        return (
          <fieldset key={item.indicator} className={ws.card} disabled={busy}>
            <legend>
              {item.indicator} · {item.title}
            </legend>
            <p>{item.content}</p>
            <p className={ws.muted}>
              {item.progress.checked} / {item.progress.total}개 확인 ·{" "}
              {item.complete ? "자기 점검 완료" : "확인 필요"}
            </p>
            {item.elements.map((element) => (
              <label key={element.element} className={ws.check}>
                <input
                  type="checkbox"
                  checked={element.checked}
                  onChange={(e) => check(element.element, e.target.checked)}
                />
                <span>
                  {element.element} · {element.text}
                </span>
              </label>
            ))}
          </fieldset>
        );
      })}
      <p className={ws.hint}>
        현장에서 확인하는 1~3영역의 6개 지표는 이 화면에서 점검하지 않아요. 자기 점검 완료는 공식
        평가 충족을 뜻하지 않아요.
      </p>
    </div>
  );
}
