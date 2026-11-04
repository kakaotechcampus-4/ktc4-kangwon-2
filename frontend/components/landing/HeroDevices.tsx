"use client";

import Image from "next/image";
import { useRef, type PointerEvent } from "react";
import s from "./Welcome.module.css";

/**
 * 첫 화면의 노트북 창과 휴대폰. 포인터를 따라 두 기기가 서로 반대로 아주 조금 움직인다.
 *
 * 움직임은 CSS 변수(--px · --py)만 바꾼다 — 상태를 두지 않아 다시 그리지 않는다.
 * 움직임 줄이기를 켠 사람에게는 CSS 쪽에서 변수를 무시한다.
 */
export function HeroDevices() {
  const ref = useRef<HTMLDivElement>(null);

  function follow(e: PointerEvent<HTMLDivElement>) {
    if (e.pointerType !== "mouse" || !ref.current) return;
    const box = ref.current.getBoundingClientRect();
    ref.current.style.setProperty("--px", ((e.clientX - box.left) / box.width - 0.5).toFixed(3));
    ref.current.style.setProperty("--py", ((e.clientY - box.top) / box.height - 0.5).toFixed(3));
  }

  function rest() {
    ref.current?.style.setProperty("--px", "0");
    ref.current?.style.setProperty("--py", "0");
  }

  return (
    <div ref={ref} className={s.devices} onPointerMove={follow} onPointerLeave={rest}>
      <figure className={s.mac}>
        <div className={s.macBar} aria-hidden="true">
          <i />
          <i />
          <i />
          <span>ssample.duckdns.org</span>
        </div>
        <Image
          src="/landing/v2/hero-pc.webp"
          alt="쌤플 홈 화면. 오늘 날짜 아래 「지금, 한 줄」 입력 칸과 오늘 적은 기록, 오른쪽 칠판에 이번 주 기록 안 된 아이가 보인다."
          width={2400}
          height={1500}
          sizes="(max-width: 860px) 100vw, 880px"
          priority
        />
      </figure>
      <figure className={s.phone}>
        <Image
          src="/landing/v2/hero-phone.webp"
          alt="휴대폰에서 연 쌤플 홈 화면"
          width={780}
          height={1688}
          sizes="230px"
          priority
        />
      </figure>
    </div>
  );
}
