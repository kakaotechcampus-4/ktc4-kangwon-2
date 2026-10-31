"use client";

/**
 * 월간계획안(v1) 편집 — 놀이 월간과 같은 배치다. 문서에서 칸을 누르면 옆 패널에서 고친다.
 * 입력을 멈추거나 칸을 떠나면 그 칸만 저장한다(v1 칸 편집 API). 저장 · 재생성 · 확정은
 * 한 줄로 세워 앞 요청이 돌려준 revision 으로 보낸다. 409 면 덮어쓰지 않고 다시 불러온다.
 * 저장하지 못한 글은 되돌리지 않고 남겨 다시 저장하게 한다 — 그동안 확정 · 반 · 월 이동은 멈춘다.
 */

import { useEffect, useRef, useState, type RefObject } from "react";
import { ApiError } from "@/lib/api/client";
import {
  confirmMonthlyPlan,
  downloadMonthlyHwpx,
  editMonthlyCell,
  getMonthlyPlanAudit,
  regenerateMonthlyCell,
} from "@/lib/api/monthly";
import { isSaveConflict } from "@/lib/api/plans";
import type { MonthlyAuditEvent, MonthlyCell, MonthlyPlan } from "@/lib/api/types";
import { sectionName } from "@/lib/monthly/section-labels";
import { useHwpxDownload } from "@/lib/hooks/use-hwpx-download";
import PlayCellEditor from "@/components/plan-generator/PlayCellEditor";
import { Cell, SheetFrame } from "@/components/plan-generator/PlayMonthlySheet";
import type { SheetZoom } from "@/components/plan-generator/playProjectPagination";
import styles from "@/components/plan-generator/PlayMonthlyView.module.css";
import { ws } from "./WorkspaceUI";

const REGENERATABLE = new Set(["focus", "outdoor_play", "basic_habit", "goals"]);
const FINDINGS: Record<string, string> = {
  ACTIVITY_REFERENCE_NOT_VERIFIED:
    "수정한 내용과 기존 참고 활동의 연결을 자동으로 확인하지 못했어요. 교사가 내용을 확인해주세요.",
  ACTIVITY_FREE_TEXT_AGE_NOT_VERIFIED:
    "직접 작성한 바깥놀이 문장의 연령 적합성은 자동으로 확인하지 못했어요. 교사가 내용을 확인해주세요.",
  ACTIVITY_AGE_UNSUPPORTED:
    "우리 반 연령을 모두 지원하지 않는 참고 활동이 있어요. 활동 내용과 대상 연령을 확인해주세요.",
  // 안전교육 배치 검증(safety_placement). 서버 문구는 영어라 코드로 옮긴다.
  SAFETY_ANNUAL_HOURS_NOT_VERIFIED:
    "계획안에는 교육 시간이 없어 안전교육 연간 법정 시간은 자동으로 확인하지 못했어요. 실제 교육 시간은 따로 확인해주세요.",
  SAFETY_OFFICIAL_GROUNDING_MISSING:
    "법정 안전교육 칸의 공식 교육 내용 근거를 확인하지 못했어요. 안전교육 내용을 확인해주세요.",
  SAFETY_SUPPLEMENTAL_GROUNDING_INVALID:
    "생활안전 칸의 참고 근거를 확인하지 못했어요. 안전교육 내용을 확인해주세요.",
};
const SAVE_LABEL = { idle: "", saving: "저장 중…", saved: "저장됨", failed: "저장하지 못했어요" };

function describe(e: unknown, fallback: string): string {
  if (e instanceof ApiError) return e.message;
  return e instanceof Error ? e.message : fallback;
}

