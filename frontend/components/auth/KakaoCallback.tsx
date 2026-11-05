"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Icon } from "@/components/app/icons";
import { verifyKakao } from "@/lib/auth/local-account";
import { takeKakaoState } from "@/lib/auth/kakao";
import { startDemoSession } from "@/lib/auth/demo-session";
import AuthFrame from "./AuthFrame";
import { restoreRoom } from "./AccountForm";

const button =
  "mt-6 flex min-h-12 w-full items-center justify-center gap-2 rounded-md border border-primary-line " +
  "bg-primary px-4 text-sm font-semibold text-white shadow-pg-hard hover:bg-primary-hover";

/** 돌아온 주소를 확인하고 로그인한다. 교사에게 보일 문장으로 throw 한다. */
async function finishKakao(params: URLSearchParams): Promise<number | null> {
  const code = params.get("code");
  // 교사가 동의 화면에서 「취소」를 누르면 code 없이 error=access_denied 로 돌아온다.
  if (params.get("error") || !code) {
    takeKakaoState(null);
    throw new Error("카카오 로그인을 취소했어요. 다시 시도하거나 이메일로 로그인해주세요.");
  }
  if (!takeKakaoState(params.get("state")))
    throw new Error("로그인 요청이 이 창에서 시작되지 않았어요. 로그인 화면에서 다시 눌러주세요.");
  const centerId = await verifyKakao(code);
  if (!startDemoSession())
    throw new Error("로그인 정보를 저장할 수 없어요. 브라우저 설정을 확인해주세요.");
  return centerId;
}

/**
 * 카카오 동의 화면에서 돌아온 자리 (`/login/kakao?code=…&state=…`).
 *
 * **인가 코드는 한 번만 쓸 수 있다.** 개발 모드의 StrictMode 는 effect 를 두 번 부르므로
 * ref 로 한 번만 보낸다 — 두 번 보내면 두 번째가 422 로 떨어져 성공한 로그인 위에 오류가 뜬다.
 */
export default function KakaoCallback() {
  const router = useRouter();
  const params = useSearchParams();
  const sent = useRef(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (sent.current) return;
    sent.current = true;
    finishKakao(new URLSearchParams(params.toString()))
      .then(async (centerId) => {
        if (centerId !== null) await restoreRoom(centerId);
        router.replace("/");
      })
      .catch((e) => setError(e instanceof Error ? e.message : "카카오 로그인을 마치지 못했어요."));
  }, [params, router]);

  if (error) return <Failed message={error} />;
  return (
    <Frame>
      <div role="status" aria-live="polite">
        <h2 className="font-display text-[30px] font-bold sm:text-[34px]">들어가는 중…</h2>
        <p className="mt-1 text-xs text-ink-soft">
          카카오 계정을 확인하고 우리 반 화면을 열고 있어요.
        </p>
        <span
          aria-hidden="true"
          className="mt-8 block h-6 w-6 animate-spin rounded-full border-2 border-primary border-r-transparent motion-reduce:animate-none"
        />
      </div>
    </Frame>
  );
}

function Failed({ message }: { message: string }) {
  return (
    <Frame>
      <div role="alert">
        <h2 className="font-display text-[30px] font-bold sm:text-[34px]">
          로그인을 마치지 못했어요
        </h2>
        <p className="mt-3 rounded-md border border-note-line bg-note-soft p-3 text-xs leading-relaxed text-sun-ink">
          {message}
        </p>
        <Link href="/login" className={button}>
          로그인 화면으로
          <Icon name="arrow" className="h-4 w-4" />
        </Link>
      </div>
    </Frame>
  );
}

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <AuthFrame
      greeting={
        <>
          카카오에서
          <br />
          돌아오는 중이에요.
        </>
      }
    >
      {children}
    </AuthFrame>
  );
}
