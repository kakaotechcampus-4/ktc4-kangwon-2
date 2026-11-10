"use client";

import type { DayPlan } from "@/lib/workspace/journal-day";
import type { DayObservation } from "./use-day-extras";
import css from "./RoutineDay.module.css";

/**
 * 일과 한 줄 아래에 붙는 것 — **전부 교사가 눌러야 들어간다** (ADR-086 · ADR-024 덧붙임).
 *
 * - 회색 후보: 요일 칸이 있는 「활동」 · 「특별활동」 줄에만. 누르면 활동 이름이 실제로 한 것에 들어간다.
 * - 「계획 보기」: 그 밖의 줄에서 그 주 계획을 펼쳐 골라 넣는다.
 * - 그 시간 관찰: 이름을 「○○」로 뺀 글. 「넣기」는 붙여 넣기다 — 교사가 고친다. 못 가린 낱말은 노랗게.
 * - 「바깥놀이(대체)」: 비 · 눈 · 미세먼지 날 바깥놀이 줄 이름을 바꾸는 칩.
 */
export default function RoutineRowExtras({
  candidates,
  plan,
  observed,
  outdoor,
  disabled,
  onPick,
  onInsert,
  onRename,
}: {
  candidates: string[];
  /** 계획안이 있을 때 「계획 보기」에 펼 것. 후보가 뜨는 줄과 계획안 없는 반은 null. */
  plan: DayPlan["all"] | null;
  observed: DayObservation[];
  outdoor: boolean;
  disabled: boolean;
  onPick: (activity: string) => void;
  onInsert: (text: string) => void;
  onRename: (name: string) => void;
}) {
  if (!candidates.length && !plan?.length && !observed.length && !outdoor) return null;
  return (
    <div className={css.extras}>
      {(candidates.length > 0 || outdoor) && (
        <div className={css.chips}>
          {candidates.length > 0 && <span className={css.candidateLead}>계획에서</span>}
          {candidates.map((name) => (
            <button
              key={name}
              type="button"
              className={css.candidate}
              disabled={disabled}
              aria-label={`${name} 했어요`}
              onClick={() => onPick(name)}
            >
              {name}
            </button>
          ))}
          {outdoor && (
            <button
              type="button"
              className={css.candidate}
              disabled={disabled}
              onClick={() => onRename("바깥놀이(대체)")}
            >
              바깥놀이(대체)
            </button>
          )}
        </div>
      )}
      {plan && plan.length > 0 && (
        <details className={css.planView}>
          <summary>계획 보기</summary>
          {plan.map((group) => (
            <div key={group.label} className={css.planGroup}>
              <h4>{group.label}</h4>
              <div className={css.chips}>
                {group.values.map((value) => (
                  <button
                    key={value}
                    type="button"
                    className={css.candidate}
                    disabled={disabled}
                    aria-label={`${value} 넣기`}
                    onClick={() => onPick(value)}
                  >
                    {value}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </details>
      )}
      {observed.map((line) => (
        <div key={line.id} className={css.observed}>
          <p>
            <Marked text={line.text} words={line.suspects} />
          </p>
          <button
            type="button"
            className={css.paperButton}
            disabled={disabled}
            onClick={() => onInsert(line.text)}
          >
            넣기
          </button>
        </div>
      ))}
    </div>
  );
}

/** 못 가린 낱말에 노란 형광펜. 글자는 그대로 둔다. */
function Marked({ text, words }: { text: string; words: string[] }) {
  if (!words.length) return <>{text}</>;
  const pattern = new RegExp(
    `(${words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`,
  );
  return (
    <>
      {text.split(pattern).map((part, index) =>
        words.includes(part) ? (
          <mark key={index} title="이름일 수 있어요. 넣은 뒤 고쳐 주세요.">
            {part}
          </mark>
        ) : (
          part
        ),
      )}
    </>
  );
}
