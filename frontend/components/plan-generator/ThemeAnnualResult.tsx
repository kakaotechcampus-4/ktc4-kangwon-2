"use client";
import { useEffect, useRef, useState } from "react";
import {
  confirmAnnualPlan,
  errorFields,
  getAnnualPlan,
  isRejectedSave,
  isSaveConflict,
  putAnnualMonth,
} from "@/lib/api/plans";
import type { AnnualPlan } from "@/lib/api/types";
import {
  cleanSlots,
  moveSlot,
  removeSlot,
  setSlot,
  slotMismatch,
} from "@/lib/plan-generator/subThemeSlots";
import AnnualFrame, {
  AsideStrip,
  BigView,
  BUTTON,
  POPOVER,
  tabClass,
  useSheetZoom,
} from "./AnnualFrame";
import AnnualThemeSheet, { type ThemeSlot } from "./AnnualThemeSheet";
import PlayMonthlyConfirm from "./PlayMonthlyConfirm";
import { PlanMemoNote } from "./PlanMemo";

type Draft = { theme: string; sub_themes: string[] };
const SAVE_LABEL = {
  idle: "작성 중",
  saving: "작성 중 · 저장 중…",
  saved: "작성 중 · 자동 저장됨",
  failed: "저장하지 못했어요",
};
const draftsOf = (plan: AnnualPlan) =>
  Object.fromEntries(
    plan.months.map((m) => [m.month, { theme: m.theme, sub_themes: m.sub_themes }]),
  ) as Record<number, Draft>;
const clean = (value: Draft): Draft => ({
  theme: value.theme.trim(),
  sub_themes: cleanSlots(value.sub_themes),
});
const same = (a: Draft, b: Draft) =>
  a.theme === b.theme && a.sub_themes.join("\n") === b.sub_themes.join("\n");
const slotInputId = (slot: ThemeSlot) => `annual-slot-${slot.month}-${slot.slot}`;
const INPUT = "rounded-xl border border-[#ddd6ca] px-3 py-2 text-[15px] leading-relaxed";
const SMALL =
  "min-h-[36px] rounded-lg border border-[#e8e2d8] px-2 text-xs text-[#5c5243] disabled:opacity-40";

/**
 * ⑤ 월별 주제형 다듬기. 왼쪽은 「칸 편집」 하나 — 생활주제와 주차별 소주제 배치(위 · 아래 · 추가 · 삭제 · 글 고치기).
 * AI 후보 탭은 서버 API 가 없어 두지 않는다. 한 달 저장은 주제와 소주제를 같이 보낸다(`putAnnualMonth`).
 */
const SHEET_WIDTH = 860;

