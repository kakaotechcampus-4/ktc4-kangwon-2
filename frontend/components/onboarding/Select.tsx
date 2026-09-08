import type { SelectHTMLAttributes } from "react";
import { inputBase } from "./FormField";

/* 계획안 생성 페이지와 같은 커스텀 chevron (색: --pg-ink-soft) */
const CHEVRON_BG =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24'%3E%3Cpath d='M5 9l7 7 7-7' fill='none' stroke='%236B7280' stroke-width='2.3' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E\")";

export interface SelectOption<V extends string = string> {
  value: V;
  label: string;
}

export default function Select<V extends string>({
  options,
  placeholder,
  className = "",
  ...rest
}: Omit<SelectHTMLAttributes<HTMLSelectElement>, "children"> & {
  options: SelectOption<V>[];
  placeholder?: string;
}) {
  return (
    <select
      {...rest}
      className={`${inputBase} appearance-none pr-10 ${className}`}
      style={{ backgroundImage: CHEVRON_BG, backgroundRepeat: "no-repeat", backgroundPosition: "right 14px center", backgroundSize: "15px" }}
    >
      {placeholder !== undefined && <option value="">{placeholder}</option>}
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}
