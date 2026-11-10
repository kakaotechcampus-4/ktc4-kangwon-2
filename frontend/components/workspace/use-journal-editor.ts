import { useCallback, useState } from "react";
import { useUnsavedWarning } from "@/lib/hooks/use-unsaved-warning";

/** 다른 날짜·반의 일지를 새 기간 아래에 붙이지 않고, 떠나기 전에 미저장 글을 확인한다. */
export function useJournalEditor(scope: string, generating: boolean) {
  const [opened, setOpened] = useState<{ scope: string; id: string } | null>(null);
  const [editing, setEditing] = useState<{
    scope: string;
    id: string;
    dirty: boolean;
    pending: boolean;
  } | null>(null);
  const openId = opened?.scope === scope ? opened.id : "";
  const current = editing?.scope === scope && editing.id === openId ? editing : null;
  const pending = generating || !!current?.pending;
  useUnsavedWarning(!!current?.dirty || pending);
  const onEditStateChange = useCallback(
    (state: { dirty: boolean; pending: boolean }) => setEditing({ scope, id: openId, ...state }),
    [scope, openId],
  );

  function leave() {
    if (pending) return false;
    if (current?.dirty && !window.confirm("저장하지 않은 일지 내용이 사라져요. 옮길까요?"))
      return false;
    setOpened(null);
    return true;
  }

  return {
    openId,
    pending,
    open: (id: string) => setOpened({ scope, id }),
    close: leave,
    leave,
    // 삭제 완료 뒤에는 저장 중 잠금과 무관하게 사라진 문서를 닫는다.
    dismiss: () => setOpened(null),
    onEditStateChange,
  };
}
