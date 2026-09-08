import { redirect } from "next/navigation";

/** 이전 경로 호환: /plan-generator → /plans/create */
export default function Page() {
  redirect("/plans/create");
}
