"use client";

import { useSyncExternalStore, type ComponentType } from "react";
import {
  Drawer,
  Elevator,
  Exploded,
  Hub,
  Padlock,
  Riffle,
  type HairlineProps,
} from "@lucasmarkes/hairline/react";
import s from "./Welcome.module.css";

/**
 * 소개 화면 가운데의 「그림」 여섯 장. 선으로 그린 등각 그림이 포인터에 답한다(hairline).
 *
 * 그림마다 쌤플이 기록을 다루는 방식 하나를 맡는다. 판 위에는 제목과 해 볼 일만 적는다 —
 * 그림이 내는 영어 읽은 값(「gap 12.0」)과 그림 번호는 교실 말이 아니라 싣지 않는다.
 * 손가락으로만 쓰는 기기는 가리킬 수 없으니 그림이 스스로 한 바퀴씩 움직이게 한다.
 */

type Plate = {
  Figure: ComponentType<HairlineProps>;
  title: string;
  hint: string;
  label: string;
};

const PLATES: Plate[] = [
  {
    Figure: Riffle,
    title: "쌓이는 기록",
    hint: "한 장씩 일으켜 보기",
    label: "카드 여덟 장이 꽂힌 상자. 가리킨 카드가 일어선다. 하루하루 쌓이는 관찰 기록.",
  },
  {
    Figure: Exploded,
    title: "일지의 네 겹",
    hint: "옆으로 벌리고, 위아래로 고르기",
    label: "네 겹으로 벌어지는 창. 사실, 놀이 모습, 지원, 확정이 겹겹이 쌓인 일지.",
  },
  {
    Figure: Hub,
    title: "기록 하나, 문서 여럿",
    hint: "가리킨 칸이 이어져요",
    label: "가운데 하나와 둘레 여덟 칸. 기록 하나가 관찰일지, 보육일지, 계획, 평가로 이어진다.",
  },
  {
    Figure: Elevator,
    title: "연간에서 일일까지",
    hint: "높이로 층을 골라요",
    label: "네 층과 승강기. 연간, 월간, 주간, 일일 계획을 오간다.",
  },
  {
    Figure: Drawer,
    title: "반별 보관함",
    hint: "서랍을 골라 열기",
    label: "서랍 세 칸. 반과 날짜별로 모이는 문서 보관함.",
  },
  {
    Figure: Padlock,
    title: "이름은 잠가 두고",
    hint: "가까이 가면 열려요",
    label: "자물쇠. 아이 이름은 가명으로 바꿔 보내고, 돌아온 초안에서만 연다.",
  },
];

/** 가리킬 수 없는 기기(손가락만)인가. 서버에서는 「가리킬 수 있다」로 둔다. */
function useTouchOnly() {
  return useSyncExternalStore(
    (onChange) => {
      const q = window.matchMedia("(hover: none)");
      q.addEventListener("change", onChange);
      return () => q.removeEventListener("change", onChange);
    },
    () => window.matchMedia("(hover: none)").matches,
    () => false,
  );
}

export function FigurePlates() {
  const touchOnly = useTouchOnly();
  return (
    <ol className={s.plates}>
      {PLATES.map((p) => (
        <PlateCard key={p.title} plate={p} play={touchOnly} />
      ))}
    </ol>
  );
}

function PlateCard({ plate, play }: { plate: Plate; play: boolean }) {
  const { Figure } = plate;
  return (
    <li className={s.plate}>
      <span className={s.plateTitle}>{plate.title}</span>
      <Figure
        className={s.plateFigure}
        intensity={0.6}
        theme="light"
        label={plate.label}
        play={play}
      />
      <span className={s.plateHint}>{plate.hint}</span>
    </li>
  );
}
