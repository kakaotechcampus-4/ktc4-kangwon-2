import PlanGeneratorPage from "@/components/plan-generator/PlanGeneratorPage";

/** 방식은 첫 화면이 쿼리로 넘긴다(`?format=MONTHLY_THEME|PLAY_PROJECT`). 모르는 값은 방식 없음이다. */
export default async function Page({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { format } = await searchParams;
  return (
    <PlanGeneratorPage
      format={format === "MONTHLY_THEME" || format === "PLAY_PROJECT" ? format : null}
    />
  );
}
