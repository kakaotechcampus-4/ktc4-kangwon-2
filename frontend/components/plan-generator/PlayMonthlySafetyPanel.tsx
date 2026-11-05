"use client";

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

export const CARD = "flex items-center gap-3 rounded-md border px-4 py-2.5";
/** 넣은 후보 카드 — 안전교육 · 훈련 · 주간 후보가 같이 쓴다. */
export const PICKED = "border-[#7053a0] bg-[#f6f1fb]";
export const PUT =
  "min-h-[36px] shrink-0 rounded-lg border border-[#ddd6ca] bg-white px-3 text-sm font-bold text-[#5e4b96] disabled:opacity-40";

/**
 * Ⓜ3 AI 후보 — 고른 주의 안전교육 후보(디자인 넘김 09a). [넣기]는 그 주에 두고, 둔 후보는 [빼기].
 * 다른 주에 둔 후보는 흐리게 「n주에 넣음」 — 같은 후보를 여러 주에 둘 수도 있다.
 */
export default function PlayMonthlySafetyPanel({
  plan,
  weekId,
  onPlace,
  disabled,
}: {
  plan: SafetyPlan;
  weekId: string;
  onPlace: (weekId: string, candidateItemId: string | null) => void;
  disabled: boolean;
}) {
  const label = (id: string) => plan.weeks.find((w) => w.week_id === id)?.label ?? id;
  const here = plan.safety_weeks.find((w) => w.week_id === weekId)?.candidate_item_id ?? null;
  return (
    <section aria-label="안전교육" className="flex flex-col gap-2">
      <PlacedWeeks plan={plan} weekId={weekId} onPlace={onPlace} disabled={disabled} />
      <h2 className="m-0 flex items-center justify-between gap-2 text-[18px] font-bold leading-tight">
        {label(weekId)} 안전교육 후보
        {/* 우리 반 화면의 복숭아색 쪽지 안내처럼. */}
        {!here && (
          <span className="shrink-0 rounded-full bg-peach-tint px-2.5 py-0.5 font-body text-[12px] font-semibold text-peach-ink">
            아직 비어 있어요
          </span>
        )}
      </h2>
      <ul className="m-0 flex list-none flex-col gap-2 p-0">
        {/* 그 주에 넣은 후보는 맨 위로 — 연간 놀이 후보 고르기와 같다. */}
        {[...plan.safety_candidates]
          .sort((a, b) => Number(b.cell.item_id === here) - Number(a.cell.item_id === here))
          .map((c) => {
            const id = c.cell.item_id;
            const mine = here === id;
            const elsewhere = plan.safety_weeks
              .filter((w) => w.week_id !== weekId && w.candidate_item_id === id)
              .map((w) => label(w.week_id));
            return (
              <li
                key={id}
                data-candidate={id}
                className={`${CARD} ${
                  mine
                    ? PICKED
                    : elsewhere.length
                      ? "border-dashed border-[#ddd6ca] text-ink-soft"
                      : "border-[#e8e2d8]"
                }`}
              >
                <div className="min-w-0 flex-1">
                  <div className="text-[11px] font-bold text-[#5c5243]">
                    {KIND[c.kind]}
                    {elsewhere.length > 0 && ` · ${elsewhere.join(", ")}에 넣음`}
                  </div>
                  <div className="text-[14px]">{c.cell.value.trim() || "(빈 후보)"}</div>
                </div>
                <button
                  type="button"
                  data-act={mine ? "clear" : "place"}
                  aria-label={`${label(weekId)}에 ${mine ? "빼기" : "넣기"}: ${c.cell.value.trim() || `${KIND[c.kind]} 빈 후보`}`}
                  className={PUT}
                  disabled={disabled}
                  onClick={() => onPlace(weekId, mine ? null : id)}
                >
                  {mine ? "빼기" : "넣기"}
                </button>
              </li>
            );
          })}
      </ul>
    </section>
  );
}

/**
 * 이번 달에 넣은 안전교육 — 놀이 고르기의 「고른 놀이」처럼 주마다 한 칸. 빈 주는 점선, 넣은 주는 ✕ 로 뺀다.
 * 지금 고른 주는 테두리로 표시한다.
 */
function PlacedWeeks({
  plan,
  weekId,
  onPlace,
  disabled,
}: {
  plan: SafetyPlan;
  weekId: string;
  onPlace: (weekId: string, candidateItemId: string | null) => void;
  disabled: boolean;
}) {
  const byId = new Map(plan.safety_candidates.map((c) => [c.cell.item_id, c]));
  return (
    <ol aria-label="넣은 안전교육" className="m-0 mb-3 flex list-none flex-col gap-1.5 p-0">
      {plan.weeks.map((week) => {
        const id = plan.safety_weeks.find((w) => w.week_id === week.week_id)?.candidate_item_id;
        const c = id ? byId.get(id) : undefined;
        const ring = week.week_id === weekId ? "outline outline-2 outline-[#7053a0]" : "";
        const badge =
          "flex h-6 min-w-6 shrink-0 items-center justify-center rounded-md px-1 text-xs font-bold";
        if (!c)
          return (
            <li
              key={week.week_id}
              className={`flex min-h-[48px] items-center gap-3 rounded-xl border-2 border-dashed border-[#ddd6ca] px-3 text-sm text-[#b1a89c] ${ring}`}
            >
              <span className={`${badge} border border-dashed border-[#d7d0c7]`}>{week.label}</span>
              <span className="sr-only">빈 칸</span>
            </li>
          );
        const sentence = c.cell.value.trim() || "(빈 후보)";
        return (
          <li
            key={week.week_id}
            className={`flex min-h-[48px] items-center gap-3 rounded-xl border-2 border-[#e6dcf0] bg-[#fbf8f2] px-3 ${ring}`}
          >
            <span className={`${badge} bg-[#eee4f4] text-[#5e4b96]`}>{week.label}</span>
            <span className="min-w-0 flex-1 text-sm leading-snug">
              <b className="block text-[12px] text-[#5e4b96]">[{safetyTopic(c)}]</b>
              <span className="line-clamp-2">{sentence}</span>
            </span>
            <button
              type="button"
              data-act="unplace"
              aria-label={`${week.label}에서 빼기: ${sentence}`}
              disabled={disabled}
              onClick={() => onPlace(week.week_id, null)}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-ink-soft hover:bg-[#efeae2] disabled:opacity-40"
            >
              ✕
            </button>
          </li>
        );
      })}
    </ol>
  );
}
