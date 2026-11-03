import Link from "next/link";

/**
 * 쌤플 워드마크. 화면마다 색과 배치가 달라져 있던 것을 한 군데로 모았다.
 *
 * 「Ssample.」은 보라(`--pg-primary-deep`), 마침표 한 점만 흙빛(`--pg-peach-strong`),
 * 한글 「쌤플」은 그 아래 손글씨체로 선다.
 *
 * 쌤플의 표시는 **둘**이다 — 가로로 긴 이 워드마크와, 네모 칸에 들어가는 「S.」
 * 아이콘(`app/icon.svg`, 브라우저 탭·앱 아이콘). 워드마크 왼쪽에 쓰던 ✳ 마크는 뺐다.
 * 표시가 셋이 되면 어느 것이 쌤플인지 흐려진다 (PM 점검 2026-11-03).
 *
 * 어두운 사이드바 위(`tone="rail"`)에서는 글자색만 바꾸지 않고 **크림 타일**에 얹는다.
 * 같은 보라 글자를 그대로 쓸 수 있어, 들어가는 문마다 색이 달라 보이던 문제가 없어진다.
 */
export function Wordmark({
  href = "/",
  label = "쌤플 홈으로",
  tone = "ink",
  size = "md",
  className,
}: {
  href?: string;
  label?: string;
  /** `rail` 은 어두운 사이드바 위 — 크림 타일을 깔고 그 위에 쓴다. */
  tone?: "ink" | "rail";
  /** `xs` 는 상단 띠처럼 한 줄밖에 없는 자리. 한글 「쌤플」을 접고 영문만 쓴다. */
  size?: "xs" | "sm" | "md";
  className?: string;
}) {
  const rail = tone === "rail";
  const big = size === "md";
  const tiny = size === "xs";
  return (
    <Link
      href={href}
      aria-label={label}
      className={`inline-flex min-w-0 flex-col ${
        rail ? "rounded-[14px] bg-cream px-3.5 pb-2 pt-2.5" : ""
      } ${className ?? ""}`}
    >
      <span
        className={`block font-bold leading-none tracking-[-0.05em] text-primary-deep ${
          big ? "text-[27px]" : tiny ? "text-[16px]" : "text-[23px]"
        }`}
      >
        Ssample<span className="text-peach-strong">.</span>
      </span>
      {!tiny && (
        <span
          className={`block font-display font-bold leading-tight text-ink-soft ${
            big ? "text-[17px]" : "text-[15px]"
          }`}
        >
          쌤플
        </span>
      )}
    </Link>
  );
}
