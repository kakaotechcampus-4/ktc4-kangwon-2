"use client";
import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Icon } from "@/components/app/icons";
import { useRouter } from "next/navigation";
import {
  registerAccount,
  verifyAccount,
  verifyDevAccount,
  isDevLogin,
  completeAccountOnboarding,
} from "@/lib/auth/local-account";
import { restoreFromServer } from "@/lib/api/onboarding";
import { startDemoSession } from "@/lib/auth/demo-session";
import AuthFrame from "./AuthFrame";
import KakaoStart from "./KakaoStart";
import s from "./AuthFrame.module.css";

// 흰 종이 위 칸 — 테두리는 --pg-field-line(3.3:1). --pg-line 은 1.4:1 이라 칸이 안 보였다
const input =
  "mt-2 block w-full min-h-12 rounded-md border border-[color:var(--pg-field-line)] bg-paper px-3 py-3.5 text-sm outline-none " +
  "placeholder:text-ink-hint hover:border-ink-soft focus:border-primary focus:ring-2 focus:ring-primary-tint";
const button =
  "mt-6 flex min-h-12 w-full items-center justify-center gap-2 rounded-md border border-primary-line " +
  "bg-primary px-4 text-sm font-semibold text-white shadow-pg-hard hover:bg-primary-hover disabled:opacity-60";
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
type Typed = { name: string; email: string; password: string; confirm: string };
const label = "block text-xs font-semibold text-ink";
export default function AccountForm({ signup = false }: { signup?: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [visible, setVisible] = useState(false);
  const [done, setDone] = useState(false);
  // 로그인은 카카오 우선이라 이메일 칸을 접어 둔다(ADR-063). 가입 화면은 이메일로 가입하러 온 곳이라 펼쳐 둔다.
  const [emailOpen, setEmailOpen] = useState(signup);
  const emailInput = useRef<HTMLInputElement>(null);
  const opened = useRef(false);
  useEffect(() => {
    if (emailOpen && opened.current) emailInput.current?.focus();
  }, [emailOpen]);
  function toggleEmail() {
    opened.current = true;
    setEmailOpen(!emailOpen);
  }
  // 칠판 인사 · 할 일 목록이 보는 값. 제출은 여전히 FormData 로 읽는다
  const [typed, setTyped] = useState<Typed>({ name: "", email: "", password: "", confirm: "" });
  function track(event: FormEvent<HTMLFormElement>) {
    const t = event.target as HTMLInputElement;
    if (t.name in typed) setTyped({ ...typed, [t.name]: t.value });
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const email = String(form.get("email"));
    const password = String(form.get("password"));
    setError("");
    if (signup && !String(form.get("name")).trim()) {
      setError("선생님 이름을 입력해주세요.");
      return;
    }
    // 개발용 임시 계정(test@test)만 이메일 형식 검사를 건너뛴다. 나머지 규칙은 그대로.
    const devLogin = !signup && isDevLogin(email, password);
    if (!email.trim()) {
      setError("이메일을 입력해주세요.");
      return;
    }
    if (!devLogin && !EMAIL.test(email.trim())) {
      setError("올바른 이메일 형식으로 입력해주세요. 예: teacher@example.com");
      return;
    }
    if (!password) {
      setError("비밀번호를 입력해주세요.");
      return;
    }
    if (signup && password.length < 8) {
      setError("비밀번호는 8자 이상 입력해주세요.");
      return;
    }
    if (signup && password !== form.get("confirm")) {
      setError("비밀번호가 서로 달라요. 다시 확인해주세요.");
      return;
    }
    setBusy(true);
    try {
      if (signup) {
        await registerAccount(String(form.get("name")), email, password);
        if (!startDemoSession())
          throw new Error("가입은 됐어요. 로그인 화면에서 다시 로그인해주세요.");
        setDone(true);
        setBusy(false);
      } else {
        let centerId: number | null = null;
        if (devLogin) await verifyDevAccount(email, password);
        else centerId = await verifyAccount(email, password);
        if (!startDemoSession())
          throw new Error("로그인 정보를 저장할 수 없어요. 브라우저 설정을 확인해주세요.");
        if (centerId !== null) await restoreRoom(centerId);
        router.replace("/");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "처리하지 못했어요. 다시 시도해주세요.");
      setBusy(false);
    }
  }
  if (done) return <SignupDone />;
  const todo = signup && (
    <Todo
      items={[
        ["이름 적기", !!typed.name.trim()],
        ["이메일 적기", EMAIL.test(typed.email.trim())],
        ["비밀번호 8자 이상", typed.password.length >= 8],
        ["비밀번호 한 번 더", !!typed.confirm && typed.confirm === typed.password],
      ]}
    />
  );
  return (
    <AuthFrame
      greeting={
        signup ? (
          <SignupGreeting name={typed.name} />
        ) : (
          <>
            선생님의 하루에,
            <br />
            여유 한 뼘을.
          </>
        )
      }
      todo={todo}
      aside={<SwitchNote signup={signup} />}
    >
      <h2
        className="font-display text-[30px] font-bold sm:text-[34px]"
        style={{ wordSpacing: "-0.2em" }}
      >
        {signup ? "함께 시작해요" : "반가워요, 선생님"}
      </h2>
      <p className="mt-1 text-xs text-ink-soft">
        {signup
          ? "가입하면 바로 우리 원 · 반 설정으로 넘어가요."
          : "우리 반의 새로운 하루를 준비해 보세요."}
      </p>
      <KakaoStart />
      <p aria-hidden="true" className="mt-5 flex items-center gap-3 text-xs text-ink-hint">
        <span className="h-px flex-1 bg-[color:var(--pg-line)]" />
        또는
        <span className="h-px flex-1 bg-[color:var(--pg-line)]" />
      </p>
      {!signup && <EmailToggle open={emailOpen} onToggle={toggleEmail} />}
      <form
        id="email-form"
        noValidate
        hidden={!emailOpen}
        onSubmit={submit}
        onChange={track}
        className="mt-5 space-y-5"
      >
        {signup && (
          <label className={label}>
            선생님 이름
            <input
              className={input}
              name="name"
              autoComplete="name"
              placeholder="이름을 입력해주세요"
              required
              maxLength={40}
              disabled={busy}
            />
          </label>
        )}
        <label className={label}>
          이메일
          <input
            className={input}
            ref={emailInput}
            name="email"
            type="email"
            autoComplete="username"
            placeholder="teacher@example.com"
            required
            maxLength={254}
            disabled={busy}
          />
        </label>
        <div>
          <label htmlFor="auth-password" className={label}>
            비밀번호
          </label>
          <div className="relative">
            <input
              id="auth-password"
              className={`${input} pr-14`}
              name="password"
              type={visible ? "text" : "password"}
              autoComplete={signup ? "new-password" : "current-password"}
              placeholder={signup ? "8자 이상 입력해주세요" : "비밀번호를 입력해주세요"}
              required
              minLength={signup ? 8 : undefined}
              maxLength={128}
              disabled={busy}
            />
            <button
              type="button"
              aria-label={visible ? "비밀번호 숨기기" : "비밀번호 보기"}
              aria-pressed={visible}
              onClick={() => setVisible(!visible)}
              className="absolute bottom-1 right-1 min-h-11 rounded-md px-3 text-[13px] font-medium text-ink-soft hover:bg-primary-tint hover:text-primary-ink"
            >
              {visible ? "숨김" : "보기"}
            </button>
          </div>
        </div>
        {signup && (
          <label className={label}>
            비밀번호 확인
            <input
              className={input}
              name="confirm"
              type={visible ? "text" : "password"}
              autoComplete="new-password"
              placeholder="비밀번호를 한 번 더 입력해주세요"
              required
              minLength={8}
              maxLength={128}
              disabled={busy}
            />
          </label>
        )}
        {error && (
          <p
            role="alert"
            className="rounded-md border border-note-line bg-note-soft p-3 text-xs leading-relaxed text-sun-ink"
          >
            {error}
          </p>
        )}
        <button className={button} disabled={busy}>
          {busy ? "처리 중…" : signup ? "회원가입" : "로그인"}
          {!busy && <Icon name="arrow" className="h-4 w-4" />}
        </button>
      </form>
    </AuthFrame>
  );
}

/** 「이메일로 로그인」 — 누르면 이메일 · 비밀번호 칸이 펼쳐진다 */
function EmailToggle({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      aria-expanded={open}
      aria-controls="email-form"
      onClick={onToggle}
      className="mx-auto mt-2 flex min-h-11 items-center gap-1.5 rounded-md px-3 text-sm font-semibold text-ink hover:bg-primary-tint"
    >
      이메일로 로그인
      <svg
        viewBox="0 0 12 12"
        width="12"
        height="12"
        aria-hidden="true"
        className={`transition-transform ${open ? "rotate-180" : ""}`}
      >
        <path
          d="M3 4.5 6 7.5 9 4.5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </button>
  );
}

/** 칠판 인사 — 이름을 치면 그 칸만 바뀐다. 길면 8자에서 줄인다 */
function SignupGreeting({ name }: { name: string }) {
  const n = name.trim();
  const shown = n.length > 8 ? `${n.slice(0, 8)}…` : n;
  return (
    <>
      <span
        key={shown}
        className={`${s.swap} ${shown ? "border-b-2 border-dashed border-note/50 text-note" : ""}`}
      >
        {shown || "처음 오신"}
      </span>{" "}
      선생님,
      <br />
      반가워요.
    </>
  );
}

/** 회원가입 할 일 — 칸이 맞으면 칠판에서 ✓ 가 그어진다. 오류를 말하지는 않는다 */
function Todo({ items }: { items: [string, boolean][] }) {
  return (
    <ul
      aria-label="가입에 필요한 것"
      className="mt-7 grid gap-2 font-display text-[21px] font-bold text-board-ink-soft"
    >
      {items.map(([text, ok]) => (
        <li
          key={text}
          data-done={ok}
          className={`${s.todo} flex items-center gap-2.5 ${ok ? "text-board-ink" : ""}`}
        >
          <span className="relative h-5 w-5 shrink-0 rounded-[3px] border-2 border-board-ink-soft/70">
            <svg
              viewBox="0 0 22 22"
              aria-hidden="true"
              className="absolute -top-1 left-px h-[22px] w-[22px] overflow-visible"
            >
              <path
                d="M3 12 L9 18 L20 3"
                fill="none"
                stroke="var(--pg-note)"
                strokeWidth={3}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </span>
          <span>
            {text}
            <span className="sr-only">{ok ? " — 됐어요" : " — 아직"}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

/** 종이 가장자리에 붙은 노란 쪽지 — 로그인 ↔ 회원가입 */
function SwitchNote({ signup }: { signup: boolean }) {
  return (
    <Link
      href={signup ? "/login" : "/signup"}
      className="relative z-[2] ml-2 mr-8 mt-6 block -rotate-[1.5deg] border border-note-line bg-note px-3.5 pb-3 pt-3.5 text-sun-ink shadow-[3px_4px_0_rgb(0_0_0/0.28)] transition-transform hover:-rotate-[0.5deg] lg:absolute lg:-left-[118px] lg:top-[150px] lg:m-0 lg:w-[140px] lg:-rotate-[4deg] lg:hover:-translate-x-1 lg:hover:-rotate-2"
    >
      <span
        aria-hidden="true"
        className="absolute -top-[9px] left-10 h-[18px] w-[60px] border border-white/70 bg-tape"
      />
      <span className="block text-xs">{signup ? "계정이 있으세요?" : "처음 오셨어요?"}</span>
      <span className="mt-0.5 flex items-center gap-1.5 font-display text-[20px] font-bold leading-tight">
        {signup ? "로그인" : "회원가입"}
        <Icon name="arrow" className="h-4 w-4" />
      </span>
    </Link>
  );
}

/**
 * 다른 기기 · 브라우저에서 로그인한 교사의 원 · 반을 서버에서 채운다 (#291).
 * 반까지 들어오면 첫 설정을 끝낸 것으로 적는다. 로그인은 늘 메인(/)으로 간다 — 실패해도 이어 가고,
 * 그때는 메인에 닿아 다른 메뉴가 안내 카드를 보인다. 온보딩 1단계의 409 복구가 원을 다시 잇는다.
 */
export async function restoreRoom(centerId: number) {
  try {
    if (await restoreFromServer(centerId)) completeAccountOnboarding();
  } catch {}
}

/** 가입 직후 카드. 포스티는 큰 화면에서 카드 윗선에 걸터앉는다(몸통 밑이 테두리에 닿게 -99px). */
function SignupDone() {
  // 폼이 사라진 뒤 스크린리더가 제목을 읽게 한 번 포커스한다.
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), []);
  return (
    <AuthFrame
      greeting={
        <>
          선생님,
          <br />
          환영해요!
        </>
      }
    >
      <h2
        ref={heading}
        tabIndex={-1}
        className="font-display text-[30px] font-bold outline-none sm:text-[34px]"
      >
        가입을 완료했어요
      </h2>
      <p className="mt-1 text-xs text-ink-soft">이제 쌤플과 함께 우리 반의 하루를 준비해 보세요.</p>
      <Link href="/" className={button}>
        메인화면으로 가기
        <Icon name="arrow" className="h-4 w-4" />
      </Link>
    </AuthFrame>
  );
}
