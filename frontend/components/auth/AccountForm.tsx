"use client";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { Icon } from "@/components/app/icons";
import { useRouter } from "next/navigation";
import {
  registerAccount,
  verifyAccount,
  verifyDevAccount,
  isDevLogin,
  loginDestination,
} from "@/lib/auth/local-account";
import { startDemoSession } from "@/lib/auth/demo-session";
import AuthFrame from "./AuthFrame";

const input =
  "mt-2 block w-full min-h-12 rounded-md border border-line bg-cream px-3 py-3.5 text-sm outline-none " +
  "placeholder:text-ink-soft focus:border-success focus:ring-2 focus:ring-success-tint";
const button =
  "mt-6 flex min-h-12 w-full items-center justify-center gap-2 rounded-md border border-success-line " +
  "bg-success px-4 text-sm font-semibold text-white shadow-pg-card hover:bg-success-hover disabled:opacity-60";
const label = "block text-xs font-semibold text-ink";
export default function AccountForm({ signup = false }: { signup?: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [visible, setVisible] = useState(false);
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
    if (!devLogin && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
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
        setDone(true);
        setBusy(false);
      } else {
        if (devLogin) await verifyDevAccount(email, password);
        else await verifyAccount(email, password);
        if (!startDemoSession())
          throw new Error("로그인 정보를 저장할 수 없어요. 브라우저 설정을 확인해주세요.");
        router.replace(loginDestination());
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "처리하지 못했어요. 다시 시도해주세요.");
      setBusy(false);
    }
  }
  return (
    <AuthFrame>
      <span className="inline-block rounded-full bg-success-tint px-3 py-1.5 text-[10px] font-semibold text-success">
        {signup ? "쌤플과 함께 시작해요" : "다시 만나 반가워요"}
      </span>
      <h2 className="mt-4 font-display text-[30px] font-bold sm:text-[36px]">
        {done ? "가입을 완료했어요" : signup ? "함께 시작해요" : "반가워요, 선생님"}
      </h2>
      <p className="mt-1 text-xs text-ink-soft">
        {done
          ? "로그인하고 우리 반 초기 설정을 시작해보세요."
          : "우리 반의 새로운 하루를 준비해 보세요."}
      </p>
      {done ? (
        <Link href="/login" className={button}>
          로그인하러 가기
          <Icon name="arrow" className="h-4 w-4" />
        </Link>
      ) : (
        <>
          <form noValidate onSubmit={submit} className="mt-7 space-y-5">
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
                  className="absolute bottom-1 right-1 min-h-11 px-2 text-[10px] font-medium text-success"
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
          <p className="mt-5 text-center text-xs text-ink-soft">
            {signup ? "이미 계정이 있으신가요?" : "아직 계정이 없으신가요?"}
            <Link
              href={signup ? "/login" : "/signup"}
              className="ml-2 font-semibold text-success underline underline-offset-4"
            >
              {signup ? "로그인" : "회원가입"}
            </Link>
          </p>
        </>
      )}
    </AuthFrame>
  );
}
