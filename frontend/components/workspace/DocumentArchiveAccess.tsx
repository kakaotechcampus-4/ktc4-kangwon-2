"use client";
/**
 * 같은 원 다른 반의 열람 요청 · 승인 (ADR-059 · docs/api-spec.md §2-2).
 *
 * 보관함 안에서만 쓴다. 승인 전에는 **요약(`archive-summary`)만** 그린다 — 제목 · 아이 이름 ·
 * 문서 id 가 없는 응답이라 화면도 종류 · 기간 · 상태 말고는 그릴 것이 없다.
 */
import { DOCUMENT_KINDS } from "@/lib/workspace/model";
import { ARCHIVE_STATUS_LABEL, planStatus } from "@/lib/workspace/document-archive";
import type { ArchiveSummaryItem, ClassAccess, ReceivedAccessRequest } from "@/lib/api/types";
import { Icon } from "@/components/app/icons";
import { ws } from "./WorkspaceUI";
import styles from "./DocumentArchive.module.css";

/** 승인이 있어야 읽는 상태. OWNER · OPEN · APPROVED 는 읽는다. */
export type LockedAccess = Extract<ClassAccess, "NONE" | "PENDING" | "REJECTED" | "REVOKED">;
export const isLocked = (access: ClassAccess | undefined): access is LockedAccess =>
  access === "NONE" || access === "PENDING" || access === "REJECTED" || access === "REVOKED";

export const ACCESS_REQUIRED_MESSAGE = "이 반의 문서를 보려면 담당 선생님의 승인이 필요해요.";
export const READ_ONLY_MESSAGE = "다른 반의 문서는 열람만 할 수 있어요.";

/** 보관함 종류 칸 → 요약의 `kind`. 영유아 평가는 다섯 칸에 없어 「전체」에서만 보인다. */
const KINDS_OF: Record<string, ArchiveSummaryItem["kind"][]> = {
  annual: ["annual"],
  monthly: ["monthly"],
  weekly: ["weekly"],
  care: ["dailyLog", "weeklyLog"],
  observation: ["observation"],
};

const ACCESS_STATE: Record<LockedAccess, string> = {
  NONE: "아직 열람을 요청하지 않았어요.",
  PENDING: "열람을 요청했어요. 담당 선생님의 승인을 기다리고 있어요.",
  REJECTED: "열람 요청이 거절됐어요. 다시 요청할 수 있어요.",
  REVOKED: "담당 선생님이 열람 승인을 취소했어요. 다시 요청할 수 있어요.",
};
const REQUEST_LABEL: Record<LockedAccess, string> = {
  NONE: "열람 요청",
  PENDING: "승인 대기 중",
  REJECTED: "다시 요청",
  REVOKED: "다시 요청",
};

export type SummaryState =
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "ready"; items: ArchiveSummaryItem[] };

const period = (item: ArchiveSummaryItem) =>
  item.start === item.end ? item.start : `${item.start} ~ ${item.end}`;

/** 승인 전 반의 본문. 요청 단추와 그 반의 문서 요약. */
export function LockedClassPanel({
  className,
  access,
  type,
  summary,
  requesting,
  message,
  onRequest,
  onRetrySummary,
}: {
  className: string;
  access: LockedAccess;
  /** 보관함에서 고른 종류. null 이면 전체. */
  type: string | null;
  summary: SummaryState;
  requesting: boolean;
  message: string;
  onRequest: () => void;
  onRetrySummary: () => void;
}) {
  return (
    <section className={`${styles.panel} ${styles.accessPanel}`} aria-label="열람 요청">
      <div className={styles.accessHead}>
        <span className={styles.accessIcon}>
          <Icon name="lock" />
        </span>
        <div>
          <h3>{ACCESS_REQUIRED_MESSAGE}</h3>
          <p className={ws.muted} role="status">
            {className} · {ACCESS_STATE[access]}
          </p>
        </div>
        <button
          type="button"
          className={ws.primary}
          disabled={requesting || access === "PENDING"}
          onClick={onRequest}
        >
          {requesting ? "요청 보내는 중…" : REQUEST_LABEL[access]}
        </button>
      </div>
      {message && (
        <p className={styles.accessMessage} role="status">
          {message}
        </p>
      )}
      <SummaryList type={type} summary={summary} onRetry={onRetrySummary} />
    </section>
  );
}

