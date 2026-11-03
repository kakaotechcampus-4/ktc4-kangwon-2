"use client";

import { useEffect, useRef, useState } from "react";
import { getCurrentUser } from "@/lib/api/auth";
import {
  getEvaluationChecklist,
  saveEvaluationChecks,
  type AutoIndicator,
  type EvaluationChecklist as Checklist,
  type SelfCheckIndicator,
} from "@/lib/api/evaluation";
import { Message, ws } from "./WorkspaceUI";
import EvaluationAuto from "./EvaluationAuto";
import EvaluationSelfCheck from "./EvaluationSelfCheck";
import EvaluationSheet from "./EvaluationSheet";
import { readChecks, withFound, writeChecks, type Scan } from "@/lib/workspace/evaluation-files";
import styles from "./Evaluation.module.css";

/** 지표와 자체평가 체크는 서버(api-spec §12)에서 온다. 이 브라우저에 두는 것은 서류 점검 체크(항목 id)뿐이다. */
export default function EvaluationChecklist({
  refresh,
}: {
  /** 화면 머리의 「현황 새로고침」이 올리는 수. 바뀌면 다시 불러온다. */
  refresh: number;
}) {
  const [checklist, setChecklist] = useState<Checklist | null>(null);
  const [centerId, setCenterId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const [initiallyOpen, setInitiallyOpen] = useState(new Set<string>());
  // 파일 이름 검사 결과는 화면 메모리에만 둔다. 이름에 아동 실명이 있을 수 있다(ADR-045).
  const [scan, setScan] = useState<Scan | null>(null);
  // 서류 점검 체크(항목 id 만). 원 · 학년도를 안 뒤에 이 브라우저에서 읽는다.
  const [fileChecks, setFileChecks] = useState<string[]>([]);
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
        setFileChecks(readChecks(user.center_id, result.school_year));
        // 안 끝난 첫 평가항목 하나만 펼쳐서 연다. 나머지는 접어 두어 스크롤을 줄인다.
        const next = result.items.find((item) => item.kind === "SELF_CHECK" && !item.complete);
        setInitiallyOpen(new Set(next ? [next.indicator] : []));
        setError("");
      } catch (e) {
        if (!controller.signal.aborted)
          setError(e instanceof Error ? e.message : "평가 점검 현황을 불러오지 못했어요.");
      }
    })();
    return () => controller.abort();
  }, [reload, refresh]);

  async function check(element: string, checked: boolean) {
    if (centerId === null || running.current) return;
    const previous = checklist;
    running.current = true;
    setError("");
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
      setSavedAt(new Date());
    } catch (e) {
      setChecklist(previous);
      setError(e instanceof Error ? e.message : "자체평가를 저장하지 못했어요.");
    } finally {
      running.current = false;
    }
  }

  function saveFileChecks(next: string[]) {
    setFileChecks(next);
    if (centerId !== null && checklist) writeChecks(centerId, checklist.school_year, next);
  }

  /** 폴더를 고르면 이름으로 찾은 서류를 체크해 둔다. 교사가 한 체크는 그대로 둔다. */
  function scanned(result: Scan) {
    setScan(result);
    saveFileChecks(withFound(fileChecks, result));
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
          <p role="status">평가 점검 현황을 불러오는 중…</p>
        )}
      </>
    );
  }

  const autos = checklist.items.filter((item): item is AutoIndicator => item.kind === "AUTO");
  const selfs = checklist.items.filter(
    (item): item is SelfCheckIndicator => item.kind === "SELF_CHECK",
  );
  const checked = selfs.reduce((sum, item) => sum + item.progress.checked, 0);
  const total = selfs.reduce((sum, item) => sum + item.progress.total, 0);

  /*
   * 화면은 서류 한 장이 중심이다. 평가 당일 교사가 꺼내는 단위가 서류여서다.
   * 평가항목별로 보기와 자체평가는 접어 둔다 — 매달 보는 것이 아니라 원장이 물을 때 펴는 것이다.
   */
  return (
    <div className={ws.stack}>
      <p className={styles.basis}>
        {checklist.school_year}학년도
        {autos[0] && ` · ${autos[0].period.to}까지 확정한 문서 기준`}
      </p>
      <Message error>{error}</Message>
      <EvaluationSheet
        autos={autos}
        scan={scan}
        onScan={scanned}
        checks={fileChecks}
        onToggle={(id, on) =>
          saveFileChecks(on ? [...fileChecks, id] : fileChecks.filter((v) => v !== id))
        }
        onImported={() => setReload((n) => n + 1)}
      />
      <details className={styles.fold} aria-label="평가항목별로 보기">
        <summary>평가항목별로 보기 · {autos.map((item) => item.indicator).join(" · ")}</summary>
        <div className={styles.foldBody}>
          <EvaluationAuto items={autos} onImported={() => setReload((n) => n + 1)} />
        </div>
      </details>
      <details className={styles.fold} aria-label="현장에서 보는 것 직접 확인">
        <summary>
          현장에서 보는 것 직접 확인 · {checked} / {total}
        </summary>
        <div className={styles.foldBody}>
          <EvaluationSelfCheck
            items={selfs}
            savedAt={savedAt}
            initiallyOpen={initiallyOpen}
            onCheck={check}
          />
        </div>
      </details>
    </div>
  );
}
