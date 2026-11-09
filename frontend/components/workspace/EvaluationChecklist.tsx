"use client";

import { useEffect, useRef, useState } from "react";
import { getCurrentUser } from "@/lib/api/auth";
import {
  getEvaluationChecklist,
  saveDirectorChecks,
  saveEvaluationChecks,
  saveEvaluationDocuments,
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
import { TEACHER_DOCS, summarize, windowOf, type Scan } from "@/lib/workspace/evaluation-files";
import { today } from "@/lib/workspace/model";
import styles from "./Evaluation.module.css";

/**
 * 지표 · 자체평가 체크 · 평가 서류 도장 근거는 모두 서버(api-spec §12 · ADR-074)에서 온다.
 * 브라우저에 아무것도 저장하지 않는다. 파일 이름은 이번에 고른 폴더의 화면 메모리에만 있다.
 */
export default function EvaluationChecklist() {
  const [checklist, setChecklist] = useState<Checklist | null>(null);
  const [centerId, setCenterId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const [initiallyOpen, setInitiallyOpen] = useState(new Set<string>());
  // 파일 이름 검사 결과는 화면 메모리에만 둔다. 이름에 아동 실명이 있을 수 있다(ADR-045).
  // 서버에는 서류마다 상태 · 숫자만 보낸다(ADR-074 결정 5).
  const [scan, setScan] = useState<Scan | null>(null);
  const [reload, setReload] = useState(0);
  // 저장은 하나씩 차례로 보낸다 — 체크했다 바로 풀면 서버가 그 순서대로 받아야 한다(Codex 리뷰 11-09).
  // 자체평가 체크 · 직접확인 · 원장 서류 · 폴더 결과가 같은 줄에 선다. 응답이 모두 GET 과 같은 전체라서다.
  const queue = useRef<Promise<void>>(Promise.resolve());
  const waiting = useRef(0);

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

  /**
   * 화면을 먼저 바꾸고 저장을 줄 세운다. 응답은 그때까지의 저장을 다 담은 전체라,
   * **줄의 마지막 응답만** 화면에 쓴다 — 앞 응답을 쓰면 뒤에서 기다리는 저장이 화면에서 잠깐 지워진다.
   * 실패하면 어디까지 되돌릴지 모르니 서버의 지금 값을 다시 받는다.
   */
  function save(
    optimistic: (before: Checklist) => Checklist,
    send: (centerId: number) => Promise<Checklist>,
    failed: string,
    onSaved?: () => void,
  ) {
    if (centerId === null) return;
    const id = centerId;
    setError("");
    setChecklist((before) => before && optimistic(before));
    waiting.current += 1;
    queue.current = queue.current.then(async () => {
      try {
        const next = await send(id);
        if (waiting.current === 1) setChecklist(next);
        onSaved?.();
      } catch (e) {
        setError(e instanceof Error ? e.message : failed);
        setReload((n) => n + 1);
      } finally {
        waiting.current -= 1;
      }
    });
  }

  const check = (element: string, checked: boolean) =>
    save(
      (before) => ({
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
      }),
      (id) => saveEvaluationChecks(id, [{ element, checked }]),
      "자체평가를 저장하지 못했어요.",
      () => setSavedAt(new Date()),
    );

  const toggleDoc = (doc: string, checked: boolean) =>
    save(
      (before) => ({
        ...before,
        documents: before.documents.map((d) => (d.doc === doc ? { ...d, checked } : d)),
      }),
      (id) => saveEvaluationDocuments(id, { checks: [{ doc, checked }] }),
      "직접확인을 저장하지 못했어요.",
    );

  const toggleDirector = (item: string, checked: boolean) =>
    save(
      (before) => ({
        ...before,
        director: before.director.map((d) => (d.item === item ? { ...d, checked } : d)),
      }),
      (id) => saveDirectorChecks(id, [{ item, checked }]),
      "원장님 서류 체크를 저장하지 못했어요.",
    );

  /** 새 폴더 — 이름은 화면에 두고, 서류마다 상태 · 숫자 · 기간만 서버에 남긴다. */
  function pickFolder(next: Scan) {
    setScan(next);
    const day = today();
    const results = TEACHER_DOCS.flatMap((doc) => {
      const result = next.results.find((r) => r.id === doc.id);
      return result ? [{ doc: doc.id, period: windowOf(doc, day), ...summarize(result) }] : [];
    });
    // 실패해도 이번 방문의 도장 · 근거 줄은 메모리의 결과로 그대로 보인다. 다시 열면 사라진다는 것만 알린다.
    save(
      (before) => before,
      (id) => saveEvaluationDocuments(id, { folder_scan: { results } }),
      "폴더 결과를 저장하지 못했어요. 다시 열면 폴더를 다시 골라야 해요.",
    );
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

  const rows = sheetRows(autos, scan, checklist.documents);
  // `date`(YYYY-MM-DD)는 시간대가 없어 잘라 써도 된다.
  const [, toMonth, toDay] = (autos[0]?.period.to ?? "").split("-").map(Number);
  const basis = `${checklist.school_year}학년도${toDay ? ` · ${toMonth}월 ${toDay}일까지 확정한 문서 기준` : ""}`;
  const recount = () => setReload((n) => n + 1);

  /*
   * 맨 위에 서류 도장판(전체 폭) — 평가 당일 교사가 꺼내는 단위가 서류여서 서류마다 칸 하나.
   * 그 아래 왼쪽에 채울 서류 카드 · 찍힌 서류 목록(시안 ⑤), 오른쪽 330px 칸에 폴더 쪽지(시안 ③)와 접힌 칸 셋(2026-11-08).
   * 오른쪽 칸은 페이지와 같이 스크롤한다 — 따로 스크롤하면 노트북 높이에서 접힌 칸이 안쪽 밑으로 숨었다.
   */
  return (
    <div className={ws.stack}>
      <Message error>{error}</Message>
      <StampBoard rows={rows} basis={basis} onToggle={toggleDoc} onRecount={recount} />
      <div className={`${ws.grid} ${styles.layout}`}>
        <EvaluationSheet rows={rows} onImported={recount} />
        <div className={styles.aside}>
          {/* 폴더 결과는 직접확인과 따로 저장한다 — 도장 근거 「내컴퓨터」 · 「직접확인」을 가르려고(ADR-074). */}
          <FolderCard scan={scan} documents={checklist.documents} onScan={pickFolder} />
          <DirectorFold checks={checklist.director} onToggle={toggleDirector} />
          <details className={styles.fold} aria-label="평가항목별로 보기">
            <summary>
              <FoldMark />
              평가항목별로 보기 · {autos.map((item) => item.indicator).join(" · ")}
            </summary>
            <div className={styles.foldBody}>
              <EvaluationAuto items={autos} onImported={recount} />
            </div>
          </details>
          {/* 도장 근거 「직접확인」과 이름이 겹쳐 바꿨다(시안 ⑤, 11-08). 쌤플이 세지 않는 평가항목을 선생님이 체크한다. */}
          <details className={styles.fold} aria-label="나머지 평가항목 체크">
            <summary>
              <FoldMark />
              나머지 평가항목 체크 · {checked} / {total}
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
      {/* 도장판 안에 있던 문장을 페이지 맨 아래로 뺐다(11-08). 도장은 서류가 있다는 표시일 뿐이다(ADR-019). */}
      <p className={styles.pageNote}>내용이 기준을 채웠는지는 선생님께서 한 번 더 확인해 주세요.</p>
    </div>
  );
}
