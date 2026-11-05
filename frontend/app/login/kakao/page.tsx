import { Suspense } from "react";
import KakaoCallback from "@/components/auth/KakaoCallback";
export const metadata = { title: "카카오 로그인 · 쌤플" };
/** 카카오 동의 뒤 돌아오는 자리. 서버 `.env` 의 `KAKAO_REDIRECT_URI` 가 이 주소다 (ADR-063). */
export default function Page() {
  return (
    <Suspense>
      <KakaoCallback />
    </Suspense>
  );
}
