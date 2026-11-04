"use client";

const KIND = { STATUTORY: "법정", SUPPLEMENTAL: "추가" } as const;

/** 패널이 읽는 칸만 — 놀이 월간과 v1 월간이 같이 쓴다. */
type SafetyPlan = {
  weeks: { week_id: string; label: string }[];
  safety_candidates: { kind: keyof typeof KIND; cell: { item_id: string; value: string } }[];
  safety_weeks: { week_id: string; candidate_item_id: string | null }[];
};

export const CARD = "flex items-center gap-3 rounded-xl border px-4 py-2.5";
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
      <h2 className="m-0 flex items-baseline justify-between text-[15px] font-bold">
        {label(weekId)} 안전교육 후보
        {!here && <span className="text-[13px] font-normal text-[#c2473d]">아직 비어 있어요</span>}
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
                      ? "border-dashed border-[#ddd6ca] text-[#8a8178]"
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
