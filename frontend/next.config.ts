import type { NextConfig } from "next";
const config: NextConfig = {
  async redirects() {
    // 레거시 주소만 정식 주소로 보낸다. (/plans/create 는 ?annual= 처리 때문에 page.tsx에서 redirect)
    // 계획안은 /plans/annual/new 한 화면으로 바로 진입한다 — 문서 구성(setup)·시작 방식(start) 단계는 쓰지 않는다.
    return ["/plans/setup", "/plans/start", "/plan-generator"].map(source => ({ source, destination: "/plans/annual/new", permanent: false }));
  },
  async rewrites() {
    const origin = process.env.FASTAPI_BASE_URL?.replace(/\/$/, "");
    if (!origin) return [];
    return ["/api/centers", "/api/centers/:path*", "/api/classes/:path*", "/api/children/:path*", "/api/plans/:path*"].map(source => ({source, destination:origin+source}));
  },
  serverExternalPackages: ["pdf-parse", "pdfjs-dist", "mammoth"],
};
export default config;
