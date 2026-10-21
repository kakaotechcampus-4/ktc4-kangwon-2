import styles from "./GenerationFlow.module.css";

/** 배치 유무와 미입력을 구분한다. 일정 추천이나 법정 충족 판정은 하지 않는다. */
export default function AnnualSafetyField({
  month,
  value,
  categories,
  editing,
  disabled,
  onChange,
}: {
  month: string;
  value: string[] | null;
  categories: { category_id: string; label: string }[];
  editing: boolean;
  disabled: boolean;
  onChange: (value: string[] | null) => void;
}) {
  const summary =
    value === null
      ? "배치 계획 미입력"
      : value.length === 0
        ? "이 달 배치 없음"
        : value
            .map((id) => categories.find((c) => c.category_id === id)?.label || "구분 확인 필요")
            .join(" · ");
  if (!editing) return <p className={styles.footnote}>안전교육 · {summary}</p>;
  return (
    <details className={styles.annualSafety}>
      <summary aria-label={`${month} 안전교육 입력`}>안전교육 입력 · {summary}</summary>
      <fieldset disabled={disabled || !categories.length} aria-label={`${month} 안전교육`}>
        <legend>교사가 정한 {month} 배치</legend>
        <label>
          <input
            type="checkbox"
            checked={value !== null}
            onChange={(e) => onChange(e.target.checked ? [] : null)}
          />
          이 달의 배치 계획을 입력했어요
        </label>
        <div>
          {categories.map((category) => (
            <label key={category.category_id}>
              <input
                type="checkbox"
                checked={value?.includes(category.category_id) ?? false}
                disabled={value === null}
                onChange={(e) =>
                  onChange(
                    e.target.checked
                      ? [...(value ?? []), category.category_id]
                      : (value ?? []).filter((id) => id !== category.category_id),
                  )
                }
              />
              {category.label}
            </label>
          ))}
        </div>
      </fieldset>
      <p className={styles.footnote}>
        {categories.length
          ? "구분을 선택하지 않고 입력 완료로 두면 이 달에는 배치하지 않은 것으로 저장해요. 교육시간은 검사하지 않아요."
          : "안전교육 구분을 불러오지 못했어요. 새로고침한 뒤 입력해주세요."}
      </p>
    </details>
  );
}
