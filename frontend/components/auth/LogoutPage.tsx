"use client";

import { startTransition, useActionState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { endDemoSession } from "@/lib/auth/demo-session";
import AuthFrame from "./AuthFrame";

export default function LogoutPage() {
  const router = useRouter();
  // 로그아웃은 "세션 정리"라는 외부 동작이라 액션으로 실행하고, 실패 메시지만 상태로 남긴다.
  const [error, logout] = useActionState((_previous: string, retry: boolean) => {
    if (endDemoSession()) {
      router.replace("/login");
      return "";
    }
    return retry
      ? "로그아웃하지 못했어요. 브라우저 설정을 확인하고 다시 시도해주세요."
      : "로그아웃하지 못했어요. 다시 시도해주세요.";
  }, "");
  useEffect(() => {
    startTransition(() => logout(false));
  }, [logout]);
  return (
    <AuthFrame>
      {error ? (
        <>
          <p role="alert" className="text-sm text-peach-ink">
            {error}
          </p>
          <button
            type="button"
            onClick={() => startTransition(() => logout(true))}
            className="mt-6 w-full min-h-12 rounded-2xl bg-sage font-bold hover:bg-sage-ink"
          >
            다시 시도
          </button>
        </>
      ) : (
        <p role="status" className="text-sm text-ink-soft">
          로그인 화면으로 이동하고 있어요.
        </p>
      )}
    </AuthFrame>
  );
}
