import Link from "next/link";
import { RECORD_STATUS_LABEL, type RecentRecord, type RecordStatus } from "@/lib/dashboard/mock";

/* 상태 배지: 교사 검토 필요 → Point 1 / AI 초안 → Point 2 / 확정 → Main */
const BADGE: Record<RecordStatus, string> = {
  review: "bg-peach-tint text-peach-ink",
  draft: "bg-mint-tint text-mint-ink",
  confirmed: "bg-sage-tint text-sage-ink",
};

export default function RecentRecordList({ records }: { records: RecentRecord[] }) {
  return (
    <section aria-labelledby="rec-title">
      <div className="flex items-center justify-between font-display text-[16px] text-ink">
        <h2 id="rec-title">최근 기록</h2>
        <Link href="/home" className="text-[12.5px] font-body text-ink-soft hover:text-sage-ink">기록 관리 →</Link>
      </div>
      <div className="mt-3 rounded-2xl border border-line overflow-hidden">
        <div className="grid grid-cols-[88px_minmax(0,1fr)_auto] lg:grid-cols-[96px_minmax(0,1fr)_auto] gap-2.5 px-3.5 py-2 text-[11px] text-ink-soft bg-cream">
          <span>원아</span><span>관찰 기록</span><span>상태</span>
        </div>
        <ul>
          {records.map((r) => (
            <li key={r.id} className="grid grid-cols-[88px_minmax(0,1fr)_auto] lg:grid-cols-[96px_minmax(0,1fr)_auto] gap-2.5 items-center px-3.5 py-[11px] border-t border-line bg-paper">
              <span className="flex items-center gap-2 min-w-0 text-[13px] font-bold text-ink">
                <span aria-hidden="true" className="inline-flex items-center justify-center w-[26px] h-[26px] rounded-full bg-mint-tint text-mint-ink text-[11px] font-bold shrink-0">
                  {r.childName.slice(-2)}
                </span>
                <span className="truncate">{r.childName}</span>
              </span>
              <span className="text-[12.5px] text-ink-soft truncate">{r.text}</span>
              <span className={`text-[11px] font-medium px-2 py-1 rounded-lg whitespace-nowrap ${BADGE[r.status]}`}>{RECORD_STATUS_LABEL[r.status]}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
