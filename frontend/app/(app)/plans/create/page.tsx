import PlanGeneratorPage from "@/components/plan-generator/PlanGeneratorPage";

export const metadata = { title: "계획안 생성" };

/** 기존 계획안 생성 화면을 공통 셸(사이드바) 안에 그대로 배치. embedded 로 자체 헤더만 끈다. */
export default function Page() {
  return <PlanGeneratorPage embedded />;
}
