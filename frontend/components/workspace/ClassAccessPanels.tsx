"use client";

/**
 * 문서 보관함의 같은 원 다른 반 (docs/api-spec.md §2-2, ADR-059).
 *
 * 남의 반은 그 반 담임이 승인해야 본다. 승인 전에는 종류 · 기간 · 상태만 보이고,
 * 승인 뒤에는 보기와 확정 문서 hwp 내려받기만 된다 — 고치는 길은 열지 않는다.
 * 보관함 화면(덕철)의 반 고르기 칸에서 이 반을 누르면 오른쪽 본문 자리에 이 칸들이 선다.
 */

import { useEffect, useState, type ReactNode } from "react";
import { errorCode } from "@/lib/api/client";
import { getMe } from "@/lib/api/auth";
import { getClasses, isMyClass } from "@/lib/api/classes";
import type { ApiClass } from "@/lib/api/types";
import {
  classAccessMessage,
  decideRequest,
  getArchiveSummary,
  listReceivedRequests,
  requestClassAccess,
  type AccessStatus,
  type ArchiveSummaryItem,
  type ReceivedRequest,
} from "@/lib/api/class-access";
import {
  downloadDocumentHwpx,
  getDocument,
  isStaleWrite,
  listDocuments,
  type ServerDocument,
} from "@/lib/api/documents";
import { downloadAnnualHwpx, listAnnualPlans } from "@/lib/api/plans";
import { downloadMonthlyHwpx, listMonthlyPlans } from "@/lib/api/monthly";
import { downloadWeeklyHwpx, listWeeklyPlans } from "@/lib/api/weekly";
import { monthLabel, weekIdLabel } from "@/lib/workspace/document-archive";
import { DOCUMENT_KINDS, localDate } from "@/lib/workspace/model";
import { Icon } from "@/components/app/icons";
import { Posty, type PostyFace, type PostyPose, type PostyTone } from "@/components/app/Posty";
import { Message, ws } from "./WorkspaceUI";
import DocumentArchivePreview, {
  PlanArchivePreview,
  type PlanPreviewTarget,
} from "./DocumentArchivePreview";

/** 남의 반 하나의 열람 상태. 서버의 `my_access` 에서 OWNER · OPEN 을 뺀 것이다. */
export type ForeignAccess = "NONE" | AccessStatus;

export const ACCESS_LABEL: Record<ForeignAccess, string> = {
  NONE: "잠김",
  PENDING: "요청 중",
  APPROVED: "함께 봐요",
  REJECTED: "거절됨",
  REVOKED: "승인 취소됨",
};

const accessOf = (room: ApiClass): ForeignAccess => (room.my_access ?? "NONE") as ForeignAccess;

/**
 * 같은 원의 남의 반과 내가 받은 요청.
 *
 * 둘 다 보관함에 덤으로 붙는 것이다 — 못 불러와도 내 반 보관함은 그대로 써야 해서
 * 실패는 빈 목록으로 둔다.
 */
export function useClassAccess() {
  const [others, setOthers] = useState<ApiClass[]>([]);
  const [received, setReceived] = useState<ReceivedRequest[]>([]);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let live = true;
    getMe()
      .then((me) => (me.center_id ? getClasses(me.center_id) : { items: [] }))
      .then(({ items }) => live && setOthers(items.filter((room) => !isMyClass(room))))
      .catch(() => live && setOthers([]));
    listReceivedRequests()
      .then(({ items }) => live && setReceived(items))
      .catch(() => live && setReceived([]));
    return () => {
      live = false;
    };
  }, [reload]);

  return { others, received, reload: () => setReload((n) => n + 1) };
}

/** 상태마다 포스티가 짓는 모습과 하는 말. */
const MOOD: Record<
  ForeignAccess,
  {
    pose: PostyPose;
    face: PostyFace;
    tone: PostyTone;
    word: string;
    lead: (teacher: string) => string;
  }
