import Link from "next/link";
import { Icon } from "./icons";

/**
 * 쌤플 워드마크. 화면마다 색과 배치가 달라져 있던 것을 한 군데로 모았다.
 *
 * 「Ssample.」은 보라(`--pg-primary-deep`), 마침표 한 점만 흙빛(`--pg-peach-strong`),
 * 한글 「쌤플」은 그 아래 손글씨체로 선다. 로그인 화면만 초록으로 쓰던 것은 없앴다 —
 * 같은 서비스인데 들어가는 문에서만 다른 색이면 다른 서비스로 보인다.
 *
 * 왼쪽 ✳ 마크는 브랜드의 쪽지에서 온 것이다. 앱 아이콘(`app/icon.svg`)의 「S.」를
 * 여기 쓰지 않는 것은 바로 옆 「Ssample」과 같은 글자가 두 번 나오기 때문이다.
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
  /** `rail` 은 어두운 사이드바 위. 그 외에는 크림 바탕. */
  tone?: "ink" | "rail";
  size?: "sm" | "md";
  className?: string;
}) {
  const rail = tone === "rail";
  const big = size === "md";
  return (
    <Link href={href} aria-label={label} className={`flex items-center gap-2.5 ${className ?? ""}`}>
      <Icon
        name="star"
        className={`${big ? "h-[25px] w-[25px]" : "h-[21px] w-[21px]"} shrink-0 ${
          rail ? "text-primary-tint-line" : "text-primary"
        }`}
      />
      <span className="min-w-0">
        <span
          className={`block font-bold tracking-[-0.05em] ${big ? "text-[27px]" : "text-[23px]"} ${
            rail ? "text-rail-ink" : "text-primary-deep"
          } leading-none`}
        >
          Ssample<span className="text-peach-strong">.</span>
        </span>
        <span
          className={`block font-display font-bold leading-tight ${
            big ? "text-[17px]" : "text-[15px]"
          } ${rail ? "text-rail-ink-soft" : "text-ink-soft"}`}
        >
          쌤플
        </span>
      </span>
    </Link>
  );
}
