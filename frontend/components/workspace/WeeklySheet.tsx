"use client";

/**
 * 주간 문서 용지 — 요일 양식(weekly_v1_mon_fri · mon_sat hwpx)과 같은 줄 순서.
 * 예상 기간 · 놀이 주제 · 소주제 · 이번 주 목표 · [이번 주 놀이] 실내자유놀이 ·
 * [대·소집단활동] 요일별 칸 · 바깥놀이 · 실내 대체놀이 · 기본생활습관 · 안전교육 ·
 * [특별활동 시간표] 요일별 칸 · 행사 · 가정 연계. 양식에 없는 칸은 맨 아래에 그대로 그린다.
 */

import type { DragEvent, MouseEvent, ReactNode } from "react";
import type { WeeklyActivityGrid, WeeklyCell, WeeklyPlan } from "@/lib/api/types";
import { DAY_NAMES, sectionName } from "@/lib/weekly/section-labels";
import { DROP } from "@/components/plan-generator/PlayMonthlySafetyPanel";
import {
  Cell,
  HATCH,
  hu,
  Paper,
  TEACHER_HINT,
  period,
  type Pick,
} from "@/components/plan-generator/PlayMonthlySheet";

type Section = WeeklyPlan["sections"][number];

/** 「AI 후보」 활동 카드를 끌 때 넘기는 글의 앞부분 — 뒤는 후보 item_id. 대·소집단활동 요일 칸이 받는다. */
export const WEEKLY_ACTIVITY_DRAG = "weekly-activity:";

const ORDER = [
  "theme",
  "focus",
  "goals",
  "indoor_play",
  "group_activity",
  "outdoor_play",
  "indoor_alternative",
  "basic_habit",
  "safety_education",
  "special_program",
  "event_schedule",
  "family_link",
];
const BAND: Record<string, string> = {
  indoor_play: "이번 주 놀이",
  group_activity: "대·소집단활동",
  special_program: "특별활동 시간표",
};
/** 양식의 표 덩어리 — 덩어리 사이를 띄운다. 모르는 칸은 마지막 덩어리에. */
const BLOCK: Record<string, number> = {
  theme: 0,
  focus: 0,
  goals: 0,
  indoor_play: 1,
  group_activity: 2,
  outdoor_play: 2,
  indoor_alternative: 2,
  basic_habit: 2,
  safety_education: 2,
  special_program: 3,
};
// 한글 양식(weekly_v1_mon_fri · mon_sat)의 색: 선 #BDE9FD, 이름 칸 #E1F2FE, 띠는 빗금, 요일 줄 살구색.
const LINE = "border border-[#bde9fd]";
const HEAD = "bg-[#e1f2fe] font-bold text-[#2b2826]";
const DAY = "bg-[#ffe0cc] font-bold text-[#2b2826]";

/** 한글 양식(weekly_v1_mon_fri · mon_sat) 줄 높이(HWPUNIT). 요일 칸은 「활동」 줄. 모르는 칸은 가정 연계 높이. */
const ROW_HU: Record<string, number> = {
  theme: 2000,
  focus: 2000,
  goals: 3800,
  indoor_play: 11000,
  group_activity: 8000,
  outdoor_play: 3900,
  indoor_alternative: 3900,
  basic_habit: 3000,
  safety_education: 3400,
  special_program: 4500,
  event_schedule: 2700,
  family_link: 3500,
};
const rowH = (key: string) => ({ height: hu(ROW_HU[key] ?? 3500) });
/** 양식 줄 이름이 화면 이름과 다른 칸. */
const ROW: Record<string, string> = { goals: "이번 주 목표", indoor_alternative: "실내 대체놀이" };

/** 양식 순서로 세운 보이는 칸. 모르는 칸은 서버 순서대로 뒤에. */
export function sheetSections(sections: Section[]) {
  const rank = (s: Section) => {
    const i = ORDER.indexOf(s.section_key);
    return i < 0 ? ORDER.length + s.order : i;
  };
  return sections.filter((s) => s.visible).sort((a, b) => rank(a) - rank(b));
}

