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
import EvaluationSheet, {
  DirectorFold,
  FolderCard,
  FoldMark,
  StampBoard,
  sheetRows,
} from "./EvaluationSheet";
import { readChecks, writeChecks, type Scan } from "@/lib/workspace/evaluation-files";
import styles from "./Evaluation.module.css";

/** 지표와 자체평가 체크는 서버(api-spec §12)에서 온다. 이 브라우저에 두는 것은 서류 점검 체크(항목 id)뿐이다. */
export default function EvaluationChecklist() {
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
  }, [reload]);

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

  const rows = sheetRows(autos, scan, fileChecks);
  // `date`(YYYY-MM-DD)는 시간대가 없어 잘라 써도 된다.
  const [, toMonth, toDay] = (autos[0]?.period.to ?? "").split("-").map(Number);
  const basis = `${checklist.school_year}학년도${toDay ? ` · ${toMonth}월 ${toDay}일까지 확정한 문서 기준` : ""}`;
  const recount = () => setReload((n) => n + 1);
  const toggleFile = (id: string, on: boolean) =>
    saveFileChecks(on ? [...fileChecks, id] : fileChecks.filter((v) => v !== id));

  /*
   * 맨 위에 서류 도장판(전체 폭) — 평가 당일 교사가 꺼내는 단위가 서류여서 서류마다 칸 하나.
   * 그 아래 왼쪽에 서류마다 자세히(표), 오른쪽 330px 칸에 폴더 고르기와 접힌 칸 셋(시안 ⑥, 2026-11-08).
   * 오른쪽 칸은 페이지와 같이 스크롤한다 — 따로 스크롤하면 노트북 높이에서 접힌 칸이 안쪽 밑으로 숨었다.
   */
  return (
    <div className={ws.stack}>
      <Message error>{error}</Message>
      <StampBoard rows={rows} basis={basis} onToggle={toggleFile} onRecount={recount} />
      <div className={`${ws.grid} ${styles.layout}`}>
        <EvaluationSheet rows={rows} scanned={!!scan} onImported={recount} />
        <div className={styles.aside}>
          {/* 폴더 결과는 화면 메모리에만 둔다(ADR-045 결정 5). 체크 목록에 써 넣지 않는다 — 도장 근거 「내컴퓨터」 · 「직접확인」을 가르려고. */}
          <FolderCard scan={scan} onScan={setScan} />
          <DirectorFold checks={fileChecks} onToggle={toggleFile} />
          <details className={styles.fold} aria-label="평가항목별로 보기">
            <summary>
              <FoldMark />
              평가항목별로 보기 · {autos.map((item) => item.indicator).join(" · ")}
            </summary>
            <div className={styles.foldBody}>
              <EvaluationAuto items={autos} onImported={recount} />
            </div>
          </details>
          <details className={styles.fold} aria-label="현장에서 보는 것 직접 확인">
            <summary>
              <FoldMark />
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
      </div>
    </div>
  );
}
