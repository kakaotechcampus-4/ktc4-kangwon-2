"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { endDemoSession } from "@/lib/auth/demo-session";
import AuthFrame from "./AuthFrame";

export default function LogoutPage() {
  const router = useRouter();
  const [error, setError] = useState("");
  function logout() {
    if (!endDemoSession()) { setError("로그아웃하지 못했어요. 브라우저 설정을 확인하고 다시 시도해주세요."); return; }
    setError("");
    router.replace("/login");
  }
  useEffect(() => {
    if (endDemoSession()) router.replace("/login");
    else setError("로그아웃하지 못했어요. 다시 시도해주세요.");
  }, [router]);
  return <AuthFrame>
    {error ? <><p role="alert" className="text-sm text-peach-ink">{error}</p><button type="button" onClick={logout} className="mt-6 w-full min-h-12 rounded-2xl bg-sage font-bold hover:bg-sage-ink">다시 시도</button></> : <p role="status" className="text-sm text-ink-soft">로그인 화면으로 이동하고 있어요.</p>}
  </AuthFrame>;
}