export default function ThemeAnnualResult({
  plan,
  className,
  notice,
  onConflict,
  onConfirmed,
}: {
  plan: AnnualPlan;
  className: string;
  notice?: string;
  onConflict: () => Promise<void>;
  onConfirmed: (plan: AnnualPlan) => void;
}) {
  const [drafts, setDrafts] = useState(() => draftsOf(plan));
  const [selected, setSelected] = useState<ThemeSlot>({
    month: plan.months[0].month,
    slot: "theme",
  });
  const [status, setStatus] = useState<keyof typeof SAVE_LABEL>("idle");
  const [message, setMessage] = useState("");
  const [flagged, setFlagged] = useState<number[]>([]);
  const [undo, setUndo] = useState<{ month: number; before: Draft }[]>([]);
  // 문서 기준 폭(AnnualThemeSheet 최대 폭). 배율 도구가 이 폭을 문서 칸에 맞춘다.
  const docBox = useRef<HTMLDivElement>(null);
  const sheetZoom = useSheetZoom(docBox, SHEET_WIDTH);
  const [asking, setAsking] = useState(false);
  const [confirming, setConfirming] = useState(false);
  // 서버가 받은 값(성공 응답 뒤에만 바뀐다) · 마지막으로 저장 줄에 넣은 값 · 저장 줄(한 번에 하나씩)
  // · 저장 실패한 달들 · 확정 중 잠금. 이벤트 핸들러에서만 읽는다.
  const saved = useRef(draftsOf(plan));
  const queued = useRef(draftsOf(plan));
  const queue = useRef<Promise<void>>(Promise.resolve());
  const failed = useRef(new Set<number>());
  const locked = useRef(false);
  const month = plan.months.find((m) => m.month === selected.month)!;
  const weekCount = (m: number) => plan.months.find((item) => item.month === m)!.week_count;
  const draft = drafts[selected.month];
  const sheetMonths = plan.months.map((m) => ({ ...m, ...drafts[m.month] }));

  // 고른 칸의 입력창으로 포커스를 옮긴다(문서 칸을 눌렀을 때).
  useEffect(() => {
    document.getElementById(slotInputId(selected))?.focus();
  }, [selected]);

  // 문서에서 아직 없는 주 칸을 누르면 그 자리까지 빈 칸을 늘린다(저장 값은 같다).
  function select(slot: ThemeSlot) {
    if (locked.current) return;
    const list = drafts[slot.month].sub_themes;
    if (typeof slot.slot === "number" && slot.slot >= list.length)
      change(slot.month, { sub_themes: [...list, ...Array(slot.slot + 1 - list.length).fill("")] });
    setSelected(slot);
  }

  function change(monthNo: number, next: Partial<Draft>) {
    if (locked.current) return;
    setDrafts((all) => ({ ...all, [monthNo]: { ...all[monthNo], ...next } }));
  }

  // 그 달을 저장 줄에 넣는다. 빈 소주제는 빼고 보낸다. 서버 값과 같은지는 앞 저장이 끝난 실행 시점에 본다.
  function save(monthNo: number, value: Draft, record = true) {
    if (locked.current) return;
    const body = clean(value);
    const before = queued.current[monthNo];
    if (!body.theme) {
      setMessage(`${monthNo}월 생활주제를 비울 수 없어요.`);
      return;
    }
    if (same(body, before) && !failed.current.has(monthNo)) return;
    queued.current = { ...queued.current, [monthNo]: body };
    if (record && !same(body, before)) setUndo((list) => [...list, { month: monthNo, before }]);
    setStatus("saving");
    setMessage("");
    const synced = () => {
      failed.current.delete(monthNo);
      setStatus(failed.current.size ? "failed" : "saved");
    };
    queue.current = queue.current.then(() => {
      if (same(body, saved.current[monthNo])) return synced();
      return putAnnualMonth(plan.id, monthNo, body).then(
        () => {
          saved.current = { ...saved.current, [monthNo]: body };
          synced();
        },
        async (error) => {
          // 이 요청이 그 달의 마지막 요청일 때만(값이 아니라 같은 객체인지로 본다) 서버 값으로
          // 되돌린다 — 같은 값을 다시 넣어도 다시 보낸다. 뒤에 요청이 있으면 그 결과에 맡긴다.
          const latest = queued.current[monthNo] === body;
          if (latest) queued.current = { ...queued.current, [monthNo]: saved.current[monthNo] };
          if (isSaveConflict(error)) return onConflict();
          if (!latest) return;
          if (isRejectedSave(error)) {
            // 서버가 받지 않았다 — 그 달을 서버 값으로 되돌린다.
            failed.current.delete(monthNo);
            const server = saved.current[monthNo];
            setDrafts((all) => ({ ...all, [monthNo]: server })); // 확정 잠금 중에도 되돌린다
            setStatus(failed.current.size ? "failed" : "idle");
            setMessage(`${monthNo}월은 저장하지 못해 원래대로 되돌렸어요.`);
            return;
          }
          failed.current.add(monthNo);
          setStatus("failed");
        },
      );
    });
  }

  function saveSelected() {
    save(selected.month, drafts[selected.month]);
  }

  // 이동 · 삭제 · 추가는 바로 저장한다(빈 칸 추가는 저장 값이 같아 보내지 않는다).
  function editSlots(next: string[], focus: ThemeSlot["slot"]) {
    const value = { ...draft, sub_themes: next };
    change(selected.month, value);
    setSelected({ month: selected.month, slot: focus });
    save(selected.month, value);
  }

  function stepBack() {
    const last = undo[undo.length - 1];
    if (!last) return;
    setUndo(undo.slice(0, -1));
    change(last.month, last.before);
    setSelected({ month: last.month, slot: "theme" });
    save(last.month, last.before, false);
  }

  async function confirm() {
    // 마지막 입력을 저장 줄에 넣은 뒤 잠근다 — 잠근 뒤에는 새 편집이 확정 뒤로 밀리지 않는다.
    (document.activeElement as HTMLElement | null)?.blur();
    locked.current = true;
    setConfirming(true);
    setMessage("");
    await queue.current;
    try {
      // 화면 값과 서버 값이 다른 달(저장 실패 · 빈 생활주제)이 있으면 옛 내용으로 확정하지 않는다.
      const unsaved = plan.months
        .map((m) => m.month)
        .filter(
          (m) =>
            failed.current.has(m) ||
            !drafts[m].theme.trim() ||
            !same(clean(drafts[m]), saved.current[m]),
        );
      if (unsaved.length) {
        setSelected({ month: unsaved[0], slot: "theme" });
        setMessage(
          `${unsaved.map((m) => m + "월").join(" · ")}은 아직 저장되지 않았어요. 생활주제를 채우거나 다시 저장한 뒤 확정해 주세요.`,
        );
        return;
      }
      await confirmAnnualPlan(plan.id);
      onConfirmed((await getAnnualPlan(plan.id)) as AnnualPlan);
    } catch (error) {
      if (isSaveConflict(error)) return void (await onConflict());
      const months = isRejectedSave(error) ? errorFields(error).map(Number).filter(Boolean) : [];
      if (!months.length)
        return setMessage(error instanceof Error ? error.message : "확정하지 못했어요.");
      setFlagged(months);
      setSelected({ month: months[0], slot: "theme" });
      setMessage(
        `${months.map((m) => m + "월").join(" · ")}은 소주제 수가 주 수와 달라요. 주마다 하나씩 맞춰 주세요.`,
      );
    } finally {
      locked.current = false;
      setAsking(false);
      setConfirming(false);
    }
  }

  const strip =
    selected.slot === "theme"
      ? `${selected.month}월 · 생활주제 칸을 골랐어요`
      : `${selected.month}월 · ${selected.slot < month.week_count ? selected.slot + 1 + "주" : "남는"} 소주제 칸을 골랐어요`;
  const filled = cleanSlots(draft.sub_themes).length;
  const aside = (
    <>
      <div className="flex gap-5 border-b border-[#efeae2] px-6 pt-2">
        <span className={tabClass(true)}>칸 편집</span>
      </div>
      <AsideStrip>{strip}</AsideStrip>
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-6 py-5">
        <label className="flex flex-col gap-1.5">
          <span className="text-[13px] text-[#5c5243]">{selected.month}월 생활주제</span>
          <input
            className={INPUT}
            id={slotInputId({ month: selected.month, slot: "theme" })}
            value={draft.theme}
            readOnly={confirming}
            onChange={(e) => change(selected.month, { theme: e.target.value })}
            onBlur={saveSelected}
          />
        </label>
        <section className="flex flex-col gap-2" aria-label={`${selected.month}월 소주제`}>
          <h2 className="m-0 flex items-baseline justify-between text-[15px] font-bold">
            소주제
            <span className="text-xs font-normal text-[#5c5243]">
              {month.week_count}주 · {filled}개 넣음
            </span>
          </h2>
          {slotMismatch(draft.sub_themes, month.week_count) && (
            <p role="status" className="m-0 text-[13px] font-bold text-[#b3261e]">
              주마다 하나씩 — {month.week_count}개를 맞춰야 확정할 수 있어요.
            </p>
          )}
          {draft.sub_themes.map((value, i) => (
            <div key={i} className="flex items-center gap-1.5">
              <span className="w-9 shrink-0 text-xs font-bold text-[#5e4b96]">
                {i < month.week_count ? i + 1 + "주" : "남음"}
              </span>
              <input
                aria-label={`${selected.month}월 ${i + 1}번째 소주제`}
                className={`${INPUT} min-w-0 flex-1 ${selected.slot === i ? "border-[#7053a0] bg-[#f6f1fb]" : ""}`}
                id={slotInputId({ month: selected.month, slot: i })}
                value={value}
                readOnly={confirming}
                onFocus={() => setSelected({ month: selected.month, slot: i })}
                onChange={(e) =>
                  change(selected.month, {
                    sub_themes: setSlot(draft.sub_themes, i, e.target.value),
                  })
                }
                onBlur={saveSelected}
              />
              <button
                type="button"
                aria-label="위로"
                className={SMALL}
                disabled={i === 0 || confirming}
                onClick={() => editSlots(moveSlot(draft.sub_themes, i, -1), i - 1)}
              >
                ↑
              </button>
              <button
                type="button"
                aria-label="아래로"
                className={SMALL}
                disabled={i === draft.sub_themes.length - 1 || confirming}
                onClick={() => editSlots(moveSlot(draft.sub_themes, i, 1), i + 1)}
              >
                ↓
              </button>
              <button
                type="button"
                aria-label="삭제"
                className={SMALL}
                disabled={confirming}
                onClick={() => editSlots(removeSlot(draft.sub_themes, i), "theme")}
              >
                삭제
              </button>
            </div>
          ))}
          <button
            type="button"
            className="min-h-[40px] rounded-lg border border-dashed border-[#c5b7dd] text-sm font-bold text-[#5e4b96] disabled:opacity-40"
            disabled={confirming}
            onClick={() => editSlots([...draft.sub_themes, ""], draft.sub_themes.length)}
          >
            + 소주제 추가
          </button>
        </section>
        <p className="m-0 text-[13px] text-[#5c5243]">고치면 오른쪽 문서에 바로 반영돼요</p>
      </div>
    </>
  );
  const sheetTitle = `${className ? className + " " : ""}${plan.school_year}학년도 연간 보육계획안`;
  return (
    <AnnualFrame
      title={`${plan.school_year} 연간계획안`}
      format={plan.format}
      status={
        <span className="flex items-center gap-3">
          {SAVE_LABEL[status]}
          <PlanMemoNote plan={plan} />
        </span>
      }
      notice={
        <>
          {notice && (
            <p role="status" className="m-0 text-sm text-[#5c5243]">
              {notice}
            </p>
          )}
          {message && (
            <p role="alert" className="m-0 text-sm font-bold text-[#b3261e]">
              {message}
            </p>
          )}
          {status === "failed" && (
            <button
              type="button"
              className={BUTTON.outline + " self-start"}
              disabled={confirming}
              onClick={() => failed.current.forEach((m) => save(m, drafts[m], false))}
            >
              다시 저장
            </button>
          )}
        </>
      }
      actions={
        <>
          <button
            type="button"
            className={BUTTON.quiet}
            disabled={!undo.length || confirming}
            onClick={stepBack}
          >
            되돌리기
          </button>
          <div className="relative">
            <button
              type="button"
              className={BUTTON.primary}
              disabled={confirming}
              onClick={() => setAsking(true)}
            >
              확정하기
            </button>
            {asking && (
              <div className={POPOVER}>
                <PlayMonthlyConfirm
                  message="확정하면 확정을 풀기 전까지 고칠 수 없어요. 이 내용으로 월간계획안을 만들게 돼요."
                  yes={confirming ? "확정하는 중…" : "확정하기"}
                  no="더 다듬기"
                  disabled={confirming}
                  onYes={confirm}
                  onNo={() => setAsking(false)}
                />
              </div>
            )}
          </div>
        </>
      }
      aside={aside}
      docLabel="소주제형 기본 양식"
      docHint={
        <div className="flex items-center gap-1">
          {sheetZoom.tools}
          <span className="ml-2">
            <BigView
              pages={1}
              render={() => <AnnualThemeSheet title={sheetTitle} months={sheetMonths} />}
            />
          </span>
        </div>
      }
    >
      <div ref={docBox}>
        <div style={{ zoom: sheetZoom.percent / 100, width: SHEET_WIDTH }} className="mx-auto">
          <AnnualThemeSheet
            title={sheetTitle}
            months={sheetMonths}
            selected={selected}
            flagged={flagged.filter((m) => slotMismatch(drafts[m].sub_themes, weekCount(m)))}
            onSelect={select}
          />
        </div>
      </div>
    </AnnualFrame>
  );
}
