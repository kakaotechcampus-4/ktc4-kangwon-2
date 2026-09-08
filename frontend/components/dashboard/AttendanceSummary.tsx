import Link from "next/link";
import { Icon } from "@/components/app/icons";
import type { Attendance } from "@/lib/dashboard/mock";

/** 오늘의 등원 인원 — 전체 / 등원 / 결석 + 출석률 progress */
export default function AttendanceSummary({ data }: { data: Attendance }) {
  const rate = data.total ? (data.present / data.total) * 100 : 0;
  return (
    <section aria-labelledby="att-title">
      <div className="flex items-center justify-between font-display text-[16px] text-ink">
        <h2 id="att-title">오늘의 등원 인원</h2>
        <Link href="/home" aria-label="등원 현황 자세히" className="text-ink-soft hover:text-sage-ink">
          <Icon name="chevron" className="w-3.5 h-3.5" />
        </Link>
      </div>
      <dl className="grid grid-cols-[1.3fr_1fr_1fr] gap-3 mt-3.5 items-end tabular-nums">
        <div>
          <dd className="font-display text-[30px] lg:text-[34px] leading-none text-ink">{data.total}</dd>
          <dt className="text-[12px] text-ink-soft mt-1.5">전체 원아</dt>
        </div>
        <div>
          <dd className="font-display text-[22px] leading-[1.1] text-ink">{data.present}</dd>
          <dt className="text-[12px] text-ink-soft mt-1.5">등원</dt>
        </div>
        <div>
          <dd className="font-display text-[22px] leading-[1.1] text-peach-strong">{data.absent}</dd>
          <dt className="text-[12px] text-ink-soft mt-1.5">결석</dt>
        </div>
      </dl>
      <div className="flex items-center gap-3 mt-4 font-mono text-[11.5px] text-ink-soft">
        <span>
          출석률 <b className="text-ink">{rate.toFixed(1)}%</b>
        </span>
        <div className="flex-1 h-1.5 rounded-full bg-line overflow-hidden" role="progressbar" aria-valuenow={Math.round(rate)} aria-valuemin={0} aria-valuemax={100}>
          <div className="h-full rounded-full bg-sage-ink" style={{ width: `${rate}%` }} />
        </div>
      </div>
    </section>
  );
}
