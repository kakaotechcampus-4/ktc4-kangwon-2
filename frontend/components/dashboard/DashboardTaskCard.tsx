import Link from "next/link";
import { Icon } from "@/components/app/icons";
import type { DashboardTask, Tone } from "@/lib/dashboard/mock";

const TONE: Record<Tone, string> = {
  sage: "bg-sage-tint text-sage-ink",
  mint: "bg-mint-tint text-mint-strong",
  peach: "bg-peach-tint text-peach-strong",
};

/** 화이트 카드 + 작은 파스텔 아이콘. 카드 전체를 색으로 채우지 않는다. */
export default function DashboardTaskCard({ task }: { task: DashboardTask }) {
  return (
    <Link
      href={task.href}
      className="group flex flex-col gap-2.5 min-h-0 lg:min-h-[196px] rounded-[20px] border border-line bg-paper p-5 shadow-[0_2px_8px_-4px_rgba(24,36,30,.08)] hover:border-sage-ink hover:-translate-y-px transition-[border-color,transform]"
    >
      <div className="flex items-start justify-between">
        <span className={`inline-flex items-center justify-center w-10 h-10 rounded-xl ${TONE[task.tone]}`}>
          <Icon name={task.icon} className="w-[19px] h-[19px]" />
        </span>
        <span className="font-mono text-[11.5px] tracking-[.06em] text-ink-soft">{String(task.count).padStart(2, "0")}</span>
      </div>
      <h3 className="font-display text-[16px] text-ink mt-2">{task.title}</h3>
      <p className="text-[13px] leading-[1.55] text-ink-soft">{task.description}</p>
      <span className="mt-auto pt-2.5 inline-flex items-center gap-1.5 text-[13px] font-bold text-sage-ink">
        {task.cta}
        <span aria-hidden="true" className="transition-transform group-hover:translate-x-[3px]">→</span>
      </span>
    </Link>
  );
}