> = {
  NONE: {
    pose: "hand",
    face: "oh",
    tone: "sun",
    word: "담임 선생님 승인을 받아야 볼 수 있어요.",
    lead: () =>
      "승인 전에는 종류 · 기간 · 상태만 보여요. 승인되면 보기와 hwp 내려받기가 열리고, 선생님 반도 담임 선생님이 볼 수 있어요.",
  },
  PENDING: {
    pose: "think",
    face: "think",
    tone: "lilac",
    word: "열람 요청을 보냈어요.",
    lead: (teacher) => `${teacher} 선생님이 승인하면 이 화면에서 바로 열려요.`,
  },
  REJECTED: {
    pose: "sit",
    face: "empty",
    tone: "shell",
    word: "요청이 거절됐어요.",
    lead: () => "필요하면 담임 선생님께 먼저 말씀드리고 다시 요청할 수 있어요.",
  },
  REVOKED: {
    pose: "sit",
    face: "empty",
    tone: "shell",
    word: "담임 선생님이 열람 권한을 거뒀어요.",
    lead: () => "필요하면 다시 요청할 수 있어요.",
  },
  APPROVED: {
    pose: "cheer",
    face: "done",
    tone: "sage",
    word: "승인받았어요 · 서로 함께 봐요",
    lead: () =>
      "보기와 확정 문서 hwp 내려받기만 돼요. 고치기 · 확정 · 삭제는 담임 선생님만 할 수 있어요.",
  },
};

const PLAN_NAME = { annual: "연간 계획안", monthly: "월간 계획안", weekly: "주간 계획안" } as const;

const kindName = (kind: ArchiveSummaryItem["kind"]) =>
  kind in PLAN_NAME ? PLAN_NAME[kind as keyof typeof PLAN_NAME] : DOCUMENT_KINDS[kind];

/** 요약 한 줄의 기간. 연간은 학년도, 월간은 그 달로 적는다 — 날짜 두 개보다 읽기 쉽다. */
function periodOf(item: ArchiveSummaryItem) {
  if (item.kind === "annual") return `${item.start.slice(0, 4)}학년도`;
  if (item.kind === "monthly") return monthLabel(item.start.slice(0, 7));
  return item.start === item.end ? item.start : `${item.start} ~ ${item.end}`;
}

/** 남의 반 하나. 승인 전이면 요약과 요청 단추, 승인 뒤면 보기 전용 목록이다. */
export function ForeignClassPanel({ room, onChanged }: { room: ApiClass; onChanged: () => void }) {
  const access = accessOf(room);
  const mood = MOOD[access];
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function ask() {
    setBusy(true);
    setError("");
    try {
      await requestClassAccess(room.id);
    } catch (e) {
      // 409 ALREADY_EXISTS 는 다른 화면에서 이미 보냈다는 뜻이다. 상태만 새로 받으면 된다.
      if (errorCode(e) !== "ALREADY_EXISTS")
        setError(e instanceof Error ? e.message : "요청을 보내지 못했어요.");
    } finally {
      setBusy(false);
      onChanged();
    }
  }

  return (
    <section className={`${ws.card} ${ws.accessCard}`} aria-label={`${room.name} 문서`}>
      <div className={ws.accessHead}>
        <Posty pose={mood.pose} face={mood.face} tone={mood.tone} size={62} label={null} />
        <div className={ws.accessName}>
          <h2>{room.name}</h2>
          <p>같은 원 · 담임 {room.teacher_name || "—"} 선생님</p>
        </div>
        <span className={ws.accessBadge} data-state={access}>
          {access !== "APPROVED" && <Icon name="lock" />}
          {ACCESS_LABEL[access]}
        </span>
      </div>

      <div className={ws.accessSay}>
        <div>
          <p className={ws.accessWord}>{mood.word}</p>
          <p className={ws.accessLead}>{mood.lead(room.teacher_name || "담임")}</p>
        </div>
        {(access === "NONE" || access === "REJECTED" || access === "REVOKED") && (
          <button type="button" className={ws.primary} disabled={busy} onClick={ask}>
            {busy ? "보내는 중…" : access === "NONE" ? "열람 요청 보내기" : "다시 요청"}
          </button>
        )}
      </div>
      <Message error>{error}</Message>

      {access === "APPROVED" ? (
        <ApprovedList room={room} onLost={onChanged} />
      ) : (
        <LockedSummary classId={room.id} />
      )}
    </section>
  );
}

