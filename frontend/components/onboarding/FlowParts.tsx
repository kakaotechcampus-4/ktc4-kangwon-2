import {
  useEffect,
  useId,
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
 * 큰 손글씨 제목, 밑줄만 있는 입력칸, 칸 밑 안내(FieldHint), 답한 칸은 요약 줄(AnsweredList), 아래 넓은 주 버튼.
 */

/**
 * 한 화면의 질문. 제목은 손글씨체(display)로, 입력한 글자는 본문체로 둔다.
 * `hint` 는 화면 전체에 대한 안내만 받는다. 칸 하나를 설명하는 안내는 그 칸 밑(FieldHint)에 둔다.
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
        className="whitespace-pre-line font-display text-[32px] font-bold leading-[1.35] text-ink outline-none sm:text-[40px]"
        style={{ wordBreak: "keep-all" }}
      >
        {title}
      </h1>
      {hint && <p className="mt-3 text-[16px] leading-[1.6] text-ink-soft">{hint}</p>}
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

/** 밑줄 칸의 글자 크기. 지금 묻는 칸은 크고, 이미 답한 칸은 작다. 밑줄은 ChalkLine 이 긋는다. */
const lineClass = (active: boolean) =>
  "w-full border-0 bg-transparent pb-2.5 pt-1.5 outline-none " +
  (active ? "text-[24px] font-bold sm:text-[28px]" : "text-[17px] font-medium");

/** 밑줄 색. 지금 묻는 칸은 노란 분필, 이미 답한 칸은 흐린 분필(누르면 노란 분필). 감싸는 쪽에 group 이 있어야 한다. */
const lineColor = (active: boolean) =>
  active ? "text-primary" : "text-line group-focus-within:text-primary";

/**
 * 칠판에 분필로 그은 밑줄. 감싸는 칸(relative)의 맨 아래에 깔린다. 색은 currentColor.
 * 칸 너비만큼 늘어나도 굵기는 그대로이고(non-scaling-stroke), 분필 결은 OnboardingLayout 의 #chalk 필터가 낸다.
 * 반듯한 직선은 높이가 0 이라 필터를 받지 못한다 — 그래서 아주 살짝 굽혀 긋는다.
 */
export function ChalkLine({ className = "" }: { className?: string }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 100 4"
      preserveAspectRatio="none"
      className={`pointer-events-none absolute inset-x-0 -bottom-[2px] h-[5px] w-full overflow-visible transition-colors ${className}`}
    >
      <path
        d="M0 2.4 Q30 1.2 55 2 T100 1.6"
        fill="none"
        stroke="currentColor"
        strokeWidth={2.6}
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
        filter="url(#chalk)"
      />
    </svg>
  );
}

/** 칸 이름. 손글씨는 질문 제목에만 쓰고, 칸 이름은 작은 기본 글씨로 둔다 — 입력한 글자와 갈린다. */
export const fieldLabelClass =
  "text-[14px] font-bold leading-[1.4] tracking-[0.02em] text-ink-soft";

export function FieldLabel({ htmlFor, children }: { htmlFor?: string; children: ReactNode }) {
  return (
    <label htmlFor={htmlFor} className={fieldLabelClass}>
      {children}
    </label>
  );
}

/** 칸 바로 밑 안내 한 줄. 그 칸이 무엇을 받는지 설명한다(질문 제목 아래 안내와 따로 둔다). */
export function FieldHint({ id, children }: { id?: string; children: ReactNode }) {
  return (
    <p id={id} className="mt-1.5 flex items-start gap-2 text-[14px] leading-[1.55] text-ink-soft">
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        className="mt-0.5 flex-none"
      >
        <circle cx="12" cy="12" r="9" />
        <path d="M12 11v5" />
        <path d="M12 8h.01" />
      </svg>
      <span>{children}</span>
    </p>
  );
}

/** 밑줄만 있는 입력칸 한 줄 — 칸 이름 · 입력 · 오류 · 안내. */
export function LineField({
  id,
  label,
  active,
  error,
  hint,
  ...input
}: {
  id: string;
  label: string;
  active: boolean;
  error?: string;
  hint?: string;
} & Omit<InputHTMLAttributes<HTMLInputElement>, "id">) {
  const hintId = `${id}-hint`;
  return (
    <div className="mb-7 flex flex-col gap-2">
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <div className="group relative">
        <input
          id={id}
          type="text"
          autoComplete="off"
          aria-invalid={error ? true : undefined}
          aria-describedby={hint ? hintId : undefined}
          {...input}
          className={`${lineClass(active)} text-ink placeholder:text-ink-hint`}
        />
        <ChalkLine className={lineColor(active)} />
      </div>
      <ErrorLine>{error}</ErrorLine>
      {hint && <FieldHint id={hintId}>{hint}</FieldHint>}
    </div>
  );
}

/** 앞에서 답한 칸 한 줄. `onEdit` 이 없으면 고칠 수 없는 줄이다. */
export type Answered = { label: string; value: string; onEdit?: () => void };

/**
 * 앞에서 답한 칸 — 지금 질문 아래에 칸째 쌓지 않고 요약 줄로 접는다. 최근에 답한 것이 위.
 * 칸 이름은 `<label>` 이 아니다 — 지금 칸의 이름과 겹쳐 「담임 이름」 같은 이름표가 둘이 되지 않게.
 */