export default function MonthlyPlanEditor({
  plan,
  onPlan,
  onConflict,
  onDelete,
  note,
  flushRef,
}: {
  plan: MonthlyPlan;
  onPlan: (plan: MonthlyPlan) => void;
  /** 409 — 그 사이 바뀌었다. 다시 불러오는 일은 화면이 한다. */
  onConflict: () => void;
  onDelete: () => void;
  /** 양식 출처 한 줄. */
  note: string;
  /** 화면이 반 · 월을 옮기기 전에 부른다 — 열린 입력을 저장하고 끝까지 기다린다. 못 저장한 칸이 남으면 false. */
  flushRef?: RefObject<(() => Promise<boolean>) | null>;
}) {
  const [live, setLive] = useState<Record<string, string>>({});
  const [selected, setSelected] = useState<string | null>(null);
  const [bumps, setBumps] = useState<Record<string, number>>({});
  const [status, setStatus] = useState<keyof typeof SAVE_LABEL>("idle");
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [problem, setProblem] = useState("");
  const [zoom, setZoom] = useState<SheetZoom>({ mode: "fit", percent: 100 });
  const hwpx = useHwpxDownload(setMessage);
  // 저장 줄 — 앞 요청이 끝나야 다음이 그 revision 으로 간다. 화면이 내려간 뒤에는 저장만 마친다.
  const queue = useRef<Promise<void>>(Promise.resolve());
  const latest = useRef(plan);
  useEffect(() => {
    latest.current = plan; // 다시 불러온 최신 계획안도 받는다.
  }, [plan]);
  // 저장하지 못한 칸과 그 글. 다시 저장하거나 서버 값과 같아질 때까지 남는다.
  const failed = useRef(new Map<string, string>());
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const confirmed = plan.status === "CONFIRMED";
  const locked = !!busy;
  const weeks = plan.weeks.filter((w) => w.active);
  const sections = plan.sections
    .filter((s) => s.visible && s.role === "CONTENT")
    .sort((a, b) => a.order - b.order);
  const cells = sections.flatMap((s) => s.cells.map((cell) => ({ section: s, cell })));
  const picked = confirmed ? null : (cells.find((c) => c.cell.item_id === selected) ?? null);
  const blank = cells.some(({ cell }) => !cell.value.trim());

  const accept = (next: MonthlyPlan) => {
    latest.current = next;
    if (mounted.current) onPlan(next);
  };
  const conflict = () => {
    if (!mounted.current) return;
    setStatus("idle");
    onConflict();
  };
  /** 줄 끝에 붙인다. 실패해도 줄은 이어진다. */
  const enqueue = (job: () => Promise<void>) => {
    const run = queue.current.then(job);
    queue.current = run.catch(() => {});
    return run;
  };

  function saveCell(itemId: string, text: string) {
    const drop = () =>
      setLive((d) =>
        d[itemId] === text
          ? Object.fromEntries(Object.entries(d).filter(([k]) => k !== itemId))
          : d,
      );
    // 바뀐 것이 없으면(보낼 것이 없던 칸) 저장 표시는 그대로 둔다.
    const settled = (changed: boolean) => {
      failed.current.delete(itemId);
      if (!mounted.current) return;
      drop();
      if (changed) setStatus(failed.current.size ? "failed" : "saved");
    };
    // 같은지는 보내기 직전에 본다 — 앞 저장이 끝난 뒤의 서버 값과 비교해야 마지막 입력을 버리지 않는다.
    enqueue(async () => {
      const cur = latest.current;
      const now = cur.sections.flatMap((s) => s.cells).find((c) => c.item_id === itemId)?.value;
      if (now === text) return settled(failed.current.has(itemId));
      if (mounted.current) setStatus("saving");
      try {
        accept(await editMonthlyCell(cur.id, itemId, text, cur.revision));
        settled(true);
      } catch (e) {
        if (isSaveConflict(e)) return conflict();
        failed.current.set(itemId, text);
        if (!mounted.current) return;
        setStatus("failed");
        setMessage(
          "저장하지 못했어요. 쓴 글은 그대로 두었어요 — 「다시 저장」을 눌러 주세요. " +
            describe(e, ""),
        );
      }
    }).catch(() => {});
  }
  const retry = () => failed.current.forEach((text, itemId) => saveCell(itemId, text));

  /** 열린 입력창을 닫아 마지막 글을 줄에 넣고 줄이 빌 때까지 기다린다. 못 저장한 칸이 남으면 false. */
  async function flush() {
    (document.activeElement as HTMLElement | null)?.blur();
    // 기다리는 사이 줄에 붙은 저장까지 기다린다.
    let tail;
    do {
      tail = queue.current;
      await tail;
    } while (tail !== queue.current);
    if (!failed.current.size) return true;
    if (mounted.current) setProblem("저장하지 못한 칸이 있어요. 「다시 저장」한 뒤 해 주세요.");
    return false;
  }
  useEffect(() => {
    if (!flushRef) return;
    // 반 · 월 이동 — 기다리는 동안 입력창 · 단추를 잠가 새 글이 이동 뒤로 새지 않게 한다.
    flushRef.current = async () => {
      if (busy) return false;
      setBusy("move");
      try {
        return await flush();
      } finally {
        if (mounted.current) setBusy("");
      }
    };
    return () => {
      flushRef.current = null;
    };
  });
  // 입력 중 · 저장 중 · 저장 실패 글이 있으면 새로고침 · 닫기 전에 묻는다.
  const unsent = status === "saving" || status === "failed" || Object.keys(live).length > 0;
  useEffect(() => {
    if (!unsent || confirmed) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [unsent, confirmed]);

  /** 열린 입력창을 닫아 마지막 글을 줄에 넣고, 줄이 빌 때까지 기다린 뒤 `job` 을 한다. */
  async function afterSaves(
    key: string,
    job: (cur: MonthlyPlan) => Promise<MonthlyPlan>,
    done: string,
  ) {
    if (busy) return;
    setBusy(key);
    setMessage("");
    setProblem("");
    try {
      if (!(await flush())) return;
      const next = await enqueue(async () => accept(await job(latest.current))).then(
        () => latest.current,
      );
      setBumps((b) => ({ ...b, "*": (b["*"] ?? 0) + 1 }));
      setMessage(done);
      return next;
    } catch (e) {
      if (isSaveConflict(e)) return conflict();
      setProblem(describe(e, "처리하지 못했어요."));
    } finally {
      if (mounted.current) setBusy("");
    }
  }

  const regenerate = (cell: MonthlyCell) => {
    if (!window.confirm("이 칸을 다시 만들면 현재 내용이 바뀌어요. 계속할까요?")) return;
    afterSaves(
      cell.item_id,
      (cur) => regenerateMonthlyCell(cur.id, cell.item_id, cur.revision),
      "다시 만들었어요.",
    );
  };
  const confirm = () =>
    afterSaves(
      "confirm",
      (cur) => confirmMonthlyPlan(cur.id, cur.revision),
      "확정했어요. 이제 고칠 수 없어요.",
    );

  const label = (section: (typeof sections)[number], cell: MonthlyCell) => {
    const week = weeks.find((w) => w.week_id === cell.week_id)?.label;
    return sectionName(section.section_key, section.label) + (week ? ` · ${week}` : "");
  };
  const at = {
    selected: picked?.cell.item_id ?? null,
    onSelect: confirmed ? undefined : setSelected,
  };
  const shown = (cell: MonthlyCell) => live[cell.item_id] ?? cell.value;
  const stamp = (id: string) => `${bumps["*"] ?? 0}:${bumps[id] ?? 0}`;

  return (
    <>
      <div className={styles.meta}>
        <span className={ws.badge}>{confirmed ? "확정됨" : "초안"}</span>
        <span>{plan.target_month}</span>
        {plan.parent.theme && <span className={ws.muted}>연간 주제 · {plan.parent.theme}</span>}
        <span className={ws.muted}>{note}</span>
        {blank && <span role="status">빈 칸이 있어요 (확정을 막지 않아요)</span>}
        {!confirmed && <span role="status">{SAVE_LABEL[status]}</span>}
        {!confirmed && status === "failed" && (
          <button type="button" className={ws.secondary} disabled={locked} onClick={retry}>
            다시 저장
          </button>
        )}
        <span role="status">{message}</span>
      </div>
      {problem && <p role="alert">{problem}</p>}
      <div className={ws.actions} style={{ marginBottom: 12 }}>
        {confirmed ? (
          <button
            type="button"
            className={ws.primary}
            disabled={hwpx.exporting}
            onClick={() => hwpx.download(() => downloadMonthlyHwpx(plan.id))}
          >
            {hwpx.exporting ? "파일 만드는 중…" : "한글 파일로 내려받기"}
          </button>
        ) : (
          <>
            <button type="button" className={ws.primary} disabled={locked} onClick={confirm}>
              {busy === "confirm" ? "확정하는 중…" : "확정하기"}
            </button>
            <span className={ws.muted}>
              확정하면 고칠 수 없어요 · 확정하면 한글 파일로 내려받을 수 있어요
            </span>
            <button type="button" className={ws.secondary} disabled={locked} onClick={onDelete}>
              지우고 다시 만들기
            </button>
          </>
        )}
      </div>
      <MonthlyHistory id={plan.id} />
      {plan.verification.findings.length > 0 && (
        <ul className={ws.list} style={{ margin: "12px 0" }}>
          {[
            ...new Map(
              plan.verification.findings.map((f) => [`${f.code}|${f.section_key}`, f]),
            ).values(),
          ].map((f, i) => (
            <li key={i} className={ws.hint}>
              {FINDINGS[f.code] ?? f.message}
            </li>
          ))}
        </ul>
      )}
      <div className={styles.layout} style={{ marginTop: 12 }}>
        <aside className={styles.side} aria-label="칸 편집">
          <h2>칸 편집</h2>
          {confirmed && <p>확정한 계획안은 고칠 수 없어요.</p>}
          {!confirmed && !picked && <p>문서의 칸을 누르면 여기서 고칠 수 있어요.</p>}
          {picked && (
            <>
              <PlayCellEditor
                key={picked.cell.item_id + ":" + stamp(picked.cell.item_id)}
                id="monthly-cell"
                label={label(picked.section, picked.cell)}
                value={shown(picked.cell)}
                allowBlank
                maxLength={Infinity}
                readOnly={locked}
                onDraft={(text) => setLive((d) => ({ ...d, [picked.cell.item_id]: text }))}
                onSave={(text) => saveCell(picked.cell.item_id, text)}
                onRevert={() =>
                  setLive((d) =>
                    Object.fromEntries(
                      Object.entries(d).filter(([k]) => k !== picked.cell.item_id),
                    ),
                  )
                }
              />
              {picked.cell.state === "EMPTY_UNRESOLVED" && (
                <p>근거가 없어 비워 두었어요. 직접 적어주세요.</p>
              )}
              {picked.cell.evidence.length > 0 && (
                <p>
                  근거 ·{" "}
                  {[
                    ...new Set(
                      picked.cell.evidence.map((e) =>
                        e.source_type === "SAFETY_RULE"
                          ? "안전교육 기준"
                          : e.display_name || e.source_type,
                      ),
                    ),
                  ].join(" · ")}
                </p>
              )}
              {REGENERATABLE.has(picked.section.section_key) &&
                (plan.generation_mode !== "RULE_ONLY" ||
                  picked.section.section_key === "outdoor_play") && (
                  <button
                    type="button"
                    className={ws.link}
                    disabled={locked}
                    onClick={() => regenerate(picked.cell)}
                  >
                    {busy === picked.cell.item_id ? "…" : "↻ 이 칸만 다시 만들기"}
                  </button>
                )}
            </>
          )}
        </aside>
        <SheetFrame
          label="월간계획안 미리보기"
          title={`${plan.target_month.slice(0, 4)}년 ${plan.month}월 월간계획안`}
          zoom={zoom}
          onZoomChange={setZoom}
        >
          <table className={styles.doc}>
            <thead>
              <tr>
                <th scope="col">구분</th>
                {weeks.map((w) => (
                  <th key={w.week_id} scope="col">
                    {w.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sections.map((section) => {
                const byWeek = new Map(section.cells.map((c) => [c.week_id, c]));
                const one = section.cells[0];
                return (
                  <tr key={section.section_key}>
                    <th scope="row">{sectionName(section.section_key, section.label)}</th>
                    {section.repeat_by !== "WEEK" ? (
                      <td colSpan={Math.max(weeks.length, 1)}>
                        {one && <Cell {...at} id={one.item_id} value={shown(one)} />}
                      </td>
                    ) : (
                      weeks.map((w) => {
                        const cell = byWeek.get(w.week_id);
                        return (
                          <td key={w.week_id}>
                            {cell && <Cell {...at} id={cell.item_id} value={shown(cell)} />}
                          </td>
                        );
                      })
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </SheetFrame>
      </div>
    </>
  );
}

const EVENT: Record<MonthlyAuditEvent["type"], string> = {
  CREATED: "만들었어요",
  TEACHER_EDITED: "고쳤어요",
  REGENERATED: "다시 만들었어요",
  CONFIRMED: "확정했어요",
};
const short = (text: string) => {
  const t = text.trim();
  return t ? "「" + (t.length > 30 ? t.slice(0, 30) + "…" : t) + "」" : "(빈 칸)";
};

/** 「변경 이력 보기」 — 놀이 월간과 같은 자리 · 같은 모양. 만들 때 칸마다 남는 CREATED 는 한 줄로 접는다. */
function MonthlyHistory({ id }: { id: number }) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<{ events: MonthlyAuditEvent[] | null; failed: boolean }>({
    events: null,
    failed: false,
  });
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    getMonthlyPlanAudit(id, undefined, controller.signal).then(
      ({ items }) => !controller.signal.aborted && setState({ events: items, failed: false }),
      () => !controller.signal.aborted && setState({ events: null, failed: true }),
    );
    return () => controller.abort();
  }, [id, open]);
  const events = (state.events ?? []).filter((e) => EVENT[e.type]);
  const created = events.filter((e) => e.type === "CREATED" && e.scope === "CELL");
  const rows = events.filter((e) => !created.includes(e) || e === created[0]);
  return (
    <div>
      <button
        type="button"
        className={ws.secondary}
        onClick={() => {
          setState({ events: null, failed: false });
          setOpen(!open);
        }}
      >
        {open ? "변경 이력 접기" : "변경 이력 보기"}
      </button>
      {open && state.failed && <p role="alert">변경 이력을 불러오지 못했어요.</p>}
      {open && !state.failed && !state.events && <p role="status">변경 이력을 읽고 있어요.</p>}
      {open && state.events && (
        <ol aria-label="변경 이력">
          {rows.map((e, i) => (
            <li key={i}>
              <time dateTime={e.occurred_at}>
                {new Date(e.occurred_at).toLocaleString("ko-KR", {
                  month: "numeric",
                  day: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </time>{" "}
              {e === created[0]
                ? `처음 만들어진 칸 ${created.length}개`
                : EVENT[e.type] +
                  (e.value_change
                    ? ` ${short(e.value_change.before)} → ${short(e.value_change.after)}`
                    : "")}
            </li>
          ))}
          {!rows.length && <li className={ws.muted}>아직 이력이 없어요</li>}
        </ol>
      )}
    </div>
  );
}