/** 만들기 화면 미리보기용 빈 양식. */
export const BLANK_SECTIONS: Section[] = ORDER.map((key, order) => {
  const day = key === "group_activity" || key === "special_program";
  return {
    section_key: key,
    label: null,
    role: "CONTENT",
    visible: true,
    order,
    semantic_variant: null,
    repeat_by: day ? "DAY" : "NONE",
    cells: [],
  };
});

export default function WeeklySheet({
  title,
  sub,
  start,
  end,
  days,
  sections,
  grids,
  at,
  shown = (cell) => cell.value,
  scale,
  onPut,
}: {
  title: string;
  sub: string;
  start: string;
  end: string;
  days: string[];
  sections: Section[];
  grids?: WeeklyActivityGrid[];
  at: Pick;
  shown?: (cell: WeeklyCell) => string;
  scale?: number;
  /** 활동 후보 카드를 대·소집단활동 칸에 놓았을 때(칸 id, 후보 id). 없으면(확정 · 저장 중) 받지 않는다. */
  onPut?: (cellId: string, candidateItemId: string) => void;
}) {
  const span = days.length;
  // 안전교육은 「[주제] 문장」 한 줄에 [주제]를 굵게, 넣은 활동은 「[종류]」 밑에 이름(PM 2026-11-06).
  // 안전교육 · 실내놀이의 옛 값(11-06 전) 「[주제] - 」는 「 - 」를 떼고 보인다.
  const cellOf = (cell: WeeklyCell, key = "") => (
    <Cell
      {...at}
      id={cell.item_id}
      value={
        key === "safety_education" || key === "indoor_play"
          ? shown(cell).replace(/^(\[[^\]\n]+\]) - /, "$1 ")
          : key === "group_activity"
            ? shown(cell).replace(/^(\[[^\]\n]+\]) /, "$1\n")
            : shown(cell)
      }
      strong={key === "safety_education"}
      hint={cell.teacher_input ? TEACHER_HINT : undefined}
    />
  );
  // 후보 카드를 놓은 곳의 칸(나눈 칸이면 그 조각, 아니면 그날 칸 하나)에 넣는다.
  const dropOn = (only: string | null) =>
    onPut
      ? {
          onDragOver: (e: DragEvent<HTMLElement>) => {
            e.preventDefault();
            e.currentTarget.dataset.drop = "";
          },
          onDragLeave: (e: DragEvent<HTMLElement>) => delete e.currentTarget.dataset.drop,
          onDrop: (e: DragEvent<HTMLElement>) => {
            e.preventDefault();
            delete e.currentTarget.dataset.drop;
            const data = e.dataTransfer.getData("text/plain");
            const hit = (e.target as HTMLElement).closest<HTMLElement>("[data-cell],[data-area]");
            const cellId = hit?.dataset.cell ?? hit?.dataset.area ?? only;
            if (data.startsWith(WEEKLY_ACTIVITY_DRAG) && cellId)
              onPut(cellId, data.slice(WEEKLY_ACTIVITY_DRAG.length));
          },
        }
      : {};
  // 칸 둘레의 빈 곳을 눌러도 그 칸을 고른다(칸 하나짜리 표 칸 · 나눈 칸). 글 위 클릭은 Cell 이 받는다.
  const area = (id: string | null | undefined) =>
    at.onSelect && id
      ? {
          onClick: (e: MouseEvent<HTMLElement>) => {
            if (e.target === e.currentTarget) at.onSelect!(id);
          },
          "data-area": id,
        }
      : {};
  const grid = (node: WeeklyActivityGrid, cells: WeeklyCell[]): ReactNode => {
    if (node.cell_id) {
      const cell = cells.find((c) => c.item_id === node.cell_id);
      return cell ? cellOf(cell, "group_activity") : null;
    }
    const vertical = node.axis === "VERTICAL";
    const ratio = node.ratio ?? 50;
    return (
      <div className={`flex h-full ${vertical ? "flex-col" : "flex-row"}`}>
        {node.children.map((child, i) => (
          <div
            key={child.cell_id ?? child.split_id ?? i}
            style={{ flex: i === 0 ? ratio : 100 - ratio, minWidth: 0 }}
            className={`flex flex-col [&>[data-cell]]:flex [&>[data-cell]]:flex-1 [&>[data-cell]]:flex-col [&>[data-cell]]:justify-center ${
              i ? (vertical ? "border-t border-[#cfe5f4]" : "border-l border-[#cfe5f4]") : ""
            }`}
            {...area(child.cell_id)}
          >
            {grid(child, cells)}
          </div>
        ))}
      </div>
    );
  };
  const blocks: ReactNode[][] = [[], [], [], [], []];
  blocks[0].push(
    <tr key="period">
      <th scope="row" className={`${LINE} ${HEAD} px-1 py-[2px]`} style={{ height: hu(1800) }}>
        예상 기간
      </th>
      <td colSpan={span} className={`${LINE} px-1.5 py-1`}>
        {start && period([{ start_date: start, end_date: end }])}
      </td>
    </tr>,
  );
  sheetSections(sections).forEach((section) => {
    const key = section.section_key;
    const out = blocks[BLOCK[key] ?? 4];
    if (BAND[key])
      out.push(
        <tr key={"band:" + key}>
          <th
            colSpan={span + 1}
            scope="colgroup"
            className={`${LINE} ${HATCH} text-[13px] font-bold`}
            style={{ height: hu(key === "indoor_play" ? 1400 : 1650) }}
          >
            [ {BAND[key]} ]
          </th>
        </tr>,
      );
    if (section.repeat_by === "DAY") {
      const tree = key === "group_activity" && grids?.length === span ? grids : null;
      out.push(
        <tr key={"days:" + key}>
          <th scope="col" className={`${LINE} ${HEAD}`} style={{ height: hu(1800) }}>
            요일
          </th>
          {days.map((d) => (
            <th key={d} scope="col" className={`${LINE} ${DAY}`}>
              {DAY_NAMES[d] ?? d}
            </th>
          ))}
        </tr>,
        <tr key={key}>
          <th scope="row" className={`${LINE} ${HEAD} px-1 py-[2px]`} style={rowH(key)}>
            {key === "group_activity" || key === "special_program"
              ? "활동"
              : sectionName(key, section.label)}
          </th>
          {days.map((d, i) => {
            const cells = section.cells.filter((c) => c.day === d);
            const one = tree ? tree[i].cell_id : cells.length === 1 ? cells[0].item_id : null;
            return (
              <td
                key={d}
                className={`${LINE} align-middle transition-colors ${DROP} ${key === "group_activity" ? "text-center" : ""}`}
                {...area(one)}
                {...(key === "group_activity" ? dropOn(one ?? null) : {})}
              >
                {tree
                  ? grid(tree[i], cells)
                  : cells.map((c) => <div key={c.item_id}>{cellOf(c, key)}</div>)}
              </td>
            );
          })}
        </tr>,
      );
    } else
      out.push(
        <tr key={key}>
          <th scope="row" className={`${LINE} ${HEAD} px-1 py-[2px]`} style={rowH(key)}>
            {ROW[key] ?? sectionName(key, section.label)}
          </th>
          <td
            colSpan={span}
            className={`${LINE} align-middle ${key === "goals" ? "[&_[data-cell]]:justify-start" : ""}`}
            {...area(section.cells.length === 1 ? section.cells[0].item_id : null)}
          >
            {/* 후보형 실내 자유놀이는 주 전체 목록이 한 칸에 순서대로 들어간다. 나머지는 한 칸. */}
            {section.cells.map((c) => (
              <div key={c.item_id}>{cellOf(c, key)}</div>
            ))}
          </td>
        </tr>,
      );
  });
  return (
    <Paper label="주간계획안 미리보기" title={title} sub={sub} scale={scale} head={4800}>
      {blocks
        .filter((rows) => rows.length)
        .map((rows, i) => (
          <table key={i} className="mt-[5px] w-full table-fixed border-collapse">
            <colgroup>
              <col style={{ width: "16.67%" }} />
              {days.map((d) => (
                <col key={d} />
              ))}
            </colgroup>
            <tbody>{rows}</tbody>
          </table>
        ))}
    </Paper>
  );
}
