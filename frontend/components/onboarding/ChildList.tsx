"use client";

import { useState } from "react";
import type { ChildEntry } from "@/lib/onboarding/types";
import { TextInput } from "./FormField";
import { GhostButton } from "./PrimaryButton";

/** 이름 중심의 단순한 아동 명단. (items는 JSX children이 아니라 데이터 배열이다) */
export default function ChildList({
  items,
  onAdd,
  onRemove,
  locked = false,
  idPrefix = "child",
}: {
  items: ChildEntry[];
  /** 법정대리인 동의를 체크하지 않은 반이면 이름을 넣지 못하게 막는다 */
  locked?: boolean;
  onAdd: (name: string) => void | Promise<void>;
  onRemove: (id: string) => void;
  idPrefix?: string;
}) {
  const [draft, setDraft] = useState("");
  const [dup, setDup] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit() {
    if (busy || locked) return;
    const name = draft.trim();
    if (!name) return;
    if (items.some((c) => c.name === name)) {
      setDup(true);
      return;
    }
    setBusy(true);
    setError("");
    // 저장을 기다리지 않고 칸부터 비운다. 그 사이 치는 다음 이름이 앞 이름에 붙지 않게
    setDraft("");
    setDup(false);
    try {
      await onAdd(name);
    } catch (e) {
      setDraft((d) => d || name);
      setError(e instanceof Error ? e.message : "추가하지 못했어요.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    setBusy(true);
    setError("");
    try {
      await onRemove(id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "삭제하지 못했어요.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <label htmlFor={`${idPrefix}-name`} className="font-semibold text-[15px] text-ink">
          아동 추가
        </label>
        <div className="flex gap-2">
          <TextInput
            id={`${idPrefix}-name`}
            value={draft}
            // 저장하는 동안에도 잠그지 않는다. 잠그면 커서가 빠지거나 그 사이 친 글자가 사라진다
            disabled={locked}
            placeholder={
              locked ? "반 정보에서 법정대리인 동의를 먼저 체크해주세요" : "아동 이름 입력 후 Enter"
            }
            aria-invalid={dup || undefined}
            onChange={(e) => {
              setDraft(e.target.value);
              setDup(false);
            }}
            onKeyDown={(e) => {
              if (
                e.key === "Enter" &&
                !e.nativeEvent.isComposing &&
                e.nativeEvent.keyCode !== 229
              ) {
                e.preventDefault();
                submit();
              }
            }}
            className={`flex-1 ${dup ? "border-peach-strong" : ""}`}
          />
          <GhostButton onClick={submit} disabled={busy || locked} className="shrink-0">
            + 추가
          </GhostButton>
        </div>
        {error && (
          <p role="alert" className="text-[12.5px] text-peach-ink">
            {error}
          </p>
        )}
        <p role="status" className="sr-only">
          {busy ? "명단을 저장하고 있어요." : ""}
        </p>
        {dup && (
          <p className="text-[12.5px] text-peach-ink">
            이미 같은 이름이 등록되어 있어요. 구분이 필요하면 성을 붙여 입력해주세요.
          </p>
        )}
      </div>

      <div className="flex flex-col gap-2">
        <span className="font-semibold text-[15px] text-ink">
          아동 명단
          <span className="ml-1.5 align-middle font-mono text-[12px] px-2 py-0.5 rounded-full bg-mint-tint text-mint-ink">
            {items.length}명
          </span>
        </span>

        {/* 처음부터 4칸 높이로 둔다 — 넣을 때마다 칸이 늘어나 아래 버튼이 밀리지 않게. 5명부터는 칸 안에서 스크롤.
            방금 넣은 아이가 맨 위. 번호는 지금 명단 안에서 등록한 순서라 지우면 당겨지고, 다 지우면 01부터 */}
        <ul className="h-[calc(4*3.5rem+3px)] overflow-y-auto rounded-md border-[1.5px] border-line divide-y divide-line bg-paper">
          {items
            .map((c, i) => ({ c, no: i + 1 }))
            .reverse()
            .map(({ c, no }) => (
              <li key={c.id} className="flex h-14 items-center gap-3 px-3.5">
                <span className="font-mono text-[12px] text-ink-soft w-[22px]">
                  {String(no).padStart(2, "0")}
                </span>
                <span
                  aria-hidden="true"
                  className="inline-flex items-center justify-center w-[34px] h-[34px] rounded-full bg-mint-tint text-mint-ink text-[13px] font-bold shrink-0"
                >
                  {c.name.slice(-2)}
                </span>
                <span className="flex-1 text-[14.5px] text-ink">{c.name}</span>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => remove(c.id)}
                  aria-label={`${c.name} 삭제`}
                  className="min-h-[36px] min-w-[44px] px-2.5 rounded-full text-[12.5px] text-ink-soft hover:text-peach-ink hover:bg-peach-tint transition-colors disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
                >
                  삭제
                </button>
              </li>
            ))}
          {Array.from({ length: Math.max(0, 4 - items.length) }, (_, i) => (
            <li
              key={`empty-${i}`}
              aria-hidden="true"
              className="flex h-14 items-center gap-3 px-3.5"
            >
              <span className="w-[22px]" />
              <span className="w-[34px] h-[34px] rounded-full border-[1.5px] border-dashed border-line shrink-0" />
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
