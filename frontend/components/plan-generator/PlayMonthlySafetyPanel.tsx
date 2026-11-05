"use client";
import type { DragEvent } from "react";

const KIND = { STATUTORY: "법정", SUPPLEMENTAL: "추가" } as const;

/** 패널이 읽는 칸만 — 놀이 월간과 v1 월간이 같이 쓴다. */
type SafetyPlan = {
  weeks: { week_id: string; label: string }[];
  safety_candidates: SafetyCandidate[];
  safety_weeks: { week_id: string; candidate_item_id: string | null }[];
};
type SafetyCandidate = {
  kind: keyof typeof KIND;
  category_id?: string | null;
  cell: { item_id: string; value: string };
};

// ponytail: Core `STATUTORY_SHORT_LABELS` 를 옮겨 적었다 — 서버가 놀이 월간에도 표시 이름을 주면(v1 의 display_value 처럼) 그걸 쓴다.
const TOPIC: Record<string, string> = {
  traffic_safety: "교통안전",
  sexual_violence_prevention: "성폭력 예방",
  child_abuse_prevention: "아동학대 예방",
  missing_and_abduction_prevention: "실종·유괴 예방",
  disaster_preparedness_safety: "재난대비",
  infectious_disease_and_drug_misuse_prevention: "감염병·약물 예방",
};
/** 안전교육 칸 머리 「[교통안전]」의 이름 — 법정은 영역 이름, 그 밖은 생활안전. */
export const safetyTopic = (c: SafetyCandidate) =>
  c.kind === "STATUTORY" ? (TOPIC[c.category_id ?? ""] ?? KIND.STATUTORY) : "생활안전";

/** 후보 카드를 끌 때 넘기는 글의 앞부분 — 뒤는 후보 item_id. 문서의 안전교육 칸 · 「넣은 안전교육」 줄이 받는다. */
export const SAFETY_DRAG = "safety-candidate:";
/** 후보 카드를 놓을 수 있는 곳 — `prefix` 로 시작하는 끌기만 받는다(안전교육은 놓으면 그 주에 둔다). */
export const dropTo = (onDrop: (candidateItemId: string) => void, prefix = SAFETY_DRAG) => ({
  onDragOver: (event: DragEvent<HTMLElement>) => {
    event.preventDefault();
    event.currentTarget.dataset.drop = "";
  },
  onDragLeave: (event: DragEvent<HTMLElement>) => delete event.currentTarget.dataset.drop,
  onDrop: (event: DragEvent<HTMLElement>) => {
    event.preventDefault();
    delete event.currentTarget.dataset.drop;
    const data = event.dataTransfer.getData("text/plain");
    if (data.startsWith(prefix)) onDrop(data.slice(prefix.length));
  },
});

export const DROP = "[&[data-drop]]:bg-[#efe7f8]";
export const CARD = "flex items-center gap-3 rounded-md border px-4 py-2.5";
/** 넣은 후보 카드 — 안전교육 · 훈련 · 주간 후보가 같이 쓴다. */
export const PICKED = "border-[#7053a0] bg-[#f6f1fb]";
export const PUT =
  "min-h-[36px] shrink-0 rounded-lg border border-[#ddd6ca] bg-white px-3 text-sm font-bold text-[#5e4b96] disabled:opacity-40";
/** 연간 「AI 후보」 패널의 작은 [+ 넣기] 단추. */
export const SMALL =
  "min-h-[36px] shrink-0 rounded-lg border border-[#ddd6ca] px-3 text-xs font-bold text-[#5e4b96] disabled:opacity-40";
/** 끌 수 있다는 손잡이(점 여섯 개) — 연간 「AI 후보」 패널과 같다. */
export const GRIP = (
  <svg
    aria-hidden="true"
    viewBox="0 0 10 16"
    width="10"
    height="16"
    className="shrink-0 text-[#b8ae9f]"
    fill="currentColor"
  >
    {[2, 8, 14].map((y) => [2, 8].map((x) => <circle key={`${x}${y}`} cx={x} cy={y} r="1.5" />))}
  </svg>
);

