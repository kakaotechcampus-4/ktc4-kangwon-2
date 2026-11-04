import {
  useEffect,
  useRef,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type KeyboardEvent,
  type ReactNode,
} from "react";

/*
 * 시작 설정(온보딩) 화면 조각. 생김새는 승인한 시안 A(한 화면에 질문 하나)를 그대로 따른다 —
 * 큰 손글씨 제목, 밑줄만 있는 입력칸, 지금 질문의 글자는 크고 답한 칸은 작게, 아래 넓은 주 버튼.
 */

/**
 * 한 화면의 질문. 제목은 손글씨체(display)로, 입력한 글자는 본문체로 둔다.
 *
 * `focus` — 입력칸이 없는 질문(연령 · 동의 · 지역)은 「다음」을 누른 뒤 포커스가 아래 버튼에 남아
 * 키보드 · 화면 읽기 프로그램 사용자가 새 질문을 모른 채 지나간다. 제목으로 옮기면 새 질문을 읽어 주고,
 * Tab 한 번에 고를 칸으로 간다. 입력칸 질문은 그 칸이 자동 포커스를 받으므로 켜지 않는다.
 */
export function Question({
  title,
  hint,
  focus = false,
}: {
  title: string;
  hint?: ReactNode;
  focus?: boolean;
}) {
  const ref = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (focus) ref.current?.focus();
  }, [focus, title]);
  return (
    <div className="mb-8">
      <h1
        ref={ref}
        tabIndex={-1}
        className="whitespace-pre-line font-display text-[31px] font-bold leading-[1.4] text-ink outline-none sm:text-[36px]"
        style={{ wordBreak: "keep-all" }}
      >
        {title}
      </h1>
      {hint && <p className="mt-2.5 text-[15px] leading-[1.6] text-ink-soft">{hint}</p>}
    </div>
  );
}

/**
 * Enter 로 다음으로 넘어가는 키 처리. 한글 조합 중 Enter 는 글자를 확정하는 키라 무시한다
 * (`isComposing` · keyCode 229).
 */
export function onEnter(e: KeyboardEvent, action: () => void) {
  if (e.key !== "Enter" || e.nativeEvent.isComposing || e.nativeEvent.keyCode === 229) return;
  e.preventDefault();
  action();
}

export function ErrorLine({ children }: { children: ReactNode }) {
  if (!children) return null;
  return (
    <p role="alert" className="text-[14px] text-alert-ink">
      {children}
    </p>
  );
}

export function LoadingLine() {
  return (
    <p role="status" className="p-6 text-ink-soft">
      설정을 불러오고 있어요.
    </p>
  );
}

/** 밑줄 칸의 글자 크기 · 밑줄 색. 지금 묻는 칸은 크고 보라, 이미 답한 칸은 작고 회색(누르면 보라). */
const lineClass = (active: boolean) =>
  "w-full border-0 border-b-2 bg-transparent pb-2.5 pt-1.5 font-semibold outline-none transition-colors " +
  (active
    ? "border-primary text-[22px] sm:text-[24px]"
    : "border-line text-[17px] focus:border-primary focus-visible:border-primary");

/** 칸 이름. 작은 회색 글자다. */
export function FieldLabel({ htmlFor, children }: { htmlFor?: string; children: ReactNode }) {
  return (
    <label htmlFor={htmlFor} className="text-[13px] font-medium text-ink-soft">
      {children}
    </label>
  );
}

/** 밑줄만 있는 입력칸 한 줄 — 칸 이름 · 입력 · 오류. */
export function LineField({
  id,
  label,
  active,
  error,
  ...input
}: {
  id: string;
  label: string;
  active: boolean;
  error?: string;
} & Omit<InputHTMLAttributes<HTMLInputElement>, "id">) {
  return (
    <div className="mb-7 flex flex-col gap-1.5">
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <input
        id={id}
        type="text"
        autoComplete="off"
        aria-invalid={error ? true : undefined}
        {...input}
        className={`${lineClass(active)} text-ink placeholder:text-ink-hint`}
      />
      <ErrorLine>{error}</ErrorLine>
    </div>
  );
}

/** 지역처럼 눌러서 고르는 칸. 입력칸과 같은 밑줄 모양이다. */
export function PickButton({
  id,
  value,
  placeholder,
  active,
  onClick,
}: {
  id?: string;
  value: string;
  placeholder: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      id={id}
      type="button"
      onClick={onClick}
      className={`${lineClass(active)} flex cursor-pointer items-center justify-between gap-3 text-left ${value ? "text-ink" : "text-ink-soft"}`}
    >
      <span>{value || placeholder}</span>
      <svg
        width="20"
        height="20"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        className="shrink-0 text-ink-soft"
      >
        <path d="M6 9l6 6 6-6" />
      </svg>
    </button>
  );
}

/** 아래 주 버튼. 휴대폰은 폭을 다 쓰고, 데스크톱은 오른쪽에 붙는다. 링크(완료 화면)도 같은 모양을 쓴다. */
export const ctaClass =
  "inline-flex h-14 w-full items-center justify-center rounded-[14px] bg-primary px-7 text-[17px] font-bold text-white transition-colors " +
  "hover:bg-primary-hover disabled:cursor-not-allowed disabled:bg-primary-tint disabled:text-ink-hint " +
  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary sm:w-auto sm:min-w-[200px]";

export function CtaButton({ className = "", ...rest }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button type="button" {...rest} className={`${ctaClass} ${className}`} />;
}

/** 주 버튼 옆 밑줄 글자 버튼(「나중에 넣을게요」). */
export function TextAction({ className = "", ...rest }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      {...rest}
      className={`h-12 px-4 text-[15px] font-medium text-ink-soft underline underline-offset-4 hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary ${className}`}
    />
  );
}

/** 오른쪽 화살표(줄을 눌러 들어가는 곳). */
export function Chevron({ size = 18 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="shrink-0 text-ink-soft"
    >
      <path d="M9 6l6 6-6 6" />
    </svg>
  );
}