function SummaryList({
  type,
  summary,
  onRetry,
}: {
  type: string | null;
  summary: SummaryState;
  onRetry: () => void;
}) {
  if (summary.status === "loading") return <p role="status">문서 요약을 불러오고 있어요.</p>;
  if (summary.status === "error")
    return (
      <div>
        <p role="alert">문서 요약을 불러오지 못했어요. {summary.error}</p>
        <button type="button" className={ws.secondary} onClick={onRetry}>
          요약 다시 불러오기
        </button>
      </div>
    );
  const kinds = type ? KINDS_OF[type] : null;
  const items = kinds ? summary.items.filter((i) => kinds.includes(i.kind)) : summary.items;
  return (
    <div className={styles.summary}>
      <div className={styles.summaryHead}>
        <h4>등록된 문서 {items.length}건</h4>
        <span className={ws.muted}>제목과 내용은 승인을 받은 뒤에 볼 수 있어요.</span>
      </div>
      {items.length ? (
        <ul className={styles.summaryList}>
          {items.map((item, i) => (
            // 요약에는 id 가 없다 — 같은 종류 · 기간 · 상태가 겹칠 수 있어 순서를 같이 쓴다.
            <li key={`${item.kind}|${item.start}|${item.end}|${item.status}|${i}`}>
              <span className={styles.summaryKind}>{DOCUMENT_KINDS[item.kind] ?? item.kind}</span>
              <span className={styles.summaryPeriod}>{period(item)}</span>
              <span className={styles.status} data-state={planStatus(item.status)}>
                {ARCHIVE_STATUS_LABEL[planStatus(item.status)]}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className={styles.summaryEmpty}>등록된 문서가 없어요.</p>
      )}
    </div>
  );
}

export type ReceivedState =
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "ready"; items: ReceivedAccessRequest[] };

const REQUEST_STATE: Record<ReceivedAccessRequest["status"], string> = {
  PENDING: "승인 대기",
  APPROVED: "열람 승인함",
  REJECTED: "거절함",
  REVOKED: "승인 취소함",
};

/** 서버 시각은 UTC 다. 자르지 않고 현지로 읽는다 (CLAUDE.md 「날짜 · 시각」). */
const when = (v: string) =>
  new Date(v).toLocaleString("ko-KR", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

/** 내가 주인인 반에 온 열람 요청. 화면 안 목록으로만 알린다 (ADR-059 §12). */
export function ReceivedRequestsPanel({
  className,
  state,
  busyId,
  message,
  onDecide,
  onRetry,
}: {
  className: string;
  state: ReceivedState;
  busyId: number | null;
  message: string;
  onDecide: (id: number, status: "APPROVED" | "REJECTED" | "REVOKED") => void;
  onRetry: () => void;
}) {
  return (
    <section className={styles.requestsPanel} aria-label="받은 열람 요청">
      <h3>
        <Icon name="bell" />
        {className} 받은 열람 요청
      </h3>
      {message && <p role="status">{message}</p>}
      <ReceivedBody state={state} busyId={busyId} onDecide={onDecide} onRetry={onRetry} />
    </section>
  );
}

function ReceivedBody({
  state,
  busyId,
  onDecide,
  onRetry,
}: {
  state: ReceivedState;
  busyId: number | null;
  onDecide: (id: number, status: "APPROVED" | "REJECTED" | "REVOKED") => void;
  onRetry: () => void;
}) {
  if (state.status === "loading") return <p role="status">받은 요청을 불러오고 있어요.</p>;
  if (state.status === "error")
    return (
      <div>
        <p role="alert">받은 요청을 불러오지 못했어요. {state.error}</p>
        <button type="button" className={ws.secondary} onClick={onRetry}>
          다시 불러오기
        </button>
      </div>
    );
  if (!state.items.length) return <p className={ws.muted}>받은 열람 요청이 없어요.</p>;
  return (
    <ul className={styles.requestList}>
      {state.items.map((r) => (
        <RequestRow key={r.id} request={r} busy={busyId === r.id} onDecide={onDecide} />
      ))}
    </ul>
  );
}

function RequestRow({
  request,
  busy,
  onDecide,
}: {
  request: ReceivedAccessRequest;
  busy: boolean;
  onDecide: (id: number, status: "APPROVED" | "REJECTED" | "REVOKED") => void;
}) {
  return (
    <li>
      <div className={styles.requestWho}>
        <strong>{request.requester_name}</strong>
        <span>
          {request.class_name} · {request.status === "PENDING" ? "요청" : "처리"}{" "}
          {when(request.updated_at)}
        </span>
      </div>
      <span className={styles.requestState} data-state={request.status}>
        {REQUEST_STATE[request.status]}
      </span>
      {request.status === "PENDING" && (
        <div className={styles.requestActions}>
          <button
            type="button"
            className={ws.primary}
            disabled={busy}
            onClick={() => onDecide(request.id, "APPROVED")}
          >
            승인
          </button>
          <button
            type="button"
            className={ws.secondary}
            disabled={busy}
            onClick={() => onDecide(request.id, "REJECTED")}
          >
            거절
          </button>
        </div>
      )}
      {request.status === "APPROVED" && (
        <div className={styles.requestActions}>
          <button
            type="button"
            className={ws.secondary}
            disabled={busy}
            onClick={() => onDecide(request.id, "REVOKED")}
          >
            승인 취소
          </button>
        </div>
      )}
    </li>
  );
}