/** 승인 전에 보이는 것 — 종류 · 기간 · 상태. 제목과 아이 이름은 서버가 주지 않는다. */
function LockedSummary({ classId }: { classId: number }) {
  const [state, setState] = useState<{
    id: number;
    items?: ArchiveSummaryItem[];
    error?: string;
  }>();

  useEffect(() => {
    let live = true;
    getArchiveSummary(classId)
      .then(({ items }) => live && setState({ id: classId, items }))
      .catch(
        (e) =>
          live &&
          setState({
            id: classId,
            error: e instanceof Error ? e.message : "요약을 불러오지 못했어요.",
          }),
      );
    return () => {
      live = false;
    };
  }, [classId]);

  const current = state?.id === classId ? state : undefined;
  if (!current) return <p className={ws.hint}>이 반에 무엇이 있는지 불러오는 중…</p>;
  if (current.error) return <Message error>{current.error}</Message>;
  if (!current.items?.length) return <p className={ws.hint}>이 반에는 아직 만든 문서가 없어요.</p>;
  return (
    <div className={ws.accessTableWrap}>
      <table className={ws.accessTable}>
        <thead>
          <tr>
            <th>종류</th>
            <th>기간</th>
            <th>상태</th>
            <th>열람</th>
          </tr>
        </thead>
        <tbody>
          {current.items.map((item, index) => (
            <tr key={index}>
              <td>{kindName(item.kind)}</td>
              <td>{periodOf(item)}</td>
              <td>{item.status === "CONFIRMED" ? "확정" : "초안"}</td>
              <td className={ws.accessLocked}>
                <Icon name="lock" />
                잠김
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** 승인받은 반의 한 줄. 보기는 미리보기 칸, 내려받기는 확정본만이다. */
type Row = {
  key: string;
  /** 정렬 열쇠 — 최근 것이 위다. */
  order: string;
  name: string;
  title: string;
  period: string;
  confirmed: boolean;
  view: { doc: string } | { plan: PlanPreviewTarget };
  /** 없으면 한글 파일로 못 만든다 — 증빙으로 올린 원문(IMPORT)은 서버가 409 로 막는다. */
  hwp?: () => Promise<void>;
};

function ApprovedList({ room, onLost }: { room: ApiClass; onLost: () => void }) {
  const [state, setState] = useState<{ id: number; rows: Row[]; error: string }>();
  const [viewing, setViewing] = useState<Row | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    const plan = (
      kind: PlanPreviewTarget["kind"],
      id: number,
      title: string,
      period: string,
      createdAt: string,
    ): PlanPreviewTarget => ({
      kind,
      id,
      classId: room.id,
      className: room.name,
      title,
      period,
      periodKey: period,
      createdAt,
      href: "",
    });
    // 승인된 반도 반을 짚어야 준다 — `class_id` 없는 목록은 내 반 것만이다 (§2-2).
    Promise.allSettled([
      listDocuments({ class_id: room.id }),
      listAnnualPlans(room.id),
      listMonthlyPlans(room.id),
      listWeeklyPlans(room.id),
    ]).then(([docs, annual, monthly, weekly]) => {
      if (!live) return;
      const failed = [docs, annual, monthly, weekly].filter((r) => r.status === "rejected");
      // 그 사이 승인이 거둬졌으면 목록이 아니라 상태를 다시 받아야 한다.
      if (failed.some((r) => errorCode(r.reason) === "CLASS_ACCESS_REQUIRED")) return onLost();
      const rows: Row[] = [];
      if (docs.status === "fulfilled")
        for (const d of docs.value)
          rows.push({
            key: d.id,
            order: d.start,
            name: DOCUMENT_KINDS[d.kind],
            title: d.title,
            period: d.start === d.end ? d.start : `${d.start} ~ ${d.end}`,
            confirmed: d.status === "confirmed",
            view: { doc: d.id },
            hwp: d.origin === "import" ? undefined : () => downloadDocumentHwpx(d.id),
          });
      if (annual.status === "fulfilled")
        for (const p of annual.value.items) {
          const title = `${p.school_year}학년도 연간 계획안`;
          rows.push({
            key: `annual:${p.id}`,
            order: `${p.school_year}-03`,
            name: PLAN_NAME.annual,
            title,
            period: `${p.school_year}학년도`,
            confirmed: p.status === "CONFIRMED",
            view: { plan: plan("annual", p.id, title, `${p.school_year}학년도`, p.created_at) },
            hwp: () => downloadAnnualHwpx(p.id),
          });
        }
      if (monthly.status === "fulfilled")
        for (const p of monthly.value.items) {
          const period = monthLabel(p.target_month);
          rows.push({
            key: `monthly:${p.id}`,
            order: p.target_month,
            name: PLAN_NAME.monthly,
            title: `${period} 월간 계획안`,
            period,
            confirmed: p.status === "CONFIRMED",
            view: { plan: plan("monthly", p.id, `${period} 월간 계획안`, period, p.created_at) },
            hwp: () => downloadMonthlyHwpx(p.id),
          });
        }
      if (weekly.status === "fulfilled")
        for (const p of weekly.value.items) {
          const period = weekIdLabel(p.week_id);
          rows.push({
            key: `weekly:${p.id}`,
            order: p.week_id,
            name: PLAN_NAME.weekly,
            title: `${period} 주간 계획안`,
            period,
            confirmed: p.status === "CONFIRMED",
            view: { plan: plan("weekly", p.id, `${period} 주간 계획안`, period, p.created_at) },
            hwp: () => downloadWeeklyHwpx(p.id),
          });
        }
      rows.sort((a, b) => b.order.localeCompare(a.order));
      setState({
        id: room.id,
        rows,
        error: failed.length ? "일부 문서를 불러오지 못했어요. 잠시 뒤 다시 열어 주세요." : "",
      });
    });
    return () => {
      live = false;
    };
    // `onLost` 는 부모가 매 렌더 새로 만든다. 넣으면 그릴 때마다 네 목록을 다시 부른다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [room.id, room.name]);

  async function download(row: Row) {
    setError("");
    try {
      await row.hwp?.();
    } catch (e) {
      setError(classAccessMessage(e) ?? (e instanceof Error ? e.message : "내려받지 못했어요."));
    }
  }

  const current = state?.id === room.id ? state : undefined;
  if (!current) return <p className={ws.hint}>문서를 불러오는 중…</p>;
  return (
    <>
      <Message error>{current.error || error}</Message>
      {!current.rows.length ? (
        <p className={ws.hint}>이 반에는 아직 만든 문서가 없어요.</p>
      ) : (
        <div className={ws.accessTableWrap}>
          <table className={ws.accessTable}>
            <thead>
              <tr>
                <th>문서</th>
                <th>기간</th>
                <th>상태</th>
                <th>할 수 있는 것</th>
              </tr>
            </thead>
            <tbody>
              {current.rows.map((row) => (
                <tr key={row.key} aria-selected={viewing?.key === row.key || undefined}>
                  <td>
                    <b>{row.title}</b>
                    <small>{row.name}</small>
                  </td>
                  <td>{row.period}</td>
                  <td>{row.confirmed ? "확정" : "초안"}</td>
                  <td>
                    <span className={ws.accessActions}>
                      <button type="button" onClick={() => setViewing(row)}>
                        보기
                      </button>
                      {/* 초안은 서버가 hwp 를 주지 않는다 — 단추를 두면 누를 때마다 실패한다. */}
                      {row.confirmed && row.hwp && (
                        <button type="button" onClick={() => download(row)}>
                          hwp
                        </button>
                      )}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {viewing && (
        <section className={ws.accessPreview} aria-label={`${viewing.title} 미리보기`}>
          <button type="button" className={ws.rowTool} onClick={() => setViewing(null)}>
            닫기
          </button>
          {"doc" in viewing.view ? (
            <DocumentView key={viewing.key} id={viewing.view.doc} />
          ) : (
            <PlanArchivePreview key={viewing.key} target={viewing.view.plan} />
          )}
        </section>
      )}
    </>
  );
}

/** 일지 한 장을 읽기만 한다. 편집 단추는 없다. */
function DocumentView({ id }: { id: string }) {
  const [doc, setDoc] = useState<ServerDocument | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let live = true;
    getDocument(id)
      .then((found) => live && setDoc(found))
      .catch(
        (e) =>
          live &&
          setError(
            classAccessMessage(e) ?? (e instanceof Error ? e.message : "문서를 열지 못했어요."),
          ),
      );
    return () => {
      live = false;
    };
  }, [id, retry]);
  return (
    <DocumentArchivePreview
      document={doc}
      status={error ? "error" : doc ? "ready" : "loading"}
      error={error}
      onRetry={() => {
        setError("");
        setRetry((n) => n + 1);
      }}
    />
  );
}

/** 내가 주인인 반에 온 요청. 기다리는 것 · 볼 수 있는 선생님 · 거절하거나 거둔 것 셋으로 가른다. */
export function ReceivedPanel({
  items,
  onChanged,
}: {
  items: ReceivedRequest[];
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(0);
  const [message, setMessage] = useState("");
  const pending = items.filter((r) => r.status === "PENDING");
  const approved = items.filter((r) => r.status === "APPROVED");
  const closed = items.filter((r) => r.status === "REJECTED" || r.status === "REVOKED");

  async function decide(item: ReceivedRequest, status: Exclude<AccessStatus, "PENDING">) {
    setBusy(item.id);
    setMessage("");
    try {
      await decideRequest(item.id, status);
    } catch (e) {
      setMessage(
        isStaleWrite(e)
          ? "그 사이 다른 화면에서 바뀌었어요. 새로 불러왔어요."
          : e instanceof Error
            ? e.message
            : "바꾸지 못했어요.",
      );
    } finally {
      setBusy(0);
      onChanged();
    }
  }

  const group = (
    title: string,
    rows: ReceivedRequest[],
    actions: (r: ReceivedRequest) => ReactNode,
    note: (r: ReceivedRequest) => string,
  ) =>
    rows.length > 0 && (
      <div className={ws.accessGroup}>
        <h3>
          {title} <span>{rows.length}</span>
        </h3>
        <ul>
          {rows.map((r) => (
            <li key={r.id}>
              <div>
                <b>{r.requester_name} 선생님</b>
                <small>
                  {r.class_name} · {note(r)}
                </small>
              </div>
              <span className={ws.accessActions}>{actions(r)}</span>
            </li>
          ))}
        </ul>
      </div>
    );

  return (
    <section className={`${ws.card} ${ws.accessCard}`} aria-label="받은 열람 요청">
      <div className={ws.accessHead}>
        <Posty
          pose={pending.length ? "point" : "stand"}
          face={pending.length ? "oh" : "base"}
          tone={pending.length ? "sun" : "note"}
          size={62}
          label={null}
        />
        <div className={ws.accessName}>
          <h2>받은 열람 요청</h2>
          <p>
            승인하면 <b>두 반이 서로 보여요</b> — 그 선생님은 우리 반 문서를, 선생님은 그 선생님 반
            문서를 보고 확정 문서를 hwp 로 받을 수 있어요. 고치는 건 각자 자기 반만 해요.
          </p>
        </div>
      </div>
      <Message error>{message}</Message>
      {!items.length && <p className={ws.hint}>아직 받은 요청이 없어요.</p>}
      {group(
        "기다리는 요청",
        pending,
        (r) => (
          <>
            <button type="button" disabled={!!busy} onClick={() => decide(r, "REJECTED")}>
              거절
            </button>
            <button type="button" data-main disabled={!!busy} onClick={() => decide(r, "APPROVED")}>
              승인
            </button>
          </>
        ),
        (r) => `${localDate(r.created_at)} 요청`,
      )}
      {group(
        "볼 수 있는 선생님",
        approved,
        (r) => (
          <button type="button" disabled={!!busy} onClick={() => decide(r, "REVOKED")}>
            승인 취소
          </button>
        ),
        (r) => `${localDate(r.updated_at)} 승인`,
      )}
      {group(
        "거절 · 취소한 요청",
        closed,
        () => null,
        (r) =>
          `${localDate(r.updated_at)} ${r.status === "REJECTED" ? "거절" : "취소"} · 다시 요청하면 위로 올라와요`,
      )}
    </section>
  );
}
