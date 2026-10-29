"use client";
import { useId } from "react";
import type { SelectedAge } from "@/lib/onboarding/types";

/**
 * 온보딩 반 정보의 연령 선택 UI.
 * 만 3·4·5세를 각각 독립적으로 고를 수 있다(복수 선택 가능).
 * 저장 값은 selectedAges 배열(예: [3,5])로 실제 선택을 그대로 보존한다.
 * 고른 버튼이 채워져 보이므로 「만 3~5세반」 같은 요약 글자는 따로 두지 않는다 (10/27 web뷰 수정사항).
 */
const AGES = [3, 4, 5] as const satisfies readonly SelectedAge[];

export default function AgeSelection({
  value,
  onChange,
}: {
  value: SelectedAge[];
  onChange: (value: SelectedAge[]) => void;
}) {
  const fieldId = useId();

  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="font-semibold text-[15px] xl:text-lg text-ink mb-2">연령</legend>

      <div className="flex flex-wrap gap-1.5">
        {AGES.map((age) => (
          <AgeChip
            key={age}
            id={`${fieldId}-age-${age}`}
            label={`만 ${age}세`}
            checked={value.includes(age)}
            onChange={(checked) =>
              onChange(AGES.filter((a) => (a === age ? checked : value.includes(a))))
            }
          />
        ))}
      </div>
    </fieldset>
  );
}

/** 체크박스를 둥근 버튼 모양으로 그린다. 고른 버튼은 보라 테두리 · 연보라 바탕 */
function AgeChip({
  id,
  label,
  checked,
  onChange,
}: {
  id: string;
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label
      htmlFor={id}
      className="inline-flex items-center min-h-[40px] px-4 rounded-full border-[1.5px] border-line bg-paper text-[14px] text-ink cursor-pointer select-none transition-colors hover:border-primary has-[:checked]:border-primary has-[:checked]:bg-primary-tint has-[:checked]:font-semibold has-[:checked]:text-primary-ink has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-primary"
    >
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="sr-only"
      />
      {label}
    </label>
  );
}
