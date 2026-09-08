/**
 * 홈(메인) 화면 Mock Data — API 연동 전 화면 확인용.
 * 실제 연동 시 이 파일의 함수를 fetch 로 교체하고 컴포넌트 props 형태는 유지한다.
 */
import type { IconName } from "@/components/app/icons";

export type Tone = "sage" | "mint" | "peach";

export interface DashboardTask {
  id: string;
  title: string;
  description: string;
  count: number;
  cta: string;
  href: string;
  icon: IconName;
  tone: Tone;
}

export const TODAY_TASKS: DashboardTask[] = [
  { id: "records", title: "확인이 필요한 기록", description: "관찰 기록 2건을 확인해 주세요.", count: 2, cta: "기록 확인", href: "/home", icon: "record", tone: "sage" },
  { id: "drafts", title: "검토할 AI 문서", description: "기록을 바탕으로 생성된 초안을 확인해 주세요.", count: 2, cta: "초안 검토", href: "/home", icon: "sparkle", tone: "mint" },
  { id: "weekly-plan", title: "처리해야 할 업무", description: "이번 주 주간계획안을 등록해 주세요.", count: 1, cta: "업무 보기", href: "/plans/create", icon: "eval", tone: "peach" },
];

export interface Attendance {
  total: number;
  present: number;
  absent: number;
}
export const TODAY_ATTENDANCE: Attendance = { total: 18, present: 16, absent: 2 };

export type RecordStatus = "review" | "draft" | "confirmed";
export interface RecentRecord {
  id: string;
  childName: string;
  text: string;
  status: RecordStatus;
}
export const RECENT_RECORDS: RecentRecord[] = [
  { id: "r1", childName: "김도윤", text: "블록으로 긴 기차를 만들었어요", status: "review" },
  { id: "r2", childName: "이서윤", text: "낙엽의 색과 모양을 관찰했어요", status: "draft" },
  { id: "r3", childName: "박하준", text: "점심 시간 스스로 정리했어요", status: "confirmed" },
];

export const RECORD_STATUS_LABEL: Record<RecordStatus, string> = {
  review: "교사 검토 필요",
  draft: "AI 초안",
  confirmed: "확정",
};

/** 달력 dot 마커 — key: "YYYY-M(0-based)" → { day: tone } */
export function calendarMarksFor(year: number, month0: number): Record<number, Tone> {
  const now = new Date();
  if (year === now.getFullYear() && month0 === now.getMonth()) {
    return { 3: "mint", 10: "peach", 15: "sage", 22: "peach", 25: "mint" };
  }
  return {};
}