export function AnsweredList({ items }: { items: Answered[] }) {
  const headingId = useId();
  if (!items.length) return null;
  return (
    <section aria-labelledby={headingId} className="mb-7">
      <h2
        id={headingId}
        className="mb-2 flex items-center gap-1.5 text-[13px] font-bold text-ink-soft"
      >
        <svg
          width="15"
          height="15"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M5 12l5 5L20 7" />
        </svg>
        앞에서 답했어요
      </h2>
      <dl className="divide-y divide-shell squircle [--r:14px] border border-shell bg-ivory">
        {items.map((item) => (
          <AnsweredRow key={item.label} item={item} />
        ))}
      </dl>
    </section>
  );
}

function AnsweredRow({ item }: { item: Answered }) {
  return (
    <div className="grid min-h-12 grid-cols-[84px_minmax(0,1fr)] items-center gap-3 pl-4 pr-1.5">
      <dt className="text-[13px] font-medium text-ink-soft">{item.label}</dt>
      <dd className="flex min-w-0 items-center gap-2 text-[15.5px] font-semibold text-ink">
        <span className="min-w-0 flex-1 [overflow-wrap:anywhere]">{item.value || "-"}</span>
        {item.onEdit && (
          <button
            type="button"
            onClick={item.onEdit}
            aria-label={`${item.label} 고치기`}
            title={`${item.label} 고치기`}
            className="inline-flex h-11 w-11 flex-none items-center justify-center squircle [--r:12px] text-ink-soft hover:bg-primary-tint hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
          >
            <EditIcon />
          </button>
        )}
      </dd>
    </div>
  );
}

/** 고치기 — 귀퉁이가 열린 네모 위에 연필. 마지막 확인의 반 줄도 같이 쓴다. */
export function EditIcon() {
  return (
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
    >
      <path d="M11 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5" />
      <path d="M17.5 3.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4z" />
    </svg>
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
      className={`${lineClass(active)} group relative flex cursor-pointer items-center justify-between gap-3 text-left ${value ? "text-ink" : "text-ink-soft"}`}
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
      <ChalkLine className={lineColor(active)} />
    </button>
  );
}

/** 아래 주 버튼. 휴대폰은 폭을 다 쓰고, 데스크톱은 오른쪽에 붙는다. 링크(완료 화면)도 같은 모양을 쓴다. */
export const ctaClass =
  "inline-flex h-14 w-full items-center justify-center squircle [--r:14px] bg-primary px-7 text-[17px] font-bold text-[color:var(--cta-ink,#fff)] transition-colors " +
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
 * 지금 묻는 칸이 맨 위, 답한 칸은 그 아래에 최근 것부터(`order` 는 `fields` 의 번호, 맨 앞이 지금 칸).
 * 질문이 바뀌면 밀어 내린다 — 답한 칸은 있던 자리에서 새 자리로 미끄러지고(FLIP),
 * 새 칸은 위에서 살짝 내려오며 나타난다. 같은 번호의 칸은 같은 DOM 으로 남아 자리만 옮긴다.
 * 「동작 줄이기」면 움직이지 않는다.
 */
export function Cascade({ fields, order }: { fields: ReactNode[]; order: number[] }) {
  const box = useRef<HTMLDivElement>(null);
  // 지난번 그린 뒤 칸마다 페이지 기준 위치. 스크롤이 바뀌어도 맞도록 scrollY 를 더해 둔다.
  const last = useRef(new Map<string, number>());
  const key = order.join(",");
  useLayoutEffect(() => {
    const root = box.current;
    if (!root) return;
    const animate = last.current.size > 0 && !reducedMotion();
    const next = new Map<string, number>();
    const first = root.firstElementChild;
    // 「←」 로 돌아오면 그 칸은 새로 그려지지 않아 autoFocus 가 다시 안 걸린다. 여기서 옮겨 준다.
    if (first instanceof HTMLElement && last.current.has(first.dataset.cascade ?? "")) {
      first.querySelector<HTMLElement>('input[type="text"]')?.focus();
    }
    for (const el of Array.from(root.children) as HTMLElement[]) {
      const id = el.dataset.cascade ?? "";
      const top = el.getBoundingClientRect().top + window.scrollY;
      next.set(id, top);
      if (!animate) continue;
      const before = last.current.get(id);
      if (before === undefined) {
        el.animate(
          [
            { transform: "translateY(-18px)", opacity: 0 },
            { transform: "none", opacity: 1 },
          ],
          { duration: 360, delay: 90, easing: "cubic-bezier(0.2, 0.8, 0.2, 1)", fill: "backwards" },
        );
      } else if (before !== top) {
        el.animate([{ transform: `translateY(${before - top}px)` }, { transform: "none" }], {
          duration: 380,
          easing: "cubic-bezier(0.2, 0.8, 0.2, 1)",
        });
      }
    }
    last.current = next;
  }, [key]);
  return (
    <div ref={box}>
      {order.map((i) => (
        <div key={i} data-cascade={i}>
          {fields[i]}
        </div>
      ))}
    </div>
  );
}
