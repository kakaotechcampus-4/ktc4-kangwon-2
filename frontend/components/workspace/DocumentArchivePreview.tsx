"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { deleteAnnualPlan, getAnnualPlan, unconfirmAnnualPlan } from "@/lib/api/plans";
import { deleteMonthlyPlan, getMonthlyPlan, unconfirmMonthlyPlan } from "@/lib/api/monthly";
import { deletePlayMonthly, getPlayMonthly, unconfirmPlayMonthly } from "@/lib/api/playMonthly";
import { deleteWeeklyPlan, getWeeklyPlan, unconfirmWeeklyPlan } from "@/lib/api/weekly";
import { errorCode } from "@/lib/api/client";
import PlayMonthlyConfirm from "@/components/plan-generator/PlayMonthlyConfirm";
import {
  DOCUMENT_KINDS,
  localDate,
  type DocumentKind,
  type SavedDocument,
  type Section,
  type Source,
} from "@/lib/workspace/model";
import { ws } from "./WorkspaceUI";
import { CircleMark } from "./CircleMark";
import styles from "./DocumentArchive.module.css";

type Content = {
  title: string;
  className: string;
  childName?: string;
  period: string;
  status: "draft" | "confirmed";
  createdAt: string;
  sections: Pick<Section, "heading" | "body">[];
  classNote?: string;
  /** 일지 문서만 — 주간 보육일지는 제목에 주를 동그라미 치고 사실을 날짜별로 묶는다. */
  kind?: DocumentKind;
  start?: string;
  end?: string;
  sources?: Pick<Source, "date" | "text">[];
};

/** 단락 이름별 왼쪽 띠 색. 그 밖의 단락(계획안 칸 등)은 기본 선 색이다. */
const SECTION_TONES: Record<string, string> = { 사실: "fact", 해석: "read", 지원: "support" };

type FactRow = { name: string; time: string; lines: string[] };
type FactDay = { date: string; rows: FactRow[] };

const ymd = (date: string) => {
  const [y, m, d] = date.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
};
const valid = (date: string) =>
  /^\d{4}-\d{2}-\d{2}$/.test(date) && !Number.isNaN(ymd(date).getTime());

/** 주간 보육일지 제목 옆의 주 — 「11월 9일 ~ 15일」, 달이 바뀌면 「11월 30일 ~ 12월 6일」. 날짜가 이상하면 "". */
export function weekLabel(start: string, end: string): string {
  if (!valid(start) || !valid(end)) return "";
  const s = ymd(start);
  const e = ymd(end);
  const head = `${s.getUTCMonth() + 1}월 ${s.getUTCDate()}일`;
  if (start === end) return head;
  const sameMonth =
    s.getUTCFullYear() === e.getUTCFullYear() && s.getUTCMonth() === e.getUTCMonth();
  return `${head} ~ ${sameMonth ? "" : `${e.getUTCMonth() + 1}월 `}${e.getUTCDate()}일`;
}

/** 사실 날짜 머리글 — 「11월 9일 (월)」. */
export function dayLabel(date: string): string {
  const d = ymd(date);
  return `${d.getUTCMonth() + 1}월 ${d.getUTCDate()}일 (${"일월화수목금토"[d.getUTCDay()]})`;
}

/**
 * 서버가 제목 끝에 붙인 기간(`_period` — 「(11월)」 · 「(11/9)」 · 「(11/30~12/6)」)을 뗀다.
 * 기간은 옆에 동그라미로 따로 쓴다. 서버에 저장된 제목은 그대로 둔다 — 교사가 바꾼 제목도 건드리지 않는다.
 */
export function bareTitle(title: string): string {
  return title.replace(/\s*\((\d{1,2}월|\d{1,2}\/\d{1,2}(~\d{1,2}\/\d{1,2})?)\)$/, "");
}

/** 주간 보육일지 제목 — 「햇살반 주간 보육일지」 옆에 주를 손글씨로 쓰고 빨간 손 동그라미를 친다(PM 11-11). */
export function WeekTitle({ title, start, end }: { title: string; start: string; end: string }) {
  const period = weekLabel(start, end);
  if (!period) return <h2>{title}</h2>;
  return (
    <h2>
      {bareTitle(title)}{" "}
      <span className={styles.weekPeriod}>
        {period}
        <CircleMark className={styles.weekRing} />
      </span>
    </h2>
  );
}