/**
 * Ⓜ3 AI 후보 — 연간 「AI 후보」 패널과 같은 모양(머리 · 넣은 목록 · 후보 카드).
 * 맨 위 「안전교육」 아래 주마다 한 줄(넣은 안전교육), 그 아래 고른 주의 후보 카드.
 * [+ 넣기]는 그 주에 두고, 넣은 후보는 후보 목록에서 숨는다(위 주 줄의 [빼기]로 되돌린다).
 * 카드나 넣은 주 줄을 끌어(점 여섯 개) 주 줄이나 문서의 안전교육 칸에 놓아도 그 주에 둔다 — 같은 후보를 여러 주에 둘 수도 있다.
 * `onWeek` 가 있으면 주 줄을 눌러 그 주로 바꾸고, [+ 넣기] 뒤에는 다음 주로 넘어간다.
 */
export default function PlayMonthlySafetyPanel({
  plan,
  weekId,
  onPlace,
  onWeek,
  disabled,
}: {
  plan: SafetyPlan;
  weekId: string;
  onPlace: (weekId: string, candidateItemId: string | null) => void;
  onWeek?: (weekId: string) => void;
  disabled: boolean;
}) {
  const label = (id: string) => plan.weeks.find((w) => w.week_id === id)?.label ?? id;
  const here = plan.safety_weeks.find((w) => w.week_id === weekId)?.candidate_item_id ?? null;
  // 어느 주에든 넣은 후보는 위 주 줄에만 보이고 후보 목록에서는 숨는다(원래 순서 그대로).
  const placed = new Set(plan.safety_weeks.map((w) => w.candidate_item_id));
  const rest = plan.safety_candidates.filter((c) => !placed.has(c.cell.item_id));
  const next = plan.weeks[plan.weeks.findIndex((w) => w.week_id === weekId) + 1]?.week_id;
  const put = (id: string) => {
    onPlace(weekId, id);
    // 1주에 넣으면 2주로 — 마지막 주면 그대로 둔다.
    if (onWeek && next) onWeek(next);
  };
  const filled = plan.weeks.filter((w) =>
    plan.safety_weeks.some((s) => s.week_id === w.week_id && s.candidate_item_id),
  ).length;
  return (
    <section aria-label="안전교육" className="flex flex-col gap-5">
      <section className="flex flex-col gap-2">
        <h2 className="m-0 flex items-baseline justify-between text-[18px] font-bold leading-tight">
          안전교육
          <span className="text-[13px] font-normal text-ink-soft">
            {filled}/{plan.weeks.length}주 채웠어요
          </span>
        </h2>
        <PlacedWeeks
          plan={plan}
          weekId={weekId}
          onPlace={onPlace}
          onWeek={onWeek}
          disabled={disabled}
        />
      </section>
      <section className="flex flex-col gap-1">
        <h3 className="m-0 flex items-center justify-between gap-2 text-[15px] font-bold text-ink">
          {label(weekId)} 안전교육 후보
          {/* 우리 반 화면의 복숭아색 쪽지 안내처럼. */}
          {!here && (
            <span className="shrink-0 rounded-full bg-peach-tint px-2.5 py-0.5 font-body text-[12px] font-semibold text-peach-ink">
              아직 비어 있어요
            </span>
          )}
        </h3>
        <p className="m-0 mb-1 text-[13px] text-ink-soft">
          {rest.length === 0
            ? "후보를 다 넣었어요. 위 주의 [빼기]로 되돌릴 수 있어요."
            : `${onWeek && next ? "넣으면 다음 주로 넘어가요. " : ""}끌어서 위 주나 문서 칸에 놓아도 돼요.`}
        </p>
        <ul className="m-0 flex list-none flex-col gap-2 p-0">
          {rest.map((c) => {
            const id = c.cell.item_id;
            const sentence = c.cell.value.trim();
            return (
              <li
                key={id}
                data-candidate={id}
                draggable={!disabled}
                onDragStart={(event) => event.dataTransfer.setData("text/plain", SAFETY_DRAG + id)}
                className={`flex items-center gap-2.5 rounded-md border border-line bg-[#faf8f4] py-2.5 pl-2 pr-3 hover:bg-[#f5f1e9] ${disabled ? "" : "cursor-grab active:cursor-grabbing"}`}
              >
                {GRIP}
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="text-[15px] font-bold leading-snug">
                    {sentence || "(빈 후보)"}
                  </span>
                  <span className="text-[13px] text-ink-soft">
                    {[...new Set([KIND[c.kind], safetyTopic(c)])].join(" · ")}
                  </span>
                </span>
                <button
                  type="button"
                  data-act="place"
                  aria-label={`${label(weekId)}에 넣기: ${sentence || `${KIND[c.kind]} 빈 후보`}`}
                  className={SMALL}
                  disabled={disabled}
                  onClick={() => put(id)}
                >
                  + 넣기
                </button>
              </li>
            );
          })}
        </ul>
      </section>
    </section>
  );
}

