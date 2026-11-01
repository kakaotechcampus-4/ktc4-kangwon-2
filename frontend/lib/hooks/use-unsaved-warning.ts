import { useEffect } from "react";

/**
 * 저장하지 않은 것이 남아 있으면 화면을 떠날 때 브라우저가 한 번 묻는다.
 *
 * 반은 사이드바에서 바꾸고, 바꾸면 화면을 다시 읽는다 — 즉 떠난다. 화면 안에 있던
 * 「저장하지 않은 게 사라져요」 확인이 그 길에는 없으므로 브라우저 쪽에 걸어 둔다.
 * 새로고침 · 탭 닫기 · 주소 바꾸기도 같이 막아 준다.
 */
export function useUnsavedWarning(unsaved: boolean) {
  useEffect(() => {
    if (!unsaved) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [unsaved]);
}
