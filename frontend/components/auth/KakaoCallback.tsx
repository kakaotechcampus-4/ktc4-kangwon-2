"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Icon } from "@/components/app/icons";
import { ApiError, errorCode, invalidFields } from "@/lib/api/client";
import { verifyKakao } from "@/lib/auth/local-account";
import { takeKakaoState } from "@/lib/auth/kakao";
import { startDemoSession } from "@/lib/auth/demo-session";
import AuthFrame from "./AuthFrame";
import { restoreRoom } from "./AccountForm";

const AGAIN = "로그인 시간이 지났어요. 로그인 화면에서 「카카오로 시작하기」를 다시 눌러 주세요.";

/**
 * 서버 오류를 화면 말투(해요체)로 바꾼다. 서버 문구는 다른 인증 오류와 같은 「습니다」체라
 * 그대로 띄우면 「로그인을 마치지 못했어요」 밑에 「…있습니다」가 붙는다.
 */
function kakaoMessage(e: unknown): string {
  if (invalidFields(e, { code: "code" }).length) return AGAIN;
  if (invalidFields(e, { email: "email" }).length)
    return "카카오 계정 이메일이 필요해요. 다시 로그인하면서 이메일 제공에 동의해 주세요.";
  if (errorCode(e) === "ALREADY_EXISTS")
    return "이 이메일은 다른 카카오 계정에 연결돼 있어요. 이메일로 로그인해 주세요.";
  if (errorCode(e) === "DEPENDENCY_UNAVAILABLE")
    return "지금은 카카오로 로그인할 수 없어요. 이메일로 로그인해 주세요.";
  // 화면이 직접 던진 문장(취소 · 시간 지남 · 저장 실패)만 그대로 쓴다.
  // 그 밖의 서버 오류 · 망 끊김(TypeError)은 같은 한 문장으로 말한다.
  if (e instanceof Error && !(e instanceof ApiError) && !(e instanceof TypeError)) return e.message;
  return "카카오 로그인을 마치지 못했어요. 잠시 뒤 다시 해 주세요.";
}

const button =
  "mt-6 flex min-h-12 w-full items-center justify-center gap-2 rounded-md border border-primary-line " +
  "bg-primary px-4 text-sm font-semibold text-white shadow-pg-hard hover:bg-primary-hover";

/** 돌아온 주소를 확인하고 로그인한다. 교사에게 보일 문장으로 throw 한다. */
async function finishKakao(params: URLSearchParams): Promise<number | null> {
  const code = params.get("code");
  // 교사가 동의 화면에서 「취소」를 누르면 code 없이 error=access_denied 로 돌아온다.
  if (params.get("error") === "access_denied") {
    takeKakaoState(null);
    throw new Error("카카오 로그인을 취소했어요.");
  }
  if (params.get("error") || !code) {
    takeKakaoState(null);
    throw new Error("카카오 로그인을 마치지 못했어요. 잠시 뒤 다시 해 주세요.");
  }
  // 새로고침 · 탭을 닫았다 연 경우 · 다른 탭에서 시작한 경우가 여기로 온다.
  if (!takeKakaoState(params.get("state"))) throw new Error(AGAIN);
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
      .catch((e) => setError(kakaoMessage(e)));
  }, [params, router]);

  if (error) return <Failed message={error} />;
  return (
    <Frame failed={false}>
      <div role="status" aria-live="polite">
        <h2 className="font-display text-[30px] font-bold sm:text-[34px]">로그인하는 중…</h2>
        <p className="mt-1 text-xs text-ink-soft">카카오 계정을 확인하고 있어요.</p>
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
    <Frame failed>
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

/** 칠판 인사 — 기다리는 동안과 실패했을 때가 다르다. 실패 뒤에 「돌아왔어요」가 남으면 안 된다 */
function Frame({ failed, children }: { failed: boolean; children: React.ReactNode }) {
  const greeting = failed ? (
    <>
      괜찮아요,
      <br />
      다시 해 봐요.
    </>
  ) : (
    <>
      카카오에서
      <br />
      돌아왔어요.
    </>
  );
  return <AuthFrame greeting={greeting}>{children}</AuthFrame>;
}
