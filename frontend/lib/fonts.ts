import { Gowun_Dodum, JetBrains_Mono, Noto_Sans_KR } from "next/font/google";

/**
 * 새싹플랜 공통 폰트. next/font 는 모듈 스코프에서만 호출할 수 있으므로
 * 여기서 한 번 선언하고 루트 레이아웃 <html> 에 variable 클래스를 붙인다.
 * (tailwind: font-display / font-body / font-mono 가 이 CSS 변수를 참조)
 */
export const display = Gowun_Dodum({ subsets: ["korean"], weight: "400", variable: "--font-display" });
export const body = Noto_Sans_KR({ subsets: ["korean"], weight: ["400", "500", "700", "900"], variable: "--font-body" });
export const mono = JetBrains_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-mono" });

export const fontClassName = `${display.variable} ${body.variable} ${mono.variable}`;
