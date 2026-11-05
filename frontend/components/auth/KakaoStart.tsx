"use client";
import { useState } from "react";
import { errorCode } from "@/lib/api/client";
import { startKakaoLogin } from "@/lib/auth/kakao";

/**
 * 카카오로 시작하기 (ADR-063). 이메일 폼 아래 「또는」 뒤 두 번째 길이다.
 * 처음 누르면 곧 가입이라 로그인 · 가입 화면 둘 다 같은 단추다.
 *
 * 색 · 심볼은 카카오 로그인 디자인 가이드를 따른다 — 바탕 #FEE500, 글자 · 심볼 검정 85%,
 * 말풍선 심볼은 모양을 바꾸지 않는다. 그래서 이 단추만 디자인 토큰 밖의 색을 쓴다.
 * 모서리 · 도장 그림자는 우리 단추와 맞춘다(가이드가 허용하는 범위).
 */
export default function KakaoStart() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function start() {
    setError("");
    setBusy(true);
    try {
      await startKakaoLogin();
      // 이동하는 동안 단추는 「가는 중」으로 둔다. 다시 눌리면 state 가 바뀌어 앞 요청이 버려진다.
    } catch (e) {
      setError(
        errorCode(e) === "DEPENDENCY_UNAVAILABLE"
          ? "지금은 카카오로 로그인할 수 없어요. 위 이메일로 로그인해주세요."
          : e instanceof Error
            ? e.message
            : "카카오로 가지 못했어요. 다시 시도해주세요.",
      );
      setBusy(false);
    }
  }

  return (
    <div>
      <button
        type="button"
        onClick={start}
        disabled={busy}
        className="flex min-h-12 w-full items-center justify-center gap-2.5 rounded-md border border-[#e5cf00] bg-[#FEE500] px-4 text-sm font-semibold text-black/85 shadow-pg-hard transition-transform hover:-translate-x-px hover:-translate-y-px active:translate-x-0.5 active:translate-y-0.5 active:shadow-none disabled:cursor-progress disabled:opacity-80"
      >
        {busy ? <Spinner /> : <KakaoSymbol />}
        {busy ? "카카오로 가는 중…" : "카카오로 시작하기"}
      </button>
      {error && (
        <p
          role="alert"
          className="mt-3 rounded-md border border-note-line bg-note-soft p-3 text-xs leading-relaxed text-sun-ink"
        >
          {error}
        </p>
      )}
    </div>
  );
}

function Spinner() {
  return (
    <span
      aria-hidden="true"
      className="h-4 w-4 animate-spin rounded-full border-2 border-black/25 border-t-black/85 motion-reduce:animate-none"
    />
  );
}

function KakaoSymbol() {
  return (
    <svg viewBox="0 0 24 22" width="20" height="18" aria-hidden="true">
      <path
        d="M12 1C5.9 1 1 4.9 1 9.7c0 3.1 2 5.8 5.1 7.3l-1.3 4.7c-.1.4.4.7.7.5l5.5-3.7c.3 0 .7.1 1 .1 6.1 0 11-3.9 11-8.8S18.1 1 12 1z"
        fill="#000"
      />
    </svg>
  );
}
