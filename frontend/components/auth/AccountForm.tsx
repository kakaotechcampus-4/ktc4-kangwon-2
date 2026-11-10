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
import { moveLegacyImports } from "@/lib/workspace/store";
import AuthFrame, { ErrorNote } from "./AuthFrame";
import KakaoStart from "./KakaoStart";
import { Posty } from "@/components/app/Posty";

// 공책 줄에 적는 칸 — 밑줄 하나. 밑줄은 --pg-field-line(종이 위 3.3:1). 적는 줄은 보라 연필 선이 된다
const input =
  "mt-0.5 block h-11 w-full rounded-none font-body font-normal tracking-normal text-ink border-0 border-b-[1.5px] border-[color:var(--pg-field-line)] bg-transparent px-0.5 text-base outline-none " +
  "placeholder:text-ink-hint hover:border-ink-soft focus:border-b-2 focus:border-primary";
// 공책에 붙인 견출지처럼 둥근 단추
export const button =
  "flex h-[50px] w-full items-center justify-center gap-2 rounded-full border border-primary-line " +
  "bg-primary px-5 text-[15px] font-bold text-white shadow-pg-card transition-transform hover:-translate-x-px hover:-translate-y-px hover:bg-primary-hover active:translate-x-0.5 active:translate-y-0.5 active:shadow-none disabled:cursor-progress disabled:opacity-80";
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
// 제목은 손글씨, 입력 칸 이름은 작은 크기에서도 읽기 쉬운 본문 글꼴을 쓴다.
const label = "block font-body text-sm font-semibold text-ink-soft focus-within:text-primary-ink";
export default function AccountForm({ signup = false }: { signup?: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [visible, setVisible] = useState(false);
  const [done, setDone] = useState(false);
  const [caps, setCaps] = useState(false);
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
      setError("이메일 형식을 확인해주세요. 예: teacher@example.com");
      return;
    }
    if (!password) {
      setError("비밀번호를 입력해주세요.");
      return;
    }
    if (signup && password.length < 8) {
      setError("비밀번호는 8자 이상이어야 해요.");
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
  const actionLabel = signup ? "회원가입" : "로그인";
  const submitLabel = busy ? `${actionLabel} 중…` : actionLabel;
  return (
    <AuthFrame>
      <h2 className="font-display text-[36px] font-bold leading-[1.2]">
        {signup ? "쌤플과 함께 시작해요" : "반가워요, 선생님"}
      </h2>
      <p className="mt-1.5 text-sm leading-relaxed text-ink-soft [word-break:keep-all]">
        {signup
          ? "가입하고 우리 원과 반을 알려 주시면 바로 시작해요."
          : "우리 반의 새로운 하루를 준비해 보세요."}
      </p>
      <form noValidate onSubmit={submit} aria-busy={busy} className="mt-7 flex flex-col gap-[22px]">
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
            inputMode="email"
            autoComplete="username"
            placeholder="이메일을 입력해주세요"
            required
            maxLength={254}
            disabled={busy}
          />
        </label>
        <div className={label}>
          <label htmlFor="auth-password">비밀번호</label>
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
              onKeyUp={(e) => setCaps(e.getModifierState("CapsLock"))}
            />
            <button
              type="button"
              aria-label={visible ? "비밀번호 숨기기" : "비밀번호 보기"}
              aria-pressed={visible}
              onClick={() => setVisible(!visible)}
              className="absolute bottom-0.5 right-0 h-10 min-w-[52px] rounded px-2.5 font-body text-[13px] font-medium tracking-normal text-ink-soft hover:bg-primary-tint hover:text-primary-ink"
            >
              {visible ? "숨기기" : "보기"}
            </button>
          </div>
          {caps && (
            <p
              role="status"
              className="mt-1.5 font-body text-xs font-medium tracking-normal text-sun-ink"
            >
              Caps Lock이 켜져 있어요. 대소문자를 확인해주세요.
            </p>
          )}
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
        {error && <ErrorNote>{error}</ErrorNote>}
        <button className={`${button} mt-3`} disabled={busy}>
          {submitLabel}
          {!busy && <Icon name="arrow" className="h-4 w-4" />}
        </button>
      </form>
      <p aria-hidden="true" className="my-5 flex items-center gap-3 text-xs text-ink-hint">
        <span className="flex-1 border-t-[1.5px] border-dashed border-line" />
        또는
        <span className="flex-1 border-t-[1.5px] border-dashed border-line" />
      </p>
      <KakaoStart />
      <p className="mt-5 flex flex-wrap items-center justify-center gap-1 text-[13px] text-ink-soft">
        {signup ? "이미 계정이 있으신가요?" : "아직 계정이 없으신가요?"}
        <Link
          href={signup ? "/login" : "/signup"}
          className="flex min-h-11 items-center px-0.5 font-bold text-primary-ink underline decoration-1 underline-offset-[5px] hover:no-underline"
        >
          {signup ? "로그인" : "회원가입"}
        </Link>
      </p>
    </AuthFrame>
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
    // 반 · 아동 서버 번호가 채워진 뒤라야 예전 증빙을 올릴 수 있다. 원 복구가 실패하면 다음 로그인에 한다.
    await moveLegacyImports();
  } catch {}
}

/** 가입 직후 — 공책 한 장에 포스티가 반기고 메인으로 보낸다. */
function SignupDone() {
  // 폼이 사라진 뒤 스크린리더가 제목을 읽게 한 번 포커스한다.
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), []);
  return (
    <AuthFrame>
      <Posty pose="cheer" face="done" tape size={64} label={null} className="mb-3 block" />
      <h2
        ref={heading}
        tabIndex={-1}
        className="font-display text-[36px] font-bold leading-[1.2] outline-none"
      >
        가입을 완료했어요
      </h2>
      <p className="mb-7 mt-1.5 text-sm text-ink-soft">
        이제 원과 반 정보를 등록하고 기록을 시작해 보세요.
      </p>
      <Link href="/" className={button}>
        메인화면으로 가기
        <Icon name="arrow" className="h-4 w-4" />
      </Link>
    </AuthFrame>
  );
}
