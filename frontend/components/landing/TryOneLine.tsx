"use client";

import { useState } from "react";
import s from "./Welcome.module.css";

/**
 * 「직접 한 줄」 — 방문자가 적은 문장이 일지의 사실 칸에 **그대로** 들어가는 것을 보여 준다.
 *
 * 쌤플의 약속(사실은 교사의 것, AI 는 그 위에 초안만)을 말 대신 손으로 겪게 하는 자리다.
 * 아래 두 줄은 영역마다 정해 둔 **예시 초안**이다 — 서버도 AI 도 부르지 않고,
 * 적은 글은 이 화면 밖으로 나가지 않는다. 화면에도 「예시」라고 밝힌다.
 */

const AREAS = [
  {
    name: "신체운동·건강",
    play: "몸을 움직여 스스로 방법을 찾아보는 모습이 나타났다.",
    next: "바깥놀이 시간에 같은 움직임을 다시 해 볼 수 있도록 공간을 마련한다.",
  },
  {
    name: "의사소통",
    play: "자신의 생각을 말로 표현하고 친구의 말에 귀 기울이는 모습을 보였다.",
    next: "그림책과 이야기 나누기로 말한 내용을 이어 가도록 지원한다.",
  },
  {
    name: "사회관계",
    play: "친구와 함께 놀이하며 차례와 양보를 경험하는 모습을 보였다.",
    next: "함께 해결하는 놀이를 이어 갈 수 있도록 모둠 자리를 마련한다.",
  },
  {
    name: "예술경험",
    play: "색과 소리, 움직임을 자기 방식으로 표현해 보는 모습이 나타났다.",
    next: "다양한 재료를 더 준비해 표현을 넓혀 갈 수 있도록 한다.",
  },
  {
    name: "자연탐구",
    play: "주변 사물과 자연을 살펴보며 차이를 비교하고 탐색하는 모습을 보였다.",
    next: "같은 재료로 다른 방법을 시도해 볼 수 있도록 준비한다.",
  },
];

const START = "바깥놀이에서 도토리를 크기별로 줄 세웠다. 친구가 와서 같이 세웠다.";

export function TryOneLine() {
  const [text, setText] = useState(START);
  const [areaIndex, setAreaIndex] = useState(4);
  const area = AREAS[areaIndex];
  const fact = text.trim();

  return (
    <div className={s.try}>
      <form className={s.tryCard} onSubmit={(e) => e.preventDefault()}>
        <label htmlFor="try-line" className={s.tryLabel}>
          지금, 한 줄
        </label>
        <textarea
          id="try-line"
          className={s.tryInput}
          value={text}
          maxLength={200}
          rows={3}
          onChange={(e) => setText(e.target.value)}
          placeholder="오늘 본 장면을 본 대로 적어 보세요"
        />
        <fieldset className={s.tryAreas}>
          <legend>영역</legend>
          {AREAS.map((a, i) => (
            <label key={a.name} className={i === areaIndex ? s.tryAreaOn : undefined}>
              <input
                type="radio"
                name="try-area"
                checked={i === areaIndex}
                onChange={() => setAreaIndex(i)}
              />
              {a.name}
            </label>
          ))}
        </fieldset>
        <p className={s.tryNote}>이 칸에 적은 글은 어디로도 보내지 않아요.</p>
      </form>

      <figure className={s.tryDoc} aria-label="일일 보육일지 미리보기">
        <figcaption>일일 보육일지 · 미리보기</figcaption>
        <div className={`${s.tryRow} ${s.tryFact}`}>
          <b>사실</b>
          <span>
            <em className={s.tryTag}>선생님이 적은 그대로 · 잠금</em>
            {fact || <i className={s.tryEmpty}>적은 문장이 여기에 그대로 들어가요</i>}
          </span>
        </div>
        <div className={s.tryRow} key={`play-${areaIndex}`}>
          <b>놀이 모습</b>
          <span>
            <em className={s.tryTag}>예시 초안 · {area.name}</em>
            {area.play}
          </span>
        </div>
        <div className={s.tryRow} key={`next-${areaIndex}`}>
          <b>내일 이어갈 것</b>
          <span>
            <em className={s.tryTag}>예시 초안</em>
            {area.next}
          </span>
        </div>
      </figure>
    </div>
  );
}
