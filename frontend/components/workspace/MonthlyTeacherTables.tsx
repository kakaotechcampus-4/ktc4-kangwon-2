/**
 * 월간 v1 교사 표 — 행사 일정 · 특성화 시간표 · 특별활동 시간표 (Human Decision 2026-11-05).
 * 칸 나눔 트리는 놀이 월간 특별활동 시간표(ADR-047)와 같은 모양이고 순수 함수도 같이 쓴다.
 * 놀이 월간 화면 부품(끌기 손잡이 · SlotTools)은 건드리지 않으려고 따로 둔다 — 크기는 단추로 바꾼다.
 */
import type { ReactNode } from "react";
import type { MonthlyTeacherTable, PlayMonthlyTimetablePart as Part } from "@/lib/api/types";
import {
  CELL_MIN_WIDTH,
  DAYS,
  MAX_DEPTH,
  RATIO_RANGE,
  leaves,
  locate,
  narrowest,
  splitLeaf,
  tooNarrow,
  withRatio,
} from "@/lib/plan-generator/playMonthlyTimetable";
import { Band, Cell, hu, LINE, TEACHER_HINT } from "@/components/plan-generator/PlayMonthlySheet";

type Pick = { selected: string | null; onSelect?: (id: string) => void };
type Axis = "VERTICAL" | "HORIZONTAL";
/** v1 양식 줄 높이가 놀이 월간보다 낮아 아래 한도가 10mm 다(서버 HEIGHT_MM_RANGE). */
export const TABLE_HEIGHT = [10, 80] as const;
const mm = (n: number) => hu(n * 283.465);
const HEAD = `${LINE} bg-[#e6f3fc] font-bold`;

/** 표의 모든 칸(열 제목 포함)과 그 표. */
export const tableCells = (tables: MonthlyTeacherTable[]) =>
  tables.flatMap((table) =>
    [...table.titles, ...table.columns.flatMap(leaves)].map((cell) => ({ table, cell })),
  );

/** 칸의 위치 이름(「특성화 시간표 · 2열 제목」). */
export function tablePlace(table: MonthlyTeacherTable, itemId: string) {
  const title = table.titles.findIndex((c) => c.item_id === itemId);
  if (title >= 0) return `${table.label} · ${title + 1}열 제목`;
  const found = locate(table.columns, itemId);
  if (!found || table.columns.length === 1) return table.label;
  return table.table_key === "special_activity_timetable"
    ? `${table.label} · ${DAYS[found.day]}요일`
    : `${table.label} · ${found.day + 1}열`;
}

export function TeacherTables({
  tables,
  at,
  shown,
}: {
  tables: MonthlyTeacherTable[];
  at: Pick;
  shown: (cell: { item_id: string; value: string }) => string;
}) {
  const tree = (part: Part): ReactNode => {
    if (part.cell)
      return (
        <div className="flex h-full min-h-0 min-w-0 overflow-auto [&>span]:h-full [&>span]:w-full [&>span]:text-center">
          <Cell {...at} hint={TEACHER_HINT} id={part.cell.item_id} value={shown(part.cell)} />
        </div>
      );
    const across = part.axis === "HORIZONTAL";
    return (
      <div
        className="grid h-full min-h-0 min-w-0"
        style={{
          [across ? "gridTemplateColumns" : "gridTemplateRows"]:
            `minmax(0,${part.ratio}fr) minmax(0,${100 - part.ratio!}fr)`,
        }}
      >
        {part.children.map((child, i) => (
          <div
            key={i}
            className={`min-h-0 min-w-0 ${i ? (across ? "border-l" : "border-t") + " border-[#a9d3ee]" : ""}`}
          >
            {tree(child)}
          </div>
        ))}
      </div>
    );
  };
  const body = (table: MonthlyTeacherTable) =>
    table.columns.map((column, i) => (
      <td key={i} className={`${LINE} p-0 align-top`}>
        <div style={{ height: mm(table.height_mm) }}>{tree(column)}</div>
      </td>
    ));
  return tables.map((table) =>
    table.table_key === "event_schedule" ? (
      <table key={table.table_key} className="mt-[10px] w-full table-fixed border-collapse">
        <colgroup>
          <col style={{ width: "16.67%" }} />
          <col />
        </colgroup>
        <tbody>
          <tr>
            <th scope="row" className={`${HEAD} px-1 py-[2px]`}>
              {table.label}
            </th>
            {body(table)}
          </tr>
        </tbody>
      </table>
    ) : (
      <div key={table.table_key} className="mt-[10px]">
        <Band>{table.label}</Band>
        <table className="w-full table-fixed border-collapse">
          <colgroup>
            {table.column_widths.map((w, i) => (
              <col key={i} style={{ width: `${w}%` }} />
            ))}
          </colgroup>
          <tbody>
            <tr>
              {table.columns.map((_, i) => (
                <th key={i} scope="col" className={`${HEAD} p-0`} style={{ height: hu(1650) }}>
                  {table.titles[i] ? (
                    <Cell
                      {...at}
                      hint={TEACHER_HINT}
                      id={table.titles[i].item_id}
                      value={shown(table.titles[i])}
                    />
                  ) : (
                    DAYS[i]
                  )}
                </th>
              ))}
            </tr>
            <tr>{body(table)}</tr>
          </tbody>
        </table>
      </div>
    ),
  );
}

