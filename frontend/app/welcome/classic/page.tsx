import LandingPage from "@/components/landing/LandingPage";

/**
 * 2026-11-04 까지 쓰던 옛 소개 화면. 새 화면(`/welcome`)으로 바꾸면서 되돌릴 때를 위해 남겨 둔다.
 * 검색에는 나오지 않게 한다 — 같은 내용이 두 주소에 있으면 검색 결과가 갈린다.
 */
export const metadata = {
  title: "쌤플 — 쌤의 계획이 쉬워지는 순간",
  robots: { index: false, follow: false },
};

export default function Page() {
  return <LandingPage />;
}
