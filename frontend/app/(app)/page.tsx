import HomePage from "@/components/dashboard/HomePage";

/**
 * 서비스 첫 화면. 주소는 "/" 다 — (app) 은 괄호라 주소에 안 들어간다.
 * 로그인 판정은 (app)/layout.tsx 의 DemoSessionGate, 원·반 판정은 RoomSetupGate(메인은 통과, 다른 화면은 안내 카드).
 */
export default function Page() {
  return <HomePage />;
}
