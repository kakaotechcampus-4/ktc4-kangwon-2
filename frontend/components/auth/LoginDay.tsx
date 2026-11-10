"use client";
import { useEffect, useRef } from "react";
import DayViews from "@/components/landing/DayViews";
import { MARKS, OBS, SCENES } from "@/components/landing/day-scenes";
import "@/components/landing/landing.css";
import s from "./LoginDay.module.css";

export type DayScene = (typeof SCENES)[number];

const SCENE_MS = 8000;
/** 하루가 시작된 시각. 로그인 ↔ 가입은 틀을 새로 그리므로, 여기 둬야 08:50 으로 돌아가지 않고 장면이 이어진다 */
let startedAt: number | null = null;

/**
 * 로그인 · 가입 화면 왼쪽의 하루 장면. 소개 화면(/welcome) 「하루」 장면의 내용과 바뀌는 순서를 그대로 쓰고,
 * 스크롤 대신 시간(장면마다 8초)으로 넘긴다. 시안은 「로그인 하루 장면 시안」 15번(화면 전체가 하루)이고,
 * 기록 창만 12번(겹쳐 쌓인 장면)으로 바꿨다 — 미니 판은 없다.
 *
 * 글자 · 표시는 소개 화면 엔진(landing-engine.js)처럼 바뀌는 칸만 직접 고친다 — 매 프레임 React 를 다시 그리지 않는다.
 * 바탕색은 화면 전체에 깔리므로 장면이 바뀔 때만 `onScene` 으로 틀(AuthFrame)에 알린다.
 * 「움직임 줄이기」면 첫 장면을 다 그린 채로 세워 두고, 시간을 눌렀을 때만 바꾼다.
 */
export default function LoginDay({ onScene }: { onScene: (scene: DayScene) => void }) {
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!root.current) return;
    const day: HTMLDivElement = root.current;
    const q = (sel: string) => day.querySelector(sel) as HTMLElement;
    const all = (sel: string) => [...day.querySelectorAll<HTMLElement>(sel)];
    const digits = all(".digit > span");
    const ampm = q(".ampm"),
      scene = q(".scene"),
      typed = q(".typed"),
      rest = q(".rest"),
      dot = q(".track i"),
      marksBox = q(".marks");
    const views = all(".view"),
      marks = all(".marks button");
    const winTitle = q("#winTitle"),
      obsLine = q("#obsLine"),
      slips = all("#chalk .slip"),
      gen1 = q("#gen1"),
      gen2 = q("#gen2"),
      stamp = q("#stamp"),
      weekDays = all("#week div"),
      ojPicks = all("#ojPicks span"),
      oj1 = q("#oj1"),
      oj2 = q("#oj2");
    const clamp = (v: number, a: number, b: number) => Math.min(b, Math.max(a, v));
    let still = matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : -1;
    startedAt ??= performance.now();
    let sIdx = -1,
      lastN = -1,
      lastA = -1,
      raf = 0;

    function setScene(i: number) {
      if (i === sIdx) return;
      sIdx = i;
      lastN = lastA = -1;
      const sc = SCENES[i];
      [...sc.t].forEach((c, j) => {
        digits[j].style.transform = `translateY(${-Number(c)}em)`;
      });
      ampm.textContent = sc.ampm;
      scene.innerHTML = `${sc.scene}<small>${sc.sub}</small>`;
      day.classList.toggle("night", sc.night);
      dot.style.setProperty("--tp", `${(i / (SCENES.length - 1)) * 100}%`);
      views.forEach((v) => v.classList.toggle("on", Number(v.dataset.view) === i));
      winTitle.textContent = sc.title;
      marks.forEach((m, j) => m.classList.toggle("on", j === i));
      onScene(sc);
    }

    // 소개 화면 sceneProgress 와 같은 비율 — 생각 한 줄은 장면 55% 에서 다 적히고, 창은 20% ~ 82% 사이에 채워진다
    function sceneProgress(i: number, lp: number) {
      const quote = SCENES[i].quote;
      const n = Math.round(clamp(lp * 1.8, 0, 1) * quote.length);
      if (n !== lastN) {
        lastN = n;
        typed.textContent = quote.slice(0, n);
        rest.textContent = quote.slice(n);
      }
      const a = clamp((lp - 0.2) * 1.6, 0, 1);
      if (a === lastA) return;
      lastA = a;
      if (i === 0) obsLine.textContent = OBS.slice(0, Math.round(a * OBS.length));
      if (i === 1) slips.forEach((sl, j) => sl.classList.toggle("in", a > j / slips.length));
      if (i === 2) {
        gen1.classList.toggle("in", a > 0.3);
        gen2.classList.toggle("in", a > 0.7);
      }
      if (i === 3) {
        ojPicks.forEach((pk, j) => pk.classList.toggle("in", a > j * 0.12));
        oj1.classList.toggle("in", a > 0.45);
        oj2.classList.toggle("in", a > 0.75);
      }
      if (i === 4) stamp.classList.toggle("in", a > 0.35);
      if (i === 5)
        weekDays.forEach((d, j) => {
          const on = a > j / weekDays.length;
          d.classList.toggle("fill", on);
          const em = d.querySelector("em");
          if (em) em.textContent = on ? `일과 6, 관찰 ${[2, 2, 2, 1, 2][j]}` : "기록 전";
        });
    }

    function draw() {
      const t =
        still >= 0
          ? still + 0.999
          : ((performance.now() - (startedAt ?? 0)) / SCENE_MS) % SCENES.length;
      const i = Math.floor(t);
      setScene(i);
      sceneProgress(i, t - i);
      if (still < 0) raf = requestAnimationFrame(draw);
    }

    const jump = (e: MouseEvent) => {
      const b = (e.target as HTMLElement).closest("button");
      if (!b) return;
      const i = Number(b.dataset.i);
      if (still >= 0) {
        still = i;
        draw();
      } else startedAt = performance.now() - i * SCENE_MS;
    };
    marksBox.addEventListener("click", jump);
    draw();
    return () => {
      cancelAnimationFrame(raf);
      marksBox.removeEventListener("click", jump);
    };
  }, [onScene]);

  return (
    <div className={`lp ${s.wrap}`}>
      <div ref={root} className={`day ${s.day}`}>
        <div className={`clock ${s.clock}`} aria-hidden="true">
          <Digit />
          <Digit />
          <span className="colon">:</span>
          <Digit />
          <Digit />
          <span className="ampm" />
        </div>
        <p className={`scene ${s.scene}`} aria-hidden="true" />
        <div className={s.time}>
          <div className="track" aria-hidden="true">
            <i />
          </div>
          <div className="marks">
            {MARKS.map((m, i) => (
              <button key={m} type="button" data-i={i} aria-label={`${m} 장면으로 이동`}>
                {m}
              </button>
            ))}
          </div>
        </div>
        <p className={`quote ${s.quote}`} aria-hidden="true">
          <span className="typed" />
          <span className="caret" />
          <span className="rest" />
        </p>
        <div className={s.win} aria-hidden="true">
          <div className="window">
            <div className="win-bar">
              <i />
              <i />
              <i />
              <span id="winTitle" />
            </div>
            <div className="win-body">
              <DayViews />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/** 시계 숫자 한 자리 — 0~9 를 세로로 쌓아 두고 위아래로 굴린다 */
function Digit() {
  return (
    <span className="digit">
      <span>
        {Array.from({ length: 10 }, (_, n) => (
          <b key={n}>{n}</b>
        ))}
      </span>
    </span>
  );
}