/**
 * 보육일지 `사실` 을 일과 한 줄씩 나눈다. 서버는 일과마다 `[이름 09:00~09:30] 실행` 을 빈 줄로
 * 잇는다(`join_facts` · `routineFactText`). 이름표가 없는 글(관찰일지 사실)은 null — 그대로 그린다.
 */
export function factRows(body: string): FactRow[] | null {
  const rows: FactRow[] = [];
  for (const raw of body.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    const label = /^\[([^\]]+)\]\s*(.*)$/.exec(line);
    if (!label) {
      if (!rows.length) return null;
      rows[rows.length - 1].lines.push(line);
      continue;
    }
    const time = /\s*((\d{1,2}:\d{2})?\s*~\s*(\d{1,2}:\d{2})?)$/.exec(label[1]);
    rows.push({
      name: (time ? label[1].slice(0, time.index) : label[1]).trim(),
      time: time ? time[1].replace(/\s*~\s*/, " ~ ").trim() : "",
      lines: label[2] ? [label[2]] : [],
    });
  }
  return rows.length ? rows : null;
}

/**
 * 「-며 · -고 · -서 · 뒤」처럼 말이 이어지는 어절 뒤에서 마디를 나눠 마디 안에서는 줄이 안 바뀌게 묶는다 —
 * 「블록을 / 나눠 주었다」처럼 한 마디가 갈리지 않는다. 「~라고 말했다」는 한 마디로 둔다.
 * 「보았다.」 · 「먹은 뒤」처럼 짧은 마디는 앞 마디에 붙여 혼자 한 줄에 남지 않게 한다.
 * 마디가 한 줄보다 길면 그 안에서 바뀐다.
 * ponytail: 끝말 몇 개만 보는 어림이다. 잘못 나눠도 줄 바꿈 자리만 달라진다.
 */
