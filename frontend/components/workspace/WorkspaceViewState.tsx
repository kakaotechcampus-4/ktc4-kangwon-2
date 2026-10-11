"use client";
import type { ReactNode } from "react";
import { Message, ws } from "./WorkspaceUI";

/** 비동기 조회 화면이 쓰는 상태. document-selection 의 DetailStatus 와 같은 세 값이다. */
export type ViewStatus = "loading" | "ready" | "error";

/**
 * 불러오는 중 · 실패 · 비었음 · 성공을 한 곳에서 가른다.
 *
 * 문구는 화면이 준다 — 화면마다 계약 문구가 달라서 여기서 만들면 그 계약이 흩어진다.
 */
export function WorkspaceViewState({
  status,
  loading,
  error,
  empty,
  children,
}: {
  status: ViewStatus;
  /** 불러오는 중에 보일 문장. */
  loading: string;
  /** 서버가 준 문구를 그대로 넘긴다. 화면에서 다시 쓰지 않는다. */
  error?: string;
  /** 비었을 때 그릴 것. `false` 나 생략이면 비어 있지 않다. */
  empty?: ReactNode;
  children: ReactNode;
}) {
  if (status === "loading")
    return (
      <div className={ws.loading} aria-busy="true">
        <span>🌱</span>
        <p>{loading}</p>
      </div>
    );
  if (status === "error") return <Message error>{error}</Message>;
  if (empty) return <>{empty}</>;
  return <>{children}</>;
}

export const fieldErrorId = (name: string) => `invalid-${name}`;

/**
 * 서버가 VALIDATION_FAILED 로 짚은 입력 칸 표시 (docs/api-spec.md 「공통 에러 형식」).
 *
 * 서버는 칸마다가 아니라 요청 하나에 message 를 한 번 준다. 그 문장은 화면 위쪽에
 * 이미 나오므로 여기서는 어느 칸인지만 알린다.
 */
export function FieldError({ name, invalid }: { name: string; invalid: string[] }) {
  return invalid.includes(name) ? (
    <small id={fieldErrorId(name)} role="alert" className={ws.fieldError}>
      이 항목을 확인해주세요.
    </small>
  ) : null;
}

/** 틀린 칸에만 붙는 접근성 속성. 값이 `undefined` 면 속성 자체가 안 나간다. */
export function fieldErrorProps(name: string, invalid: string[]) {
  const bad = invalid.includes(name);
  return {
    "aria-invalid": bad || undefined,
    "aria-describedby": bad ? fieldErrorId(name) : undefined,
  };
}
