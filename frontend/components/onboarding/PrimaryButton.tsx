import type { ButtonHTMLAttributes } from "react";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement>;

const base =
  "inline-flex items-center justify-center gap-1.5 rounded-2xl px-5 py-3 min-h-[48px] text-[15px] " +
  "transition-colors active:translate-y-px disabled:cursor-not-allowed " +
  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sage-ink";

/** Main #AFCDB5 배경 · hover Dark #7EAD8B — 계획안 생성 버튼과 동일 규격 */
export default function PrimaryButton({ className = "", ...rest }: ButtonProps) {
  return (
    <button
      type="button"
      {...rest}
      className={`${base} font-display text-[16px] bg-sage text-ink hover:bg-sage-ink disabled:bg-line disabled:text-ink-soft ${className}`}
    />
  );
}

/** 흰 배경 + 얇은 테두리 (이전 / 추가 등 보조 동작) */
export function GhostButton({ className = "", ...rest }: ButtonProps) {
  return (
    <button
      type="button"
      {...rest}
      className={`${base} bg-paper text-ink-soft border-[1.5px] border-line hover:border-sage-ink hover:text-ink ${className}`}
    />
  );
}

/** 배경 없는 텍스트 버튼 (되돌리기 등) */
export function TextButton({ className = "", ...rest }: ButtonProps) {
  return (
    <button
      type="button"
      {...rest}
      className={`inline-flex items-center rounded-full px-2.5 py-1.5 min-h-[36px] text-[12.5px] text-ink-soft hover:text-sage-ink hover:bg-sage-tint transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-sage-ink ${className}`}
    />
  );
}