/**
 * 이번 달에 넣은 안전교육 — 연간 「AI 후보」의 고른 놀이 목록처럼 한 상자에 주마다 한 줄. 넣은 주는 [빼기].
 * 지금 고른 주는 연보라 바탕. 줄에 후보 카드를 끌어 놓으면 그 주에 두고, 줄을 누르면(`onWeek`) 그 주로 바꾼다.
 */
function PlacedWeeks({
  plan,
  weekId,
  onPlace,
  onWeek,
  disabled,
}: {
  plan: SafetyPlan;
  weekId: string;
  onPlace: (weekId: string, candidateItemId: string | null) => void;
  onWeek?: (weekId: string) => void;
  disabled: boolean;
}) {
  const byId = new Map(plan.safety_candidates.map((c) => [c.cell.item_id, c]));
  return (
    <ol
      aria-label="넣은 안전교육"
      className="m-0 list-none divide-y divide-[#ece6dc] rounded-md border border-line bg-paper p-0"
    >
      {plan.weeks.map((week) => {
        const id = plan.safety_weeks.find((w) => w.week_id === week.week_id)?.candidate_item_id;
        const c = id ? byId.get(id) : undefined;
        const current = week.week_id === weekId;
        const drop = disabled ? {} : dropTo((id) => onPlace(week.week_id, id));
        const sentence = c ? c.cell.value.trim() || "(빈 후보)" : "";
        // 주 이름 · 문장 자리가 주 고르기 단추다. [빼기]는 그 옆에 따로 둔다(단추 안에 단추를 두지 않는다).
        const body = (
          <>
            <span
              className={`flex h-6 shrink-0 items-center justify-center rounded-full px-2 text-xs font-bold ${c ? "bg-[#efe8f7] text-primary-ink" : "border border-dashed border-[#d7d0c7] text-[#b1a89c]"}`}
            >
              {week.label}
            </span>
            {c ? (
              <span className="min-w-0 flex-1 text-sm leading-snug">
                <b className="block text-[12px] text-[#5e4b96]">[{safetyTopic(c)}]</b>
                <span className="line-clamp-2">{sentence}</span>
              </span>
            ) : (
              <span className="flex-1 text-[13px] text-[#b1a89c]">비어 있어요</span>
            )}
          </>
        );
        return (
          <li
            key={week.week_id}
            {...drop}
            // 넣은 줄도 끌어서 다른 주 줄이나 문서 칸에 놓을 수 있다(그 주에도 같은 후보를 둔다).
            draggable={!!c && !disabled}
            onDragStart={
              c
                ? (event) => event.dataTransfer.setData("text/plain", SAFETY_DRAG + c.cell.item_id)
                : undefined
            }
            className={`flex min-h-[48px] items-center gap-2.5 py-2 pl-2 pr-3 ${c && !disabled ? "cursor-grab active:cursor-grabbing" : ""} ${current ? "bg-[#f6f1fb]" : "hover:bg-[#fbf9f5]"} ${DROP}`}
          >
            {/* 빈 주는 손잡이 자리만 비워 둬 줄이 맞는다. */}
            <span className={c ? "contents" : "invisible contents"}>{GRIP}</span>
            {onWeek ? (
              <button
                type="button"
                data-act="week"
                aria-current={current ? "true" : undefined}
                aria-label={`${week.label} 안전교육 고르기${c ? `: ${sentence}` : " (빈 칸)"}`}
                onClick={() => onWeek(week.week_id)}
                className="flex min-h-[40px] min-w-0 flex-1 items-center gap-2.5 self-stretch text-left"
              >
                {body}
              </button>
            ) : (
              body
            )}
            {c && (
              <button
                type="button"
                data-act="unplace"
                aria-label={`${week.label}에서 빼기: ${sentence}`}
                disabled={disabled}
                onClick={() => onPlace(week.week_id, null)}
                className="min-h-[36px] shrink-0 rounded-md px-2.5 text-[13px] text-ink-soft hover:bg-[#f3efe8] hover:text-ink disabled:opacity-40"
              >
                빼기
              </button>
            )}
          </li>
        );
      })}
    </ol>
  );
}
