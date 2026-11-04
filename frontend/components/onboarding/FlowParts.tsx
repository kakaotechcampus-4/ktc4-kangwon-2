import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { useClientState } from "@/lib/hooks/use-client-state";

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

const REDUCED_MOTION = "(prefers-reduced-motion: reduce)";
const reducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia(REDUCED_MOTION).matches;

/**
 * 포스티가 말하듯 한 글자씩 늘어나는 글자 수. 글이 바뀌면 처음부터 다시 치도록 부르는 쪽이 `key` 를 글로 준다.
 * 「동작 줄이기」를 켠 교사에게는 처음부터 다 보인다.
 */
export function useTypewriter(length: number) {
  const [reduced] = useClientState(reducedMotion, false);
  const [count, setCount] = useState(0);
  useEffect(() => {
    if (reduced || count >= length) return;
    const id = setTimeout(() => setCount(count + 1), 35);
    return () => clearTimeout(id);
  }, [reduced, count, length]);
  return reduced ? length : Math.min(count, length);
}

/**
 * 앞에서 `shown` 글자까지만 보인다. 아직 안 나온 글자는 투명하게 자리만 잡아 둔다 —
 * 말풍선 크기와 가운데 맞춤이 글자마다 흔들리지 않는다. 화면 읽기 프로그램용 글은 부르는 쪽이 따로 둔다.
 */
export function Typed({ text, shown }: { text: string; shown: number }) {
  const n = Math.max(0, Math.min(shown, text.length));
  return (
    <>
      {text.slice(0, n)}
      <span className="opacity-0">{text.slice(n)}</span>
    </>
  );
}

/**
 * 새로 묻는 입력칸이 포스티 입에서 나와 제자리에 놓인다. 질문이 바뀔 때마다 새로 그려지도록 `key` 를 질문으로 준다.
 * 입 자리는 오른쪽 칸 포스티의 `[data-posty-mouth]`(OnboardingLayout). 그 칸이 없는 폭(767px 이하)에서는
 * 아래에서 살짝 떠오르기만 한다. 「동작 줄이기」면 움직이지 않는다.
 */
export function FlyIn({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || reducedMotion()) return;
    const mouth = document.querySelector("[data-posty-mouth]");
    if (!mouth || mouth.getClientRects().length === 0) {
      el.animate(
        [
          { transform: "translateY(14px)", opacity: 0 },
          { transform: "none", opacity: 1 },
        ],
        { duration: 320, easing: "ease-out" },
      );
      return;
    }
    const m = mouth.getBoundingClientRect();
    const box = el.getBoundingClientRect();
    const dx = m.left - (box.left + box.width / 2);
    const dy = m.top - (box.top + box.height / 2);
    el.animate(
      [
        { transform: `translate(${dx}px, ${dy}px) scale(0.08)`, opacity: 0 },
        {
          transform: `translate(${dx * 0.85}px, ${dy * 0.85}px) scale(0.25)`,
          opacity: 1,
          offset: 0.15,
        },
        { transform: "none", opacity: 1 },
      ],
      { duration: 620, easing: "cubic-bezier(0.34, 1.25, 0.64, 1)" },
    );
  }, []);
  // 날아오는 동안 오른쪽 칸 말풍선 위로 지나가도록 위에 둔다.
  return (
    <div ref={ref} className="relative z-10">
      {children}
    </div>
  );
}
