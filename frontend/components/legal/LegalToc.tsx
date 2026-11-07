"use client";

import { useEffect, useState } from "react";
import s from "./Legal.module.css";

/**
 * 약관 · 개인정보 문서의 목차. 지금 읽고 있는 항목에 표시가 붙는다.
 * 넓은 화면에서는 왼쪽에 붙어 따라오고, 좁은 화면에서는 접힌 「목차」가 된다.
 */
export function LegalToc({ items }: { items: { id: string; heading: string }[] }) {
  const [active, setActive] = useState(items[0]?.id ?? "");

  useEffect(() => {
    const seen = new Map<string, boolean>();
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => seen.set(e.target.id, e.isIntersecting));
        const first = items.find((it) => seen.get(it.id));
        if (first) setActive(first.id);
      },
      { rootMargin: "-20% 0px -60% 0px" },
    );
    items.forEach((it) => {
      const el = document.getElementById(it.id);
      if (el) io.observe(el);
    });
    return () => io.disconnect();
  }, [items]);

  const list = (
    <ol className={s.tocList}>
      {items.map((it) => (
        <li key={it.id}>
          <a href={`#${it.id}`} aria-current={it.id === active ? "true" : undefined}>
            {it.heading}
          </a>
        </li>
      ))}
    </ol>
  );

  return (
    <nav className={s.toc} aria-label="목차">
      <p className={s.tocTitle}>목차</p>
      <div className={s.tocWide}>{list}</div>
      <details className={s.tocNarrow}>
        <summary>목차 펼치기</summary>
        {list}
      </details>
    </nav>
  );
}
