import { redirect } from "next/navigation";

/** 옛 주소. 화면 이름이 「주간 기록」이 된 뒤에도 주소만 남아 있었다. 북마크를 넘겨 준다. */
export default function Page() {
  redirect("/weekly-records");
}