export function phrases(text: string): string[] {
  const parts: string[] = [];
  for (const part of text.split(/(?<=[며서면데뒤후,]|(?<!라)고)\s+/)) {
    if (parts.length && part.replace(/[\s.,!?"“”]/g, "").length <= 4)
      parts[parts.length - 1] += ` ${part}`;
    else parts.push(part);
  }
  return parts;
}

function Phrases({ text }: { text: string }) {
  return phrases(text).flatMap((part, i) => [
    i ? " " : "",
    <span key={i} className={styles.phrase}>
      {part}
    </span>,
  ]);
}

function FactLines({ lines }: { lines: string[] }) {
  return lines.map((line, i) => (
    <p key={i} className={styles.factText}>
      <Phrases text={line} />
    </p>
  ));
}

/**
 * 일과마다 한 줄 — 왼쪽 칸에 시각, 오른쪽 세로줄을 따라 이름표 · 사실이 내려간다(PM 11-10, 시간 줄).
 * 이름표는 작은 베이지 딱지다. 시각이 없는 일과도 왼쪽 칸을 비워 둔다.
 */
export function FactRows({ rows }: { rows: FactRow[] }) {
  return (
    <ol className={styles.factRows}>
      {rows.map((row, i) => {
        const [from, to] = row.time.split("~").map((t) => t.trim());
        return (
          <li key={i}>
            <div className={styles.factClock}>
              {from && <b>{from}</b>}
              {to && <span>{`~ ${to}`}</span>}
            </div>
            <div className={styles.factStep}>
              <b className={styles.factName}>{row.name}</b>
              <FactLines lines={row.lines} />
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/**
 * 주간 보육일지 `사실` 을 날짜별로 묶는다(PM 11-11). 사실은 근거 원문을 이은 글이라(`join_facts`)
 * 일과 한 줄마다 같은 글을 가진 근거를 찾아 그 근거의 날짜를 붙인다 — 한 번 쓴 근거 줄은 다시 안 쓴다.
 * 못 찾은 줄은 짐작하지 않고 「날짜 없음」(date "")에 둔다. 날짜순, 「날짜 없음」은 맨 뒤.
 * 묶음이 하나뿐이면 null — 머리글 없이 그대로 그린다.
 */
export function factDays(
  rows: FactRow[],
  sources: Pick<Source, "date" | "text">[],
): FactDay[] | null {
  const pool = sources.flatMap((s) =>
    (factRows(s.text) ?? []).map((row) => ({
      key: JSON.stringify(row),
      date: valid(s.date) ? s.date : "",
    })),
  );
  const days: FactDay[] = [];
  for (const row of rows) {
    const at = pool.findIndex((p) => p.key === JSON.stringify(row));
    const date = at < 0 ? "" : pool.splice(at, 1)[0].date;
    const day = days.find((d) => d.date === date);
    if (day) day.rows.push(row);
    else days.push({ date, rows: [row] });
  }
  if (days.length < 2) return null;
  return days.sort((a, b) => (!a.date ? 1 : !b.date ? -1 : a.date.localeCompare(b.date)));
}

/** 사실 시간 줄. `sources` 를 주면(주간 보육일지) 날짜가 둘 이상일 때 날짜 머리글로 나눈다. */
export function FactTimeline({
  rows,
  sources,
}: {
  rows: FactRow[];
  sources?: Pick<Source, "date" | "text">[];
}) {
  const days = sources ? factDays(rows, sources) : null;
  if (!days) return <FactRows rows={rows} />;
  return days.map((day) => (
    <div key={day.date} className={styles.factDay}>
      <h4 className={styles.factDayHead}>{day.date ? dayLabel(day.date) : "날짜 없음"}</h4>
      <FactRows rows={day.rows} />
    </div>
  ));
}

function SectionBody({
  heading,
  body,
  sources,
}: {
  heading: string;
  body: string;
  sources?: Content["sources"];
}) {
  if (!body) return <p className={styles.previewEmpty}>아직 작성된 내용이 없어요.</p>;
  const rows = heading === "사실" ? factRows(body) : null;
  if (rows) return <FactTimeline rows={rows} sources={sources} />;
  return <p>{body}</p>;
}

/** 입력 요소나 변경 요청을 갖지 않는, 실제 조회 값만 그리는 본문.
 *  children 은 머리 쪽지 바로 아래에 붙는 안내(테스트 초안 · 근거 변경)다. */
export function PreviewContent({
  content,
  kind,
  children,
}: {
  content: Content;
  kind: string;
  children?: ReactNode;
}) {
  return (
    <article className={styles.previewContent}>
      <header className={styles.previewHead}>
        <div className={styles.previewMeta}>
          <span className={styles.previewKind}>읽기 전용 · {kind}</span>
          <span className={styles.previewStatus} data-status={content.status}>
            {content.status === "confirmed" ? "확정" : "검토 중"}
          </span>
        </div>
        {content.kind === "weeklyLog" ? (
          <WeekTitle title={content.title} start={content.start ?? ""} end={content.end ?? ""} />
        ) : (
          <h2>{content.title}</h2>
        )}
        <dl className={styles.previewFacts}>
          <div>
            <dt>{content.childName ? "반 · 아이" : "반"}</dt>
            <dd>
              {content.className}
              {content.childName ? ` · ${content.childName}` : ""}
            </dd>
          </div>
          <div>
            <dt>기간</dt>
            <dd>{content.period}</dd>
          </div>
          {content.createdAt && (
            <div>
              <dt>작성</dt>
              <dd>{localDate(content.createdAt)}</dd>
            </div>
          )}
        </dl>
      </header>
      {children}
      {!content.sections.some((s) => s.body.trim()) && (
        <p className={styles.previewNotice}>아직 작성된 본문이 없어요.</p>
      )}
      {content.sections.map((section, i) => (
        <section
          key={i}
          className={styles.previewSection}
          data-tone={SECTION_TONES[section.heading]}
        >
          <h3>{section.heading}</h3>
          <SectionBody
            heading={section.heading}
            body={section.body}
            sources={content.kind === "weeklyLog" ? content.sources : undefined}
          />
        </section>
      ))}
      {content.classNote && (
        <section className={styles.previewSection}>
          <h3>반 운영 특이사항</h3>
          <p>{content.classNote}</p>
        </section>
      )}
    </article>
  );
}

function PreviewError({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <div>
      <p role="alert">미리보기를 불러오지 못했어요. {error}</p>
      <button type="button" className={ws.secondary} onClick={onRetry}>
        미리보기 다시 시도
      </button>
    </div>
  );
}

/** 기존 선택 컨트롤러가 조회한 문서를 읽기만 한다. 편집기는 여기서 마운트하지 않는다. */
export default function DocumentArchivePreview({
  document,
  status,
  error,
  onRetry,
  onEdit,
}: {
  document: SavedDocument | null;
  status: "loading" | "ready" | "error";
  error: string;
  onRetry: () => void;
  /** 없으면 편집 단추를 그리지 않는다 — 승인받은 남의 반은 보기만 한다 (ADR-059). */
  onEdit?: () => void;
}) {
  if (status === "loading") return <p role="status">문서 미리보기를 불러오고 있어요.</p>;
  if (status === "error") return <PreviewError error={error} onRetry={onRetry} />;
  if (!document)
    return <PreviewError error="문서가 삭제되었거나 목록이 변경되었어요." onRetry={onRetry} />;
  return (
    <>
      <PreviewContent
        kind={DOCUMENT_KINDS[document.kind]}
        content={{
          ...document,
          period:
            document.start === document.end
              ? document.start
              : `${document.start} ~ ${document.end}`,
        }}
      >
        {document.mockDraft && (
          <p className={styles.previewNotice}>테스트 모드(mock)로 만든 초안이에요.</p>
        )}
        {"stale" in document && document.stale === true && (
          <p className={styles.previewNotice} data-tone="warn">
            원본 근거가 변경되었어요. 문서를 열어 재검토해 주세요.
          </p>
        )}
      </PreviewContent>
      {document.reviewNote && (
        <section className={styles.previewMemo}>
          <h3>검토 메모</h3>
          <p>{document.reviewNote}</p>
        </section>
      )}
      {onEdit && (
        <div className={styles.previewActions}>
          <button type="button" className={ws.primary} onClick={onEdit}>
            {document.status === "confirmed" ? "문서 열기" : "편집하기"}
          </button>
        </div>
      )}
    </>
  );
}

export type PlanPreviewTarget = {
  kind: "annual" | "monthly" | "weekly";
  id: number;
  classId: number;
  className: string;
  title: string;
  period: string;
  periodKey: string;
  createdAt: string;
  /** 비면 「문서 열기」를 그리지 않는다 — 승인받은 남의 반 계획안은 편집 화면으로 보내지 않는다. */
  href: string;
  /** 놀이 중심 월간(`kind` 는 monthly). 읽기 · 지우기 경로가 다르다. */
  play?: boolean;
};

/** 지운다. 이 계획안으로 만든 하위가 있으면 서버가 409 `IN_USE` 다(ADR-064). */
function deletePlan(target: PlanPreviewTarget) {
  if (target.kind === "annual") return deleteAnnualPlan(target.id);
  if (target.kind === "weekly") return deleteWeeklyPlan(target.id);
  return target.play ? deletePlayMonthly(target.id) : deleteMonthlyPlan(target.id);
}
/** 확정을 풀어 초안으로 되돌린다. 딸린 하위가 있어도 풀린다(하위는 부모 스냅샷을 그대로 가진다). */
function unconfirmPlan(target: PlanPreviewTarget, revision: number | undefined) {
  if (target.kind === "annual") return unconfirmAnnualPlan(target.id, revision);
  if (revision === undefined) throw new Error("계획안 판이 없어요. 다시 열어 주세요.");
  if (target.kind === "weekly") return unconfirmWeeklyPlan(target.id, revision);
  return target.play
    ? unconfirmPlayMonthly(target.id, revision)
    : unconfirmMonthlyPlan(target.id, revision);
}
const IN_USE_MESSAGE: Record<PlanPreviewTarget["kind"], string> = {
  annual: "이 계획안으로 만든 월간계획안이 있어요. 먼저 지워주세요.",
  monthly: "이 계획안으로 만든 주간계획안이 있어요. 먼저 지워주세요.",
  weekly: "계획안을 지우지 못했어요.",
};

/**
 * 권한 검사는 기존 GET API가 한다. 이동/해제 뒤 늦은 응답은 버린다.
 * `onDeleted` 가 있으면 「삭제」를 그린다(상태 무관, 확정본도 — ADR-064). 남의 반은 넘기지 않는다.
 * 확정본이고 편집 화면이 있으면 「수정하기」(누르면 확정을 풀고 편집 화면으로 간다)도 그린다 — 계획안 화면에는 확정 취소가 없다(ADR-064).
 */
export function PlanArchivePreview({
  target,
  onDeleted,
}: {
  target: PlanPreviewTarget;
  onDeleted?: () => void;
}) {
  const key = `${target.kind}:${target.classId}:${target.id}`;
  const router = useRouter();
  const [request, setRequest] = useState<{
    key: string;
    content?: Content;
    revision?: number;
    error?: string;
  } | null>(null);
  const [retry, setRetry] = useState(0);
  const [asking, setAsking] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  async function unconfirm() {
    setDeleting(true);
    setDeleteError("");
    try {
      await unconfirmPlan(target, request?.revision);
      router.push(target.href);
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : "확정을 풀지 못했어요.");
      setDeleting(false);
    }
  }
  async function remove() {
    setDeleting(true);
    setDeleteError("");
    try {
      await deletePlan(target);
      setAsking(false);
      onDeleted?.();
    } catch (e) {
      setAsking(false);
      setDeleteError(
        errorCode(e) === "IN_USE"
          ? IN_USE_MESSAGE[target.kind]
          : e instanceof Error
            ? e.message
            : "계획안을 지우지 못했어요.",
      );
    } finally {
      setDeleting(false);
    }
  }
  useEffect(() => {
    let live = true;
    const controller = new AbortController();
    async function load() {
      let plan;
      let sections: Content["sections"];
      if (target.play) {
        const play = await getPlayMonthly(target.id, controller.signal);
        plan = play;
        sections = [
          { heading: "주제", body: play.theme.value },
          { heading: "주제선정이유", body: play.rationale.value },
          ...play.together.map((a) => ({
            heading: `함께 하는 활동 · ${a.name.value}`,
            body: a.description.value,
          })),
          ...play.free_play.map((a) => ({
            heading: `유아 예상 자유놀이 · ${a.name.value}`,
            body: a.description.value,
          })),
        ];
      } else if (target.kind === "annual") {
        const annual = await getAnnualPlan(target.id, controller.signal);
        plan = annual;
        if (annual.format === "PLAY_PROJECT") {
          sections = annual.periods.flatMap((period) =>
            period.selected.flatMap((key) => {
              const row = period.candidates.find((candidate) => candidate.row_key === key);
              if (!row) return [];
              return [
                {
                  heading: `${period.label} · ${row.play_name.value}`,
                  body: [row.materials.value, row.support_direction.value, row.learning.value].join(
                    "\n",
                  ),
                },
              ];
            }),
          );
        } else {
          sections = annual.months.map((m) => ({
            heading: `${m.month}월`,
            body: [m.theme, ...m.sub_themes].join("\n"),
          }));
        }
      } else {
        const matrix =
          target.kind === "monthly"
            ? await getMonthlyPlan(target.id, controller.signal)
            : await getWeeklyPlan(target.id, controller.signal);
        plan = matrix;
        sections = matrix.sections
          .filter((s) => s.visible && s.role === "CONTENT")
          .flatMap((s) =>
            s.cells.map((c) => ({
              heading: s.label || "본문",
              body: ("week_id" in c && c.week_id ? `${c.week_id}\n` : "") + c.value,
            })),
          );
      }
      if (plan.id !== target.id || plan.class_id !== target.classId)
        throw new Error("선택한 반의 문서가 아니에요.");
      if (live)
        setRequest({
          key,
          revision: "revision" in plan ? plan.revision : undefined,
          content: {
            title: target.title,
            className: target.className,
            period: target.period,
            createdAt: target.createdAt,
            status: plan.status === "CONFIRMED" ? "confirmed" : "draft",
            sections,
          },
        });
    }
    void load().catch((e: unknown) => {
      if (live)
        setRequest({ key, error: e instanceof Error ? e.message : "문서를 조회할 수 없어요." });
    });
    return () => {
      live = false;
      controller.abort();
    };
  }, [key, retry, target]);
  const current = request?.key === key ? request : null;
  if (!current) return <p role="status">계획안 미리보기를 불러오고 있어요.</p>;
  if (current.error)
    return (
      <PreviewError
        error={current.error}
        onRetry={() => {
          setRequest(null);
          setRetry((n) => n + 1);
        }}
      />
    );
  if (!current.content) return null;
  return (
    <>
      <PreviewContent kind={DOCUMENT_KINDS[target.kind]} content={current.content} />
      {target.href && (
        <div className={styles.previewActions}>
          <Link className={ws.primary} href={target.href}>
            문서 열기
          </Link>
        </div>
      )}
      {onDeleted && target.href && current.content.status === "confirmed" && (
        <button type="button" className={ws.secondary} disabled={deleting} onClick={unconfirm}>
          수정하기
        </button>
      )}
      {onDeleted && (
        <button
          type="button"
          className={ws.secondary}
          disabled={deleting}
          onClick={() => setAsking(true)}
        >
          삭제
        </button>
      )}
      {asking && (
        <PlayMonthlyConfirm
          message="이 계획안을 지울까요? 되돌릴 수 없어요."
          yes={deleting ? "지우는 중…" : "지우기"}
          no="그대로 두기"
          disabled={deleting}
          onYes={remove}
          onNo={() => setAsking(false)}
        />
      )}
      {deleteError && <p role="alert">{deleteError}</p>}
    </>
  );
}
