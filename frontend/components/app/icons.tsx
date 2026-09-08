import type { SVGProps } from "react";

export type IconName = "home" | "plan" | "record" | "doc" | "eval" | "settings" | "search" | "bell" | "chevron" | "chevronLeft" | "sparkle";

const PATHS: Record<IconName, React.ReactNode> = {
  home: <path d="M4 10.5 12 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-6h-5v6H5a1 1 0 0 1-1-1z" />,
  plan: (<><rect x="4" y="4" width="16" height="16" rx="3" /><path d="M8 9h8M8 13h8M8 17h5" /></>),
  record: (<><path d="M6 4h8l4 4v12H6z" /><path d="M14 4v4h4M9 13h6M9 17h4" /></>),
  doc: (<><rect x="5" y="3.5" width="14" height="17" rx="2.5" /><path d="M9 8h6M9 12h6M9 16h3" /></>),
  eval: (<><circle cx="12" cy="12" r="8.5" /><path d="M8.5 12.5l2.3 2.3L15.8 9.8" /></>),
  settings: (<><circle cx="12" cy="12" r="3" /><path d="M12 3.5v2M12 18.5v2M3.5 12h2M18.5 12h2M6 6l1.4 1.4M16.6 16.6 18 18M6 18l1.4-1.4M16.6 7.4 18 6" /></>),
  search: (<><circle cx="11" cy="11" r="6.5" /><path d="m20 20-4-4" /></>),
  bell: (<><path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z" /><path d="M10 20a2 2 0 0 0 4 0" /></>),
  chevron: <path d="m9 6 6 6-6 6" />,
  chevronLeft: <path d="m15 6-6 6 6 6" />,
  sparkle: (<><path d="M12 3.5l1.6 4.2 4.2 1.6-4.2 1.6L12 15.1l-1.6-4.2-4.2-1.6 4.2-1.6z" /><path d="M5.5 16.5l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z" /></>),
};

/** 선 아이콘 (stroke = currentColor). 사이드바·헤더·카드에서 공용. */
export function Icon({ name, ...rest }: { name: IconName } & SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...rest}>
      {PATHS[name]}
    </svg>
  );
}
