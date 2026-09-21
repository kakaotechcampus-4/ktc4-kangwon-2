import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // pdf-parse(pdf.js)는 런타임에 워커 파일을 직접 import한다.
  // 서버 번들에 함께 묶이면 .next/server/chunks/pdf.worker.mjs 경로가 깨져
  // production에서만 "Setting up fake worker failed"로 PDF 추출이 실패한다.
  serverExternalPackages: ["pdf-parse"],
  // 레거시 계획안 주소 — 정식 주소는 /plans/annual/new(생성) · /plans/annual/{id}(결과)다.
  // /plans/create 와 /plan-generator 는 쿼리를 다뤄야 해서 각자 페이지에서 redirect() 한다.
  async redirects() {
    return [
      { source: "/plans/setup", destination: "/plans/annual/new", permanent: false },
      { source: "/plans/start", destination: "/plans/annual/new", permanent: false },
    ];
  },
};

export default nextConfig;