const TOOL =
  "flex min-h-[36px] items-center gap-1.5 rounded-md px-2.5 text-[13px] font-semibold disabled:opacity-40";
const STEP =
  "flex h-9 w-9 items-center justify-center rounded-md text-[18px] font-bold text-[#5e4b96] hover:bg-[#f6f1fb] disabled:opacity-40";

/**
 * 표 칸 도구 — 위아래 · 좌우로 나누기, 이 칸 빼기, 나뉜 칸이면 그 칸 크기, 표 높이.
 * 열 제목은 나누지 않는다. 한도(깊이 4 · 비율 10~90 · 칸 3.5%)는 미리 끄고 최종 검사는 서버가 한다.
 */
export function TableTools({
  table,
  itemId,
  disabled,
  onSplit,
  onRemove,
  onRatio,
  onHeight,
}: {
  table: MonthlyTeacherTable;
  itemId: string;
  disabled: boolean;
  onSplit: (axis: Axis) => void;
  onRemove: () => void;
  onRatio: (splitId: string, ratio: number) => void;
  onHeight: (heightMm: number) => void;
}) {
  const slot = locate(table.columns, itemId);
  if (!slot) return null;
  const column = table.columns[slot.day];
  const width = table.column_widths[slot.day];
  const cramped = (axis: Axis) =>
    axis === "HORIZONTAL" &&
    narrowest(splitLeaf(column, itemId, axis, "", slot.path.at(-1)!.cell!), width) < CELL_MIN_WIDTH;
  const parent = slot.path.at(-2);
  const first = parent?.children[0] === slot.path.at(-1);
  const ratio = parent?.ratio ?? 50;
  const what = parent?.axis === "VERTICAL" ? "높이" : "너비";
  const next = (delta: number) => (first ? ratio + delta : ratio - delta);
  const fits = (r: number) =>
    r >= RATIO_RANGE[0] &&
    r <= RATIO_RANGE[1] &&
    !tooNarrow(
      table.columns.map((c, i) => (i === slot.day ? withRatio(c, parent!.split_id!, r) : c)),
      table.column_widths,
    );
  const height = (delta: number) => table.height_mm + delta;
  const step = (label: string, sign: number, ok: boolean, run: () => void) => (
    <button
      type="button"
      aria-label={label}
      className={STEP}
      disabled={disabled || !ok}
      onClick={run}
    >
      {sign < 0 ? "−" : "+"}
    </button>
  );
  const stepper = (name: string, value: string, minus: ReactNode, plus: ReactNode) => (
    <div role="group" aria-label={name} className="flex items-center gap-3">
      <span className="text-sm text-[#5c5243]">{name}</span>
      <div className="inline-flex items-center rounded-lg border border-[#ddd6ca] bg-white p-0.5">
        {minus}
        <span className="min-w-[3.5em] text-center text-sm font-bold tabular-nums">{value}</span>
        {plus}
      </div>
    </div>
  );
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <div
          role="group"
          aria-label="칸 나누기"
          className="inline-flex rounded-lg border border-[#ddd6ca] bg-white p-0.5"
        >
          {(["VERTICAL", "HORIZONTAL"] as const).map((axis) => (
            <button
              key={axis}
              type="button"
              className={`${TOOL} text-[#5e4b96] hover:bg-[#f6f1fb]`}
              disabled={disabled || slot.path.length - 1 >= MAX_DEPTH || cramped(axis)}
              onClick={() => onSplit(axis)}
            >
              {axis === "VERTICAL" ? "위아래로 나누기" : "좌우로 나누기"}
            </button>
          ))}
        </div>
        <button
          type="button"
          className={`${TOOL} text-[#a2492f] hover:bg-[#fbf0ec]`}
          disabled={disabled || !parent}
          onClick={onRemove}
        >
          이 칸 빼기
        </button>
      </div>
      {parent &&
        stepper(
          `이 칸 ${what}`,
          `${first ? ratio : 100 - ratio}%`,
          step(`이 칸 ${what} 줄이기`, -1, fits(next(-5)), () =>
            onRatio(parent.split_id!, next(-5)),
          ),
          step(`이 칸 ${what} 키우기`, 1, fits(next(5)), () => onRatio(parent.split_id!, next(5))),
        )}
      {stepper(
        "표 높이",
        `${table.height_mm}mm`,
        step("표 높이 줄이기", -1, height(-5) >= TABLE_HEIGHT[0], () => onHeight(height(-5))),
        step("표 높이 키우기", 1, height(5) <= TABLE_HEIGHT[1], () => onHeight(height(5))),
      )}
    </>
  );
}
