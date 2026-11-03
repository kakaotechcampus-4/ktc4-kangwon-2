"use client";

/**
 * 주간 문서 용지 — 요일 양식(weekly_v1_mon_fri · mon_sat hwpx)과 같은 줄 순서.
 * 예상 기간 · 놀이 주제 · 소주제 · 이번 주 목표 · [이번 주 놀이] 실내자유놀이 ·
 * [대·소집단활동] 요일별 칸 · 바깥놀이 · 실내 대체놀이 · 기본생활습관 · 안전교육 ·
 * [특별활동 시간표] 요일별 칸 · 행사 · 가정 연계. 양식에 없는 칸은 맨 아래에 그대로 그린다.
 */

import type { MouseEvent, ReactNode } from "react";
import type { WeeklyActivityGrid, WeeklyCell, WeeklyPlan } from "@/lib/api/types";
import { DAY_NAMES, sectionName } from "@/lib/weekly/section-labels";
import {
  Cell,
  Paper,
  TEACHER_HINT,
  period,
  type Pick,
} from "@/components/plan-generator/PlayMonthlySheet";

type Section = WeeklyPlan["sections"][number];

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
const HATCH =
  "[background:repeating-linear-gradient(90deg,#c1f3fd_0_1px,transparent_1px_4px),#e1f2fe]";

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
}) {
  const span = days.length;
  const cellOf = (cell: WeeklyCell) => (
    <Cell
      {...at}
      id={cell.item_id}
      value={shown(cell)}
      hint={cell.teacher_input ? TEACHER_HINT : undefined}
    />
  );
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
      return cell ? cellOf(cell) : null;
    }
    const vertical = node.axis === "VERTICAL";
    const ratio = node.ratio ?? 50;
    return (
      <div className={`flex h-full ${vertical ? "flex-col" : "flex-row"}`}>
        {node.children.map((child, i) => (
          <div
            key={child.cell_id ?? child.split_id ?? i}
            style={{ flex: i === 0 ? ratio : 100 - ratio, minWidth: 0 }}
            className={`flex flex-col [&>[data-cell]]:flex-1 ${
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
      <th scope="row" className={`${LINE} ${HEAD} px-1 py-1.5`}>
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
            className={`${LINE} ${HATCH} py-1 text-[12px] font-bold`}
          >
            [ {BAND[key]} ]
          </th>
        </tr>,
      );
    if (section.repeat_by === "DAY") {
      const tree = key === "group_activity" && grids?.length === span ? grids : null;
      out.push(
        <tr key={"days:" + key}>
          <th scope="col" className={`${LINE} ${HEAD} py-0.5`}>
            요일
          </th>
          {days.map((d) => (
            <th key={d} scope="col" className={`${LINE} ${DAY} py-0.5`}>
              {DAY_NAMES[d] ?? d}
            </th>
          ))}
        </tr>,
        <tr key={key}>
          <th scope="row" className={`${LINE} ${HEAD} px-1 py-1.5`}>
            {key === "group_activity" || key === "special_program"
              ? "활동"
              : sectionName(key, section.label)}
          </th>
          {days.map((d, i) => {
            const cells = section.cells.filter((c) => c.day === d);
            return (
              <td
                key={d}
                className={`${LINE} h-[72px] align-top`}
                {...area(tree ? tree[i].cell_id : cells.length === 1 ? cells[0].item_id : null)}
              >
                {tree
                  ? grid(tree[i], cells)
                  : cells.map((c) => <div key={c.item_id}>{cellOf(c)}</div>)}
              </td>
            );
          })}
        </tr>,
      );
    } else
      out.push(
        <tr key={key}>
          <th scope="row" className={`${LINE} ${HEAD} px-1 py-1.5`}>
            {ROW[key] ?? sectionName(key, section.label)}
          </th>
          <td
            colSpan={span}
            className={`${LINE} align-top`}
            {...area(section.cells.length === 1 ? section.cells[0].item_id : null)}
          >
            {/* 후보형 실내 자유놀이는 주 전체 목록이 한 칸에 순서대로 들어간다. 나머지는 한 칸. */}
            {section.cells.map((c) => (
              <div key={c.item_id}>{cellOf(c)}</div>
            ))}
          </td>
        </tr>,
      );
  });
  return (
    <Paper label="주간계획안 미리보기" title={title} sub={sub} scale={scale}>
      {blocks
        .filter((rows) => rows.length)
        .map((rows, i) => (
          <table key={i} className="mt-2.5 w-full table-fixed border-collapse">
            <colgroup>
              <col style={{ width: "15%" }} />
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
