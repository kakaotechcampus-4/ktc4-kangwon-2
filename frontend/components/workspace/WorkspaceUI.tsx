"use client";
import { useEffect, type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { loadClassSettings, saveClassSettings } from "@/lib/onboarding/settings";
import { adoptServerClasses, hydrateClassChildren } from "@/lib/api/onboarding";
import { useClientState } from "@/lib/hooks/use-client-state";
import { EMPTY_CLASS_SETTINGS, type ClassroomEntry } from "@/lib/onboarding/types";
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
/**
 * 보육일지 메뉴 안의 두 화면 — 일일(일과를 적고 그날 일지)과 주간(한 주 일지).
 * 주간 기록이 메뉴 하나를 따로 차지했는데 일과 목록을 다시 보여 줄 뿐이라 합쳤다(13주차 멘토 리뷰).
 */
export function JournalTabs({
  at,
  daily,
  weekly,
}: {
  at: "daily" | "weekly";
  daily: string;
  weekly: string;
}) {
  return (
    <nav aria-label="보육일지 종류" className={styles.journalTabs} data-tour="journal-tabs">
      <Link href={daily} className="tap44" aria-current={at === "daily" ? "page" : undefined}>
        일일 보육일지
      </Link>
      <Link href={weekly} className="tap44" aria-current={at === "weekly" ? "page" : undefined}>
        주간 보육일지
      </Link>
    </nav>
  );
}

/** 종이를 붙여 둔 테이프 한 조각. 기록 · 계획안 화면의 첫 판에 붙인다. 부모는 relative 여야 한다. */
export function Tape() {
  return <span aria-hidden="true" className={styles.tape} />;
}
export function Empty({
  title,
  children,
  art,
}: {
  title: string;
  children?: ReactNode;
  /** 새싹 대신 세울 그림. 포스티가 말을 거는 화면에서 쓴다. */
  art?: ReactNode;
}) {
  return (
    <div className={styles.empty}>
      {art ?? <span aria-hidden="true">🌱</span>}
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
export function Message({
  children,
  error = false,
  id,
  onClose,
}: {
  children: ReactNode;
  error?: boolean;
  /** 입력 칸이 `aria-errormessage` 로 이 글을 가리킬 때 쓴다. */
  id?: string;
  /** 있으면 오른쪽에 × 단추를 단다. 단추는 알림 글(role) 밖에 둔다 — 「안내 닫기」까지 읽히지 않게. */
  onClose?: () => void;
}) {
  if (!children) return null;
  const line = (
    <p id={id} className={error ? styles.error : styles.message} role={error ? "alert" : "status"}>
      {children}
    </p>
  );
  if (!onClose) return line;
  return (
    <div className={styles.messageBar}>
      {line}
      <button
        type="button"
        className={`${styles.messageClose} tap44`}
        aria-label="안내 닫기"
        onClick={onClose}
      >
        ×
      </button>
    </div>
  );
}
const NO_CLASSES: ClassroomEntry[] = [];
/**
 * 스르륵 올라왔다 4.5초 뒤 스스로 사라지는 한 줄 알림.
 *
 * 화면을 막을 일은 아니지만 교사가 바로 알아야 하는 말 — 「시간이 겹쳐요」,
 * 「왜 이 단추가 안 눌리나」 같은 것. 흐린 단추만 두면 고장으로 읽힌다.
 */
export function Notice({ children, onDone }: { children: string; onDone: () => void }) {
  useEffect(() => {
    if (!children) return;
    const timer = setTimeout(onDone, 4500);
    return () => clearTimeout(timer);
    // `onDone` 은 매 렌더 새 함수다. 넣으면 다시 그릴 때마다 시계가 처음부터 돈다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [children]);
  if (!children) return null;
  return (
    <p className={styles.toast} role="status">
      <svg className={styles.toastMark} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" strokeWidth="1.8" />
        <path d="M12 7v6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <circle cx="12" cy="16.6" r="1.15" fill="currentColor" />
      </svg>
      {children}
    </p>
  );
}
/**
 * 이 교사가 쓸 반 목록. 작업실 화면들이 전부 이걸 쓴다.
 *
 * **브라우저 저장소에 있는 반 + 서버에만 있는 반**을 합친다. 저장소만 보면
 * 기기를 바꾼 교사에게 반이 하나도 안 보인다 — 서버에는 멀쩡히 있는데도.
 */
export function useClasses(onError?: (message: string) => void) {
  const [classes, setClasses] = useClientState<ClassroomEntry[]>(
    () => loadClassSettings()?.classes || NO_CLASSES,
    NO_CLASSES,
  );
  const pathname = usePathname();
  useEffect(() => {
    let live = true;
    const settings = loadClassSettings();
    (async () => {
      const local = settings ? await hydrateClassChildren(settings) : NO_CLASSES;
      if (!live) return;
      if (local.length) setClasses(local);
      // 서버에만 있는 반을 뒤에 붙인다. 이게 실패해도 로컬 반은 이미 그려져 있다.
      // **저장을 adopt 안에서 먼저 한다.** 연결보다 반 목록이 먼저 남아야 한다 —
      // 반대로 끊기면 「연결은 있는데 목록에 없는 반」이 되어 영영 안 들어온다.
      // 화면을 떠났어도 저장은 한다. 사이드바·홈도 저장소를 본다.
      let next = local;
      await adoptServerClasses(
        local,
        (name) =>
          onError?.(`${name || "반"}의 아동 명단을 못 불러왔어요. 페이지를 새로고침해주세요.`),
        (rows, dropped) => {
          // 남의 반이 된 것은 뺀다 — 들인 반이 없어도 저장 · 화면 갱신이 필요하다.
          next = [...local.filter((c) => !dropped.includes(c.id)), ...rows];
          saveClassSettings({ ...(settings ?? EMPTY_CLASS_SETTINGS), classes: next });
        },
      );
      // 같은 화면의 다른 useClasses(사이드바 등)가 먼저 들였으면 여기서는 「연결은 있는데
      // 목록에 없는 반」이라 건너뛴다. 그쪽이 목록을 먼저 저장했으니 저장소에서 받는다.
      const stored = loadClassSettings();
      const extra = stored?.classes.filter((c) => !next.some((n) => n.id === c.id)) ?? [];
      if (stored && extra.length)
        next = [...next, ...(await hydrateClassChildren({ ...stored, classes: extra }))];
      if (next !== local && live) setClasses(next);
    })().catch(() => {
      if (live) onError?.("반 정보를 불러오지 못했어요. 페이지를 새로고침해주세요.");
    });
    return () => {
      live = false;
    };
    // 화면을 옮길 때마다 다시 맞춘다. 사이드바는 화면을 옮겨도 다시 붙지 않아서(DemoSessionGate),
    // 주소를 안 보면 그사이 서버에 생긴 반이 새로고침 전까지 반 고르개에 안 뜬다.
  }, [setClasses, onError, pathname]);
  return classes;
}
