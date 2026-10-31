"use client";

import { useEffect, useRef, useState, type ChangeEvent } from "react";
import workspace from "@/components/workspace/Workspace.module.css";

export const MAX_CELL_LENGTH = 600;
/** 입력을 멈춘 뒤 저장하기까지. */
export const SAVE_DELAY_MS = 1000;

const isSavable = (raw: string, allowBlank: boolean, maxLength: number) => {
  const length = [...raw.trim()].length;
  return (allowBlank || length > 0) && length <= maxLength;
};

/**
 * 칸 하나의 입력창 (ADR-044 §2). 칸이 바뀌면 부모가 `key` 로 새로 만든다.
 * 입력을 1초 멈추거나 칸을 떠나면(blur) 앞뒤 공백을 턴 값으로 저장한다.
 * 비었거나(`allowBlank` 면 빈 값은 저장한다) `maxLength`(기본 600자)를 넘으면 저장하지 않고, 떠날 때 마지막 저장값(`value`)으로 되돌린다.
 */
export default function PlayCellEditor({
  id,
  label,
  value,
  onDraft,
  onSave,
  onRevert,
  allowBlank = false,
  maxLength = MAX_CELL_LENGTH,
  readOnly,
}: {
  id: string;
  label: string;
  /** 마지막으로 저장한 값. */
  value: string;
  /** 입력할 때마다 — 문서 미리보기가 바로 따라간다. */
  onDraft: (text: string) => void;
  /** 저장할 만한 값(앞뒤 공백을 턴 1~600자). 마지막 저장값과 같은지는 부모가 본다. */
  onSave: (text: string) => void;
  /** 되돌렸다 — 미리보기도 마지막 저장값으로. */
  onRevert: () => void;
  /** 빈 값도 저장한다(놀이 월간). 기본은 거절 — 연간 동작 그대로. */
  allowBlank?: boolean;
  /** 글자 수 상한. 월간 v1 칸은 상한이 없다(Infinity). */
  maxLength?: number;
  /** 고칠 수 없다(놀이 월간 확정 중). 기본은 고칠 수 있다. */
  readOnly?: boolean;
}) {
  const [text, setText] = useState(value);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // 아직 저장도 되돌림도 안 한 입력이 있는가와 그 글. 입력창이 blur 없이 사라질 때만 쓴다.
  const pending = useRef<string | null>(null);
  const latest = useRef({ onSave, onRevert, allowBlank, maxLength });
  const length = [...text.trim()].length; // 서버는 글자(코드포인트) 수로 센다.
  const blank = length === 0 && !allowBlank;
  const over = length > maxLength;
  const overText = `${maxLength}자를 넘으면 저장되지 않아요`;

  useEffect(() => {
    latest.current = { onSave, onRevert, allowBlank, maxLength };
  });
  useEffect(
    () => () => {
      clearTimeout(timer.current ?? undefined);
      const raw = pending.current;
      if (raw === null) return;
      // blur 없이 사라졌다(탭 · 칸이 바뀌어 새로 그려짐) — 저장할 만하면 보내고, 아니면 미리보기를 되돌린다.
      if (isSavable(raw, latest.current.allowBlank, latest.current.maxLength))
        latest.current.onSave(raw.trim());
      else latest.current.onRevert();
    },
    [],
  );

  function change(event: ChangeEvent<HTMLTextAreaElement>) {
    const next = event.target.value;
    setText(next);
    pending.current = next;
    onDraft(next);
    clearTimeout(timer.current ?? undefined);
    timer.current = setTimeout(() => saveIfValid(next), SAVE_DELAY_MS);
  }

  function saveIfValid(raw: string) {
    if (!isSavable(raw, allowBlank, maxLength)) return;
    pending.current = null;
    onSave(raw.trim());
  }

  function leave() {
    clearTimeout(timer.current ?? undefined);
    pending.current = null;
    if (!blank && !over) return onSave(text.trim());
    setText(value);
    onRevert();
  }

  return (
    <>
      <label htmlFor={id}>{label}</label>
      <textarea
        id={id}
        value={text}
        readOnly={readOnly}
        aria-invalid={blank || over}
        aria-describedby={`${id}-count`}
        onChange={change}
        onBlur={leave}
      />
      <p id={`${id}-count`} className={workspace.muted}>
        {length}
        {Number.isFinite(maxLength) ? `/${maxLength}` : ""}자{over ? ` · ${overText}` : ""}
      </p>
      <p role="status">{blank ? "비워 둘 수 없어요" : over ? overText : ""}</p>
    </>
  );
}
