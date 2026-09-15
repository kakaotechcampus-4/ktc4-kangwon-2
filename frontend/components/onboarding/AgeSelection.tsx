"use client";
import { useId } from "react";
import { ageSelectionLabel, type SelectedAge } from "@/lib/onboarding/types";

/**
 * 온보딩 반 정보의 연령 선택 UI.
 * 만 3·4·5세를 각각 독립적으로 고를 수 있다(복수 선택 가능).
 * 저장 값은 selectedAges 배열(예: [3,5])로 실제 선택을 그대로 보존한다.
 */
const AGES = [3, 4, 5] as const satisfies readonly SelectedAge[];

export default function AgeSelection({ value, onChange }: { value: SelectedAge[]; onChange: (value: SelectedAge[]) => void }) {
  const fieldId = useId();

  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="font-display text-[15px] xl:text-lg text-ink mb-2">연령</legend>

      {/* 한 줄에 3개 배치 */}
      <div className="grid grid-cols-3 gap-x-4 gap-y-1">
        {AGES.map((age) => (
          <AgeCheckbox
            key={age}
            id={`${fieldId}-age-${age}`}
            label={`만 ${age}세`}
            checked={value.includes(age)}
            onChange={(checked) => onChange(AGES.filter((a) => (a === age ? checked : value.includes(a))))}
          />
        ))}
      </div>

      <p className="text-[12.5px] xl:text-sm text-ink-soft" aria-live="polite">{ageSelectionLabel(value)}</p>
    </fieldset>
  );
}

function AgeCheckbox({ id, label, checked, onChange }: { id: string; label: string; checked: boolean; onChange: (checked: boolean) => void }) {
  return (
    <label
      htmlFor={id}
      className="flex items-center gap-2.5 min-h-[40px] text-base lg:text-[15px] xl:text-[17px] text-ink cursor-pointer select-none"
    >
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="w-[18px] h-[18px] shrink-0 rounded-[5px] accent-[var(--pg-sage-ink)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sage-ink"
      />
      {label}
    </label>
  );
}
