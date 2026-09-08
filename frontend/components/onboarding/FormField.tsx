import type { InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";

/**
 * 라벨 + 입력 + 도움말을 한 덩어리로 묶는 필드 래퍼.
 * 계획안 생성 페이지의 섹션 라벨(font-display 15px)과 같은 규격을 쓴다.
 */
export default function FormField({
  id,
  label,
  optional = false,
  hint,
  children,
}: {
  id?: string;
  label: ReactNode;
  optional?: boolean;
  hint?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="font-display text-[15px] text-ink">
        {label}
        {optional && (
          <span className="ml-1.5 align-middle font-mono text-[10.5px] tracking-wider text-ink-soft border border-line rounded-full px-1.5 py-px">
            선택
          </span>
        )}
      </label>
      {children}
      {hint && <p className="text-[12.5px] text-ink-soft">{hint}</p>}
    </div>
  );
}

/* 공통 입력 스타일 — Select / TextInput / TextArea가 공유 */
export const inputBase =
  "w-full rounded-2xl border-[1.5px] border-line bg-paper text-ink px-4 py-3 text-base lg:text-[15px] min-h-[48px] " +
  "placeholder:text-ink-soft/80 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sage-ink";

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  const { className = "", ...rest } = props;
  return <input type="text" autoComplete="off" {...rest} className={`${inputBase} ${className}`} />;
}

export function TextArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const { className = "", ...rest } = props;
  return <textarea {...rest} className={`${inputBase} resize-none leading-relaxed ${className}`} />;
}
