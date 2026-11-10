"use client";

/**
 * 서버 문서 하나를 열고 고치고 확정하는 한 벌.
 *
 * 문서 보관함만 이 일을 할 수 있던 것은 보관함 화면 안에 선택 · 요청 상태가 묶여 있어서였다.
 * 문서를 만든 화면에서 바로 이어 쓰려면 같은 한 벌이 필요하다 — 보관함에 있던 것을 여기로 옮긴다.
 */

import { useEffect, useState, useSyncExternalStore } from "react";
import {
  confirmDocument,
  deleteDocument,
  documentServerId,
  getDocument,
  reconfirmDocument,
  refreshDocument,
  unconfirmDocument,
  updateDocument,
  verifyDocument,
  type ReconfirmInput,
  type SourceResolution,
} from "@/lib/api/documents";
import { isUnauthenticated } from "@/lib/api/client";
import type { SavedDocument, Section } from "@/lib/workspace/model";
import { createSelection } from "./document-selection";
import type { ServerDocumentActions } from "./DocumentEditor";

export function messageFor(error: unknown) {
  if (isUnauthenticated(error)) return "로그인이 필요해요. 다시 로그인한 뒤 이용해주세요.";
  return error instanceof Error ? error.message : "요청을 처리하지 못했어요.";
}

const GATEWAY = {
  get: getDocument,
  update: updateDocument,
  confirm: confirmDocument,
  unconfirm: unconfirmDocument,
  refresh: refreshDocument,
  reconfirm: reconfirmDocument,
  remove: deleteDocument,
};

/**
 * `localId` 가 비면 아무것도 부르지 않는다. 문서가 바뀌면 열던 것을 놓고 새로 받는다.
 * `onChanged` 는 저장 · 확정 · 삭제가 끝난 뒤 — 목록을 들고 있는 쪽이 다시 세라고 부른다.
 * `onRemoved` 는 삭제한 뒤에만 — 편집기를 닫을 쪽이 받는다.
 */
export function useServerDocument(
  localId: string,
  { onChanged, onRemoved }: { onChanged?: () => void; onRemoved?: () => void } = {},
) {
  const [selection] = useState(() => createSelection(GATEWAY, messageFor));
  const chosen = useSyncExternalStore(selection.subscribe, selection.get, selection.get);

  useEffect(() => {
    selection.select(localId, documentServerId(localId));
  }, [localId, selection]);

  const doc = chosen.detail?.id === localId ? chosen.detail : null;
  const then = async <T>(work: Promise<T>) => {
    const next = await work;
    onChanged?.();
    return next;
  };

  // 지금 연 문서에 묶인 작업. 저장과 반영 사이 다른 문서를 열어도 뒤 작업이 새 문서로 가지 않는다.
  const pinned = selection.pin();
  const server: ServerDocumentActions | undefined = doc
    ? {
        stale: doc.stale,
        pending: chosen.pending !== "",
        reload: pinned.reload,
        reconfirm: (input: ReconfirmInput) => then(pinned.reconfirm(input)),
        save: (sections: Section[], reviewNote: string, classNote?: string) =>
          then(pinned.save(sections, reviewNote, classNote)),
        saveAndConfirm: (sections: Section[], reviewNote: string, classNote?: string) =>
          then(pinned.saveAndConfirm(sections, reviewNote, classNote)),
        unconfirm: () => then(pinned.unconfirm()),
        refresh: (resolutions?: SourceResolution[]) => then(pinned.refresh(resolutions)),
        // 판정만 한다 — 저장 · 확정과 겹쳐도 문서를 바꾸지 않아 selection 의 순서 잠금을 타지 않는다.
        verify: (sections: Section[]) => verifyDocument(localId, doc.kind, sections),
        remove: async () => {
          await then(pinned.remove());
          onRemoved?.();
        },
      }
    : undefined;

  return {
    doc: doc as SavedDocument | null,
    status: chosen.status,
    error: chosen.error,
    server,
  };
}
