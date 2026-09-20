"use client";
import { useEffect, useState, type ReactNode } from "react";
import AppHeader from "@/components/app/AppHeader";
import { loadClassSettings } from "@/lib/onboarding/settings";
import { useClientState } from "@/lib/hooks/use-client-state";
import type { ClassroomEntry } from "@/lib/onboarding/types";
import styles from "./Workspace.module.css";
export { styles as ws };
export function WorkspacePage({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <>
      <AppHeader
        title={title}
        description={description}
        divider={false}
        tools={<span className={styles.badge}>🌱 우리 반의 하루를 차곡차곡</span>}
      />
      <main className={styles.page}>{children}</main>
    </>
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
export function useClasses() {
  const [classes] = useClientState<ClassroomEntry[]>(
    () => loadClassSettings()?.classes || NO_CLASSES,
    NO_CLASSES,
  );
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
