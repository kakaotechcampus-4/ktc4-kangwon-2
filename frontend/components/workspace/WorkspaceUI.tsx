"use client";
import { useEffect, useState, type ReactNode } from "react";
import { loadClassSettings } from "@/lib/onboarding/settings";
import { hydrateClassChildren } from "@/lib/api/onboarding";
import { useClientState } from "@/lib/hooks/use-client-state";
import type { ClassroomEntry } from "@/lib/onboarding/types";
import styles from "./Workspace.module.css";
export { styles as ws };
/**
 * 작업실 안쪽 화면들의 공통 머리. 제목은 손글씨로 크게, 설명은 한 줄.
 * `action` 은 그 화면의 주된 동작 하나만 — 둘 이상 두면 뭘 눌러야 할지 모른다.
 */
export function WorkspacePage({
  title,
  description,
  action,
  children,
}: {
  title: string;
  description: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <main className={styles.page}>
      <div className={styles.pageHead}>
        <div>
          <h1>{title}</h1>
          <p>{description}</p>
        </div>
        {action}
      </div>
      {children}
    </main>
  );
}
export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className={styles.empty}>
      <span aria-hidden="true">🌱</span>
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
export function Message({ children, error = false }: { children: ReactNode; error?: boolean }) {
  return children ? (
    <p className={error ? styles.error : styles.message} role={error ? "alert" : "status"}>
      {children}
    </p>
  ) : null;
}
const NO_CLASSES: ClassroomEntry[] = [];
export function useClasses(onError?: (message: string) => void) {
  const [classes, setClasses] = useClientState<ClassroomEntry[]>(
    () => loadClassSettings()?.classes || NO_CLASSES,
    NO_CLASSES,
  );
  useEffect(() => {
    let live = true;
    const settings = loadClassSettings();
    if (settings) {
      hydrateClassChildren(settings)
        .then((next) => {
          if (live) setClasses(next);
        })
        .catch(() => {
          if (live) onError?.("아동 명단을 불러오지 못했어요. 페이지를 새로고침해주세요.");
        });
    }
    return () => {
      live = false;
    };
  }, [setClasses, onError]);
  return classes;
}
export function useAIStatus() {
  const [available, setAvailable] = useState<boolean | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/assistant", { signal: controller.signal })
      .then(async (r) => {
        if (!r.ok) throw new Error();
        const data = await r.json();
        if (typeof data.available !== "boolean") throw new Error();
        setAvailable(data.available);
      })
      .catch(() => {});
    return () => controller.abort();
  }, []);
  return available;
}
export function AIHint({ available }: { available: boolean | null }) {
  return (
    <p className={styles.hint}>
      {available === null
        ? "AI 연결 상태 확인 중이에요. 응답이 없으면 잠시 후 페이지를 새로고침해주세요."
        : available
          ? "AI 연결됨 · 선택한 자료를 바탕으로 초안을 작성해요."
          : "직접 작성 모드 · AI 연결 전에도 기록 입력, 문서 작성과 기본 점검을 사용할 수 있어요."}
    </p>
  );
}
