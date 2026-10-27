"use client";

import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { getCurrentUser } from "@/lib/api/auth";
import {
  getEvaluationChecklist,
  saveEvaluationChecks,
  type AutoIndicator,
  type EvaluationChecklist as Checklist,
  type SelfCheckIndicator,
} from "@/lib/api/evaluation";
import { useClientState } from "@/lib/hooks/use-client-state";
import { Message, ws } from "./WorkspaceUI";
import EvaluationAuto from "./EvaluationAuto";
import EvaluationSelfCheck from "./EvaluationSelfCheck";
import styles from "./Evaluation.module.css";

const TABS = ["docs", "self"] as const;
type Tab = (typeof TABS)[number];

/** 고른 탭은 주소(?tab=)에 남긴다. 새로고침하거나 다른 화면에 다녀와도 같은 탭이 열린다. */
function readTab(): Tab {
  if (typeof window === "undefined") return "docs";
  const tab = new URLSearchParams(window.location.search).get("tab");
  return TABS.find((t) => t === tab) ?? "docs";
}

/** Official indicators and saved checks come from §12, never from browser-local documents. */
export default function EvaluationChecklist({
  refresh,
  children,
}: {
  /** 화면 머리의 「현황 새로고침」이 올리는 수. 바뀌면 다시 불러온다. */
  refresh: number;
  children?: ReactNode;
}) {
  const [checklist, setChecklist] = useState<Checklist | null>(null);
  const [centerId, setCenterId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const [initiallyOpen, setInitiallyOpen] = useState(new Set<string>());
  const [reload, setReload] = useState(0);
  const [tab, setTab] = useClientState<Tab>(readTab, "docs");
  const running = useRef(false);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

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
          setError(e instanceof Error ? e.message : "평가 준비 현황을 불러오지 못했어요.");
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

  function choose(next: Tab) {
    setTab(next);
    const url = new URL(window.location.href);
    url.searchParams.set("tab", next);
    window.history.replaceState(null, "", url);
  }

  // 탭은 화살표 · Home · End 로 옮긴다(WAI-ARIA Tabs).
  function moveTab(e: KeyboardEvent, index: number) {
    const keys: Record<string, number> = {
      ArrowRight: index + 1,
      ArrowLeft: index - 1,
      Home: 0,
      End: TABS.length - 1,
    };
    if (!(e.key in keys)) return;
    e.preventDefault();
    const next = (keys[e.key] + TABS.length) % TABS.length;
    choose(TABS[next]);
    tabRefs.current[next]?.focus();
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

  const autos = checklist.items.filter((item): item is AutoIndicator => item.kind === "AUTO");
  const selfs = checklist.items.filter(
    (item): item is SelfCheckIndicator => item.kind === "SELF_CHECK",
  );
  const supported = autos.filter((item) => item.verdict === "SUPPORTED").length;
  const checked = selfs.reduce((sum, item) => sum + item.progress.checked, 0);
  const total = selfs.reduce((sum, item) => sum + item.progress.total, 0);
  // 다 채운 칸은 숫자 대신 「✓ 완료」. 아래 줄은 무엇을 채웠는지만 말한다 — 평가 통과가 아니다(ADR-022).
  const DONE = "✓ 완료";
  const tiles: Record<Tab, [label: string, value: string, sub: string]> = {
    docs: [
      "문서로 확인하는 평가항목",
      autos.length && supported === autos.length ? DONE : `${supported} / ${autos.length}`,
      autos.every((item) => item.verdict === "NONE")
        ? "아직 확정된 문서가 없어요. 문서를 확정하면 여기서 세요"
        : supported === autos.length
          ? "기준 건수를 채웠어요"
          : `보완 필요 ${autos.length - supported}개`,
    ],
    self: [
      "자체평가",
      total && checked === total ? DONE : `${checked} / ${total}`,
      checked < total ? `확인할 평가요소 ${total - checked}개` : "모두 확인했어요",
    ],
  };

  return (
    <div className={ws.stack}>
      <p className={styles.basis}>
        {checklist.school_year}학년도
        {autos[0] && ` · ${autos[0].period.to}까지 확정한 문서 기준`}
      </p>
      <Message error>{error}</Message>
      <div role="tablist" aria-label="평가 준비 보기" className={styles.tabs}>
        {TABS.map((id, index) => (
          <button
            key={id}
            ref={(node) => {
              tabRefs.current[index] = node;
            }}
            type="button"
            role="tab"
            id={`eval-tab-${id}`}
            aria-selected={tab === id}
            aria-controls={`eval-panel-${id}`}
            tabIndex={tab === id ? 0 : -1}
            className={`${styles.tab} ${styles[id]}`}
            onClick={() => choose(id)}
            onKeyDown={(e) => moveTab(e, index)}
          >
            <span className={styles.tabLabel}>{tiles[id][0]}</span>
            <span className={styles.tabValue}>{tiles[id][1]}</span>
            <span className={styles.tabSub}>{tiles[id][2]}</span>
          </button>
        ))}
      </div>
      <div
        role="tabpanel"
        id="eval-panel-docs"
        aria-labelledby="eval-tab-docs"
        hidden={tab !== "docs"}
      >
        <EvaluationAuto items={autos} />
      </div>
      <div
        role="tabpanel"
        id="eval-panel-self"
        aria-labelledby="eval-tab-self"
        hidden={tab !== "self"}
      >
        <EvaluationSelfCheck
          items={selfs}
          savedAt={savedAt}
          initiallyOpen={initiallyOpen}
          onCheck={check}
        >
          {children}
        </EvaluationSelfCheck>
      </div>
    </div>
  );
}
