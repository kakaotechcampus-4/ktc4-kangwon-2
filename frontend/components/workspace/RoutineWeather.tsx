"use client";

import { useState } from "react";
import type { DayWeather, DustGrade, Sky } from "@/lib/api/routines";
import css from "./RoutineDay.module.css";

const SKIES: Sky[] = ["맑음", "구름많음", "흐림", "비", "눈", "비나 눈"];

/**
 * 날짜 옆 날씨 · 미세먼지 (ADR-081 화면, PM 시안 「날씨」).
 *
 * 날씨는 아이콘 하나 — 마우스를 올리면 글자가 뜬다. 값이 없으면 점선 빈 동그라미.
 * 누르면 여섯 + 「자동으로」가 펼쳐지고, 고르면 접힌다. 교사가 고른 값이 자동 값을 이긴다.
 * 미세먼지는 얼굴 표정과 에어코리아 색, 얼굴 아래 손글씨로 아주 작게 등급. 고르지 않는다.
 */
export default function RoutineWeather({
  weather,
  disabled,
  onChoose,
}: {
  weather: DayWeather | null;
  disabled: boolean;
  onChoose: (sky: Sky | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const sky = weather?.sky ?? null;
  const choose = (next: Sky | null) => {
    setOpen(false);
    onChoose(next);
  };
  return (
    <span className={css.weather}>
      <button
        type="button"
        className={css.weatherButton}
        aria-label={sky ? `날씨 ${sky} — 바꾸기` : "날씨 고르기"}
        aria-expanded={open}
        title={sky ?? "날씨 고르기"}
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
      >
        {sky ? <SkyIcon sky={sky} /> : <span className={css.weatherNone} aria-hidden="true" />}
      </button>
      {weather?.dust && <DustFace grade={weather.dust} />}
      {open && (
        <span className={css.weatherPicker} role="group" aria-label="날씨 고르기">
          {SKIES.map((value) => (
            <button
              key={value}
              type="button"
              className={css.weatherButton}
              aria-label={value}
              aria-pressed={weather?.source === "teacher" && sky === value}
              title={value}
              onClick={() => choose(value)}
            >
              <SkyIcon sky={value} />
            </button>
          ))}
          <button type="button" className={css.weatherAuto} onClick={() => choose(null)}>
            자동으로
          </button>
        </span>
      )}
    </span>
  );
}

const FACE: Record<DustGrade, string> = {
  좋음: "M8.5 15.5c2 2 5 2 7 0",
  보통: "M8.5 15.5h7",
  나쁨: "M8.5 16.5c2-2 5-2 7 0",
  매우나쁨: "M8 17.5c2.2-3 5.8-3 8 0",
};

function DustFace({ grade }: { grade: DustGrade }) {
  return (
    <span className={css.dust} data-grade={grade} title={`미세먼지 ${grade}`}>
      <svg
        viewBox="0 0 24 24"
        aria-hidden="true"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
      >
        <circle cx="12" cy="12" r="9.5" />
        <circle cx="9" cy="10" r="0.9" fill="currentColor" />
        <circle cx="15" cy="10" r="0.9" fill="currentColor" />
        <path d={FACE[grade]} strokeLinecap="round" />
      </svg>
      <span className={css.dustWord} aria-label={`미세먼지 ${grade}`}>
        {grade}
      </span>
    </span>
  );
}

/** 하늘 여섯 가지. 손으로 그은 선처럼 둥근 끝, 색 없이 글자색을 따른다. */
function SkyIcon({ sky }: { sky: Sky }) {
  const cloud = "M7 18h10a4 4 0 0 0 .4-8 5.5 5.5 0 0 0-10.6 1.2A3.4 3.4 0 0 0 7 18Z";
  const rain = "M9 20.5l-.8 1.6M13 20.5l-.8 1.6M17 20.5l-.8 1.6";
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {sky === "맑음" && (
        <>
          <circle cx="12" cy="12" r="4" />
          <path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4" />
        </>
      )}
      {sky === "구름많음" && (
        <>
          <path d="M8 7.5a3.5 3.5 0 0 1 6.2-1.6M6 4.5l.8.8M10 2.5v1.2" />
          <path d={cloud} />
        </>
      )}
      {sky !== "맑음" && sky !== "구름많음" && <path d={cloud} transform="translate(0 -2)" />}
      {sky === "비" && <path d={rain} transform="translate(0 -1.5)" />}
      {sky === "눈" && <path d="M9 20.5h.01M13 21.5h.01M17 20.5h.01" strokeWidth="2.6" />}
      {sky === "비나 눈" && (
        <>
          <path d="M9 19l-.8 1.6M17 19l-.8 1.6" />
          <path d="M13 21h.01" strokeWidth="2.6" />
        </>
      )}
    </svg>
  );
}
