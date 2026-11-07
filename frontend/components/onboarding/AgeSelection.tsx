"use client";
import { useId } from "react";
import { FieldHint, fieldLabelClass } from "./FlowParts";
import type { SelectedAge } from "@/lib/onboarding/types";

/**
 * 온보딩 반 정보의 연령 선택 — 시안 A 의 3칸 큰 타일.
 * 만 3·4·5세를 각각 독립적으로 고를 수 있다(복수 선택 가능).
 * 저장 값은 selectedAges 배열(예: [3,5])로 실제 선택을 그대로 보존한다.
 * `active` 는 지금 묻는 질문일 때 — 타일이 크다. 이미 답한 칸으로 쌓이면 작아진다.
 */
const AGES = [3, 4, 5] as const satisfies readonly SelectedAge[];

export default function AgeSelection({
  value,
  onChange,
  active = false,
  hint,
}: {
  value: SelectedAge[];
  onChange: (value: SelectedAge[]) => void;
  active?: boolean;
  /** 타일 밑 안내 한 줄(FieldHint). */
  hint?: string;
}) {
  const fieldId = useId();

  return (
    <fieldset className="mb-7 flex flex-col gap-2.5">
      {/* 칸 이름은 다른 칸(FieldLabel)과 같은 모양 */}
      <legend className={`mb-2.5 ${fieldLabelClass}`}>연령</legend>
      <div className="grid grid-cols-3 gap-2">
        {AGES.map((age) => (
          <AgeTile
            key={age}
            id={`${fieldId}-age-${age}`}
            label={`만 ${age}세`}
            active={active}
            checked={value.includes(age)}
            onChange={(checked) =>
              onChange(AGES.filter((a) => (a === age ? checked : value.includes(a))))
            }
          />
        ))}
      </div>
      {hint && <FieldHint>{hint}</FieldHint>}
    </fieldset>
  );
}

/** 체크박스를 타일 모양으로 그린다. 고른 타일은 보라 테두리 · 연보라 바탕 */
function AgeTile({
  id,
  label,
  active,
  checked,
  onChange,
}: {
  id: string;
  label: string;
  active: boolean;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label
      htmlFor={id}
      className={`relative flex w-full cursor-pointer select-none items-center justify-center squircle [--r:14px] border-[1.5px] border-line bg-paper font-medium text-ink transition-colors hover:border-primary has-[:checked]:border-primary has-[:checked]:bg-primary-tint has-[:checked]:font-bold has-[:checked]:text-primary-ink has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-primary ${active ? "h-[60px] text-[17px]" : "h-11 text-[15px]"}`}
    >
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        // 화면에서는 숨기되 타일 전체를 덮어 둔다. sr-only 로 숨기면 라벨이 클릭을 가로채
        // 체크박스를 직접 누르는 e2e(getByLabel(...).check())가 멈춘다
        className="absolute inset-0 m-0 h-full w-full cursor-pointer appearance-none squircle [--r:14px] opacity-0"
      />
      {label}
    </label>
  );
}
