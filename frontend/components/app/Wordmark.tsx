import Link from "next/link";

/**
 * 쌤플 워드마크. 화면마다 색과 배치가 달라져 있던 것을 한 군데로 모았다.
 *
 * 「Ssample.」은 보라(`--pg-primary-deep`), 마침표 한 점만 흙빛(`--pg-peach-strong`),
 * 한글 「쌤플」은 그 아래 손글씨체로 선다.
 *
 * 왼쪽에 쓰던 ✳ 마크 자리에는 네모 칸용 **「S.」 아이콘**이 선다. 브라우저 탭·앱
 * 아이콘(`app/icon.svg`)과 같은 표시다 — 쌤플의 표시는 이 워드마크와 「S.」 둘뿐이다.
 *
 * 어두운 사이드바 위(`tone="rail"`)에서는 글자색만 바꾼다 — 밝은 타일을 깔면
 * 사이드바에 네모 하나가 더 생겨 메뉴보다 먼저 눈에 띈다.
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
      className={`flex items-center gap-2.5 ${className ?? ""}`}
    >
      {!tiny && <SsampleMark size={big ? 34 : 30} />}
      <span className="min-w-0">
      <span
        className={`block font-bold leading-none tracking-[-0.05em] ${
          big ? "text-[27px]" : tiny ? "text-[16px]" : "text-[23px]"
        } ${rail ? "text-rail-ink" : "text-primary-deep"}`}
      >
        Ssample<span className="text-peach-strong">.</span>
      </span>
      {!tiny && (
        <span
          className={`block font-display font-bold leading-tight ${
            big ? "text-[17px]" : "text-[15px]"
          } ${rail ? "text-rail-ink-soft" : "text-ink-soft"}`}
        >
          쌤플
        </span>
      )}
      </span>
    </Link>
  );
}

/**
 * 네모 칸에 들어가는 쌤플 표시 — 크림 타일 위의 세리프 「S」 와 흙빛 점 하나.
 *
 * `app/icon.svg` 와 같은 모양이다. 둘이 어긋나면 브라우저 탭과 화면 안의 표시가
 * 다른 서비스처럼 보이므로, 한쪽을 고치면 다른 쪽도 같이 고친다.
 */
export function SsampleMark({ size = 34 }: { size?: number }) {
  return (
    <span
      aria-hidden="true"
      className="flex shrink-0 items-center justify-center rounded-[11px] bg-cream font-serif font-bold leading-none tracking-[-0.02em] text-primary-deep"
      style={{ width: size, height: size, fontSize: Math.round(size * 0.62) }}
    >
      S<span className="text-peach-strong">.</span>
    </span>
  );
}
