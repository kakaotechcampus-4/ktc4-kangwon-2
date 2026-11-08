"use client";
import {
  useEffect,
  useRef,
  useState,
  type DragEvent,
  type KeyboardEvent,
  type MouseEvent,
  type PointerEvent,
  type ReactNode,
} from "react";
import type {
  PlayMonthlyActivity,
  PlayMonthlyPlan,
  PlayMonthlyTimetablePart as Part,
  PlayMonthlyTimetableSize as Size,
} from "@/lib/api/types";
import {
  COLUMN_MIN,
  DAYS,
  HEIGHT_RANGE,
  RATIO_RANGE,
  tooNarrow,
  withRatio,
} from "@/lib/plan-generator/playMonthlyTimetable";
import type { PlaySection } from "@/lib/plan-generator/playMonthlyQueue";
import { dropCells, liftCells, settle } from "./rowDrag";
import { DRILL_DRAG, DROP, SAFETY_DRAG, dropTo, safetyTopic } from "./PlayMonthlySafetyPanel";

/**
 * 월간 문서 용지 — 디자인 넘김 `monthly-docs.tsx`(내보내기 양식 모양)의 선 · 머리 색 · 주 색.
 * 월간 v1 · 놀이 월간이 같이 쓴다. 칸은 서버가 준 만큼 그린다.
 */
export const LINE = "border border-[#a9d3ee]";
export const HEAD = "bg-[#e6f3fc] font-normal text-[#5c7f99]";
/** 제목 · 구획 띠의 세로 빗금(내보내기 양식 무늬). */
export const HATCH =
  "[background:repeating-linear-gradient(90deg,#c1f3fd_0_1px,transparent_1px_4px),#e1f2fe]";
export const WEEK_BG = ["#fcd6d6", "#fde2cf", "#fdf4c8", "#dff3e6", "#e4e8fb"];
const SELECTED = "outline outline-2 -outline-offset-2 outline-[#7053a0] bg-[#f6f1fb]";
export const TEACHER_HINT = "선생님이 적는 칸이에요";

/** 칸을 고를 수 있으면(`onSelect`) 누르는 칸이 되고, 고른 칸(`selected`)은 강조한다. 확정본은 `onSelect` 가 없어 글자만 그린다. */
export interface Pick {
  selected?: string | null;
  onSelect?: (itemId: string) => void;
}
/** 빈 칸은 다듬는 동안만 `hint`(기본 연한 「+ 채우기」 — 오류가 아니라 남은 할 일)를 보인다. 확정본에는 보이지 않는다. */
export const Cell = ({
  id,
  value,
  selected,
  onSelect,
  hint = "+ 채우기",
  strong = false,
  tag,
}: Pick & {
  id: string;
  value: string;
  hint?: string;
  /** 「[화재대피] …」의 [..] 를 건강 · 영양 머리처럼 굵게. */
  strong?: boolean;
  /** 「[건강] 문장」 — 머리까지 칸 안에 넣어 칸 전체가 눌린다. 한글 양식처럼 가운데. */
  tag?: string;
}) => (
  <span
    className={`${tag ? "flex h-full items-start justify-center text-center" : !value.trim() && onSelect ? "flex items-center justify-center" : "block"} min-h-[1.5em] whitespace-pre-line px-[7px] py-[2px] ${onSelect ? "cursor-pointer hover:bg-[#faf7fd]" : ""} ${selected === id ? SELECTED : ""}`}
    data-cell={id}
    {...(onSelect && {
      role: "button",
      tabIndex: 0,
      "aria-pressed": selected === id,
      onClick: () => onSelect(id),
      onKeyDown: (e: KeyboardEvent<HTMLSpanElement>) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect(id);
        }
      },
    })}
  >
    {tag && <b className="shrink-0 pr-1">[{tag}]</b>}
    {value.trim() || !onSelect ? (
      strong ? (
        value.split(/(\[[^\]\n]*\])/).map((part, n) => (n % 2 ? <b key={n}>{part}</b> : part))
      ) : (
        value
      )
    ) : (
      <span
        data-hint
        className={`text-[11px] ${hint === TEACHER_HINT ? "text-ink-soft" : "text-primary-ink"}`}
      >
        {hint}
      </span>
    )}
  </span>
);

export const Band = ({ children }: { children: ReactNode }) => (
  <div
    className={`${LINE} ${HATCH} flex h-[24px] items-center justify-center text-[13px] font-bold`}
  >
    [ {children} ]
  </div>
);

/** 주 머리 칸 — 주 색 띠 + 날짜. */
export const WeekHead = ({
  index,
  week,
}: {
  index: number;
  week: { label: string; start_date: string; end_date: string };
}) => (
  <th
    scope="col"
    className={`${LINE} py-0.5 font-normal`}
    style={{ background: WEEK_BG[index % WEEK_BG.length] }}
  >
    {week.label}
    <small className="block text-[10px] text-[#5c5243]">
      {md(week.start_date)} ~ {md(week.end_date)}
    </small>
  </th>
);
const md = (date: string) => date.slice(5).replace("-", ".");
/** 예상 기간 — 첫 주 시작 ~ 마지막 주 끝(2026.11.02 ~ 2026.11.27). */
export const period = (weeks: { start_date: string; end_date: string }[]) =>
  weeks.length
    ? `${weeks[0].start_date.replaceAll("-", ".")} ~ ${weeks[weeks.length - 1].end_date.replaceAll("-", ".")}`
    : "";

/**
 * 한 장 용지 — 한글 양식의 실제 크기(A4 59528 HWPUNIT, 연간과 같은 0.01433 px/HWPUNIT).
 * 좌우 여백 4251 → 61px, 표 폭 50703 → 727px, 본문 9pt → 13px, 제목 22pt → 32px · 13pt → 19px.
 * `scale` 이 없으면 칸이 좁은 만큼만 줄이고 넓어도 키우지 않는다(확정본 · 크게 보기).
 * 다듬기는 문서 배율 도구(`useSheetZoom`)의 배율을 넘긴다.
 */
export const PAPER_WIDTH = 853;
/** HWPUNIT → 화면 px. */
export const hu = (n: number) => Math.round(n * 0.01433);
/**
 * 표 칸의 빈 곳을 눌러도 그 칸의 글(Cell)을 고른다(월간 v1 · 놀이 월간 · 주간 공통).
 * 고를 수 있는 Cell(role=button)이 하나뿐인 td 만 — 확정본은 role 이 없어 그대로. 주간 `area` 가 붙은 칸은 그쪽이 받는다.
 */
function pickByCell(event: MouseEvent<HTMLElement>) {
  const td = event.target as HTMLElement;
  if (td.tagName !== "TD" || td.dataset.area) return;
  const cells = td.querySelectorAll<HTMLElement>("[data-cell][role=button]");
  if (cells.length === 1) cells[0].click();
}

export function Paper({
  label,
  title,
  sub,
  scale: given,
  head = 6250,
  children,
}: {
  label: string;
  title: ReactNode;
  sub: ReactNode;
  scale?: number;
  /** 제목 줄 높이(HWPUNIT) — 월간 6250 · 주간 4800. */
  head?: number;
  children: ReactNode;
}) {
  const box = useRef<HTMLElement>(null);
  const [scale, setScale] = useState(1);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const update = () => setScale(Math.min(1, el.clientWidth / PAPER_WIDTH));
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return (
    <section ref={box} aria-label={label} className="w-full min-w-0">
      <div style={{ zoom: given ?? scale }}>
        <article
          className="mx-auto w-[853px] bg-white px-[61px] py-[41px] text-[13px] leading-[1.2] text-[#2b2826] shadow-[0_1px_2px_rgba(43,40,38,0.1),0_14px_32px_-14px_rgba(43,40,38,0.35)] [&_td:has([data-cell][role=button])]:cursor-pointer [&_td:has([data-hint]):not(:has([data-area]))]:align-middle"
          onClick={pickByCell}
        >
          <div
            className={`${LINE} ${HATCH} flex flex-col justify-center px-[7px] text-center`}
            style={{ height: hu(head) }}
          >
            <h2 className="m-0 text-[32px] font-bold leading-tight">{title}</h2>
            <div className="text-right text-[19px] leading-tight">{sub}</div>
          </div>
          {children}
          <p className="m-0 mt-[12px] bg-[#e6f3fc] px-3 py-[3px] text-center text-[12px] leading-snug text-[#3d3a36]">
            *예상 놀이 방향은 [2019 개정 누리과정]의 목적에 따라 ‘유아 놀이 중심’ 활동이 진행 될 수
            있도록 융통성 있게 구성되었습니다.
            <br />
            *유아들의 흥미도와 참여 정도에 따라 다른 방향으로 조정됩니다.
          </p>
        </article>
      </div>
    </section>
  );
}

/** 안전교육 줄의 칸 주소 — 주마다 하나(같은 후보를 여러 주에 둘 수 있어 후보 id 로는 주를 모른다). */
export const safetyCellId = (weekId: string) => "safety:" + weekId;
/** 함께 하는 활동 · 자유놀이의 「AI 후보에서 고르기」 칸 주소(ADR-065). */
export const pickCellId = (section: PlaySection) => "pick:" + section;
const N = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩"];
/** 행 순서를 끌어 바꾼다 — 같은 목록 안에서만. 끈 행을 놓은 행 자리에 넣는다. */
type MoveRow = (section: PlaySection, fromId: string, toId: string) => void;
/**
 * 함께 하는 활동 · 자유놀이 목록. `onMove` 가 있으면 행 왼쪽 위 손잡이로 끌어 같은 목록 안에서 순서를 바꾼다
 * (안전교육 칸 끌기와 같은 모양). 손으로 옮기기 어려우면 행을 눌러 「칸 편집」의 위로 · 아래로 단추를 쓴다.
 */
const Rows = ({
  rows,
  mark,
  section,
  pick,
  onMove,
  ...at
}: Pick & {
  rows: PlayMonthlyActivity[];
  mark: (i: number) => string;
  section: PlaySection;
  /** AI 후보에서 고르는 계획안(ADR-065)이면 목록마다 둘 수 — 모자라면 다듬는 동안 「고르기」 칸을 단다. */
  pick?: number | null;
  onMove?: MoveRow;
}) => (
  <>
    <ol className="m-0 list-none p-0">
      {rows.map((row, i) => (
        <li
          key={row.activity_id}
          data-play-row={row.activity_id}
          className={`flex items-start ${onMove ? "group relative transition-[background-color,opacity] duration-200 [&[data-dragging]]:opacity-40 [&[data-drop]]:bg-[#efe7f8]" : ""}`}
          {...(onMove && {
            onDragOver: (event: DragEvent<HTMLElement>) => {
              event.preventDefault();
              event.currentTarget.dataset.drop = "";
            },
            onDragLeave: (event: DragEvent<HTMLElement>) => delete event.currentTarget.dataset.drop,
            onDrop: (event: DragEvent<HTMLElement>) => {
              event.preventDefault();
              delete event.currentTarget.dataset.drop;
              dropCells();
              const from = event.dataTransfer.getData("text/plain");
              // 다른 목록 · 안전교육 칸에서 끈 것은 받지 않는다.
              if (from === row.activity_id || !rows.some((r) => r.activity_id === from)) return;
              onMove(section, from, row.activity_id);
              settle(`li[data-play-row="${CSS.escape(from)}"]`);
            },
          })}
        >
          {onMove && (
            <span
              draggable
              aria-hidden="true"
              title="끌어서 순서 바꾸기"
              className="absolute left-0 top-0 z-10 cursor-grab rounded-br-md bg-[#7053a0] px-1 text-[10px] font-bold leading-[16px] text-white opacity-0 transition-opacity duration-150 active:cursor-grabbing group-hover:opacity-100"
              onDragStart={(event) => {
                const li = event.currentTarget.closest("li");
                if (li) liftCells(event, [li], row.activity_id);
              }}
              onDragEnd={dropCells}
            >
              ⠿
            </span>
          )}
          <span aria-hidden="true" className="shrink-0 py-1 pl-1.5">
            {mark(i)}
          </span>
          <span className="min-w-0 flex-1">
            <Cell {...at} id={row.name.item_id} value={row.name.value} />
          </span>
        </li>
      ))}
    </ol>
    {pick != null && at.onSelect && rows.length < pick && (
      <Cell
        {...at}
        id={pickCellId(section)}
        value=""
        hint={
          rows.length ? `+ AI 후보에서 ${pick - rows.length}개 더 고르기` : "+ AI 후보에서 고르기"
        }
      />
    )}
  </>
);

/**
 * 주마다 한 칸인 줄(안전교육 · 기본생활습관)의 칸 하나. `onMove` 가 있으면 넣은 칸 왼쪽 위 손잡이로 끌어
 * 같은 줄의 다른 주 칸에 놓는다(놀이 중심형 연간 줄 끌기와 같은 모양). 끄는 글은 안전교육이면 주 id, 습관이면
 * `habit:<주>` — 다른 줄에 놓아도 받지 않는다. 안전교육 칸은 「AI 후보」 카드를 끌어 놓아도(`onPlace`) 그 주에 둔다.
 * 손으로 옮기기 어려우면 칸을 눌러 「AI 후보」 · 「칸 편집」을 쓴다.
 */
function WeekTd({
  row,
  weekId,
  cellId,
  value,
  weekIds,
  onMove,
  onPlace,
  ...at
}: Pick & {
  row: "safety" | "habit";
  weekId: string;
  cellId: string;
  value: string;
  weekIds: string[];
  onMove?: (fromWeekId: string, toWeekId: string) => void;
  onPlace?: (weekId: string, candidateItemId: string) => void;
}) {
  const prefix = row === "safety" ? "" : "habit:";
  const where = `data-${row}-week`;
  const drop = onMove && {
    onDragOver: (event: DragEvent<HTMLElement>) => {
      event.preventDefault();
      event.currentTarget.dataset.drop = "";
    },
    onDragLeave: (event: DragEvent<HTMLElement>) => delete event.currentTarget.dataset.drop,
    onDrop: (event: DragEvent<HTMLElement>) => {
      event.preventDefault();
      delete event.currentTarget.dataset.drop;
      dropCells();
      const data = event.dataTransfer.getData("text/plain");
      const settled = () => settle(`td[${where}="${CSS.escape(weekId)}"]`);
      if (onPlace && data.startsWith(SAFETY_DRAG)) {
        onPlace(weekId, data.slice(SAFETY_DRAG.length));
        return settled();
      }
      const from = data.startsWith(prefix) ? data.slice(prefix.length) : "";
      if (!weekIds.includes(from) || from === weekId) return;
      onMove(from, weekId);
      settled();
    },
  };
  return (
    <td
      {...{ [where]: weekId }}
      className={`${LINE} p-0 ${onMove ? "group relative transition-[background-color,opacity] duration-200 [&[data-dragging]]:opacity-40 [&[data-drop]]:bg-[#efe7f8]" : ""}`}
      {...drop}
    >
      {onMove && value && (
        <span
          draggable
          aria-hidden="true"
          title="끌어서 다른 주로 옮기기"
          className="absolute left-0 top-0 z-10 cursor-grab rounded-br-md bg-[#7053a0] px-1 text-[10px] font-bold leading-[16px] text-white opacity-0 transition-opacity duration-150 active:cursor-grabbing group-hover:opacity-100"
          onDragStart={(event) => {
            const td = event.currentTarget.closest("td");
            if (td) liftCells(event, [td], prefix + weekId, "x");
          }}
          onDragEnd={dropCells}
        >
          ⠿
        </span>
      )}
      <Cell {...at} id={cellId} value={value} strong={row === "safety"} />
    </td>
  );
}

export default function PlayMonthlySheet({
  plan,
  selected,
  onSelect,
  scale,
  onRatio,
  onSize,
  onMoveSafety,
  onPlaceSafety,
  onDropDrill,
  onMoveHabit,
  onMoveRow,
}: {
  plan: PlayMonthlyPlan;
  /** 「AI 후보」의 안전교육 후보 카드를 문서의 주 칸에 끌어 놓았다 — `onMoveSafety` 가 있을 때만 받는다. */
  onPlaceSafety?: (weekId: string, candidateItemId: string) => void;
  /** 「AI 후보」 훈련 카드를 소방대피/재난대비 칸에 끌어 놓았다. 없으면(확정 · 저장 중) 받지 않는다. */
  onDropDrill?: (candidateItemId: string) => void;
  /** 기본생활습관 칸을 다른 주로 끌어 옮긴다(두 주를 맞바꾼다) — 다듬는 동안만. */
  onMoveHabit?: (fromWeekId: string, toWeekId: string) => void;
  /** 함께 하는 활동 · 자유놀이 행을 같은 목록 안에서 끌어 옮긴다 — 다듬는 동안만. */
  onMoveRow?: MoveRow;
  /** 안전교육 칸을 다른 주로 끌어 옮긴다(두 주를 맞바꾼다) — 다듬는 동안만. */
  onMoveSafety?: (fromWeekId: string, toWeekId: string) => void;
  /** 문서 배율(다듬기). 없으면 칸에 맞춰 줄이기만. */
  scale?: number;
  /** 특별활동 시간표 경계 · 크기 — 다듬는 동안만. */
  onRatio?: (splitId: string, ratio: number) => void;
  onSize?: (size: Size) => void;
} & Pick) {
  const at = { selected, onSelect };
  const teacher = (key: string) =>
    plan.teacher_inputs.find((input) => input.key === key)?.cell ?? null;
  const input = (key: string, label: string) => {
    const cell = teacher(key);
    return (
      <tr key={key}>
        <th scope="row" className={`${LINE} ${HEAD} w-[15%]`}>
          {label}
        </th>
        <td className={`${LINE} p-0`}>
          {cell && <Cell {...at} hint={TEACHER_HINT} id={cell.item_id} value={cell.value} />}
        </td>
      </tr>
    );
  };
  // 「[교통안전]」 다음 줄에 문장. 빈 문장이면 빈칸(머리도 안 붙인다).
  const safetyText = (weekId: string) => {
    const picked = plan.safety_weeks.find((w) => w.week_id === weekId)?.candidate_item_id;
    const c = plan.safety_candidates.find((c) => c.cell.item_id === picked);
    return c?.cell.value.trim() ? `[${safetyTopic(c)}]\n${c.cell.value}` : "";
  };
  const drill = teacher("fire_disaster_drill");
  const weeks = plan.weeks;
  const weekIds = weeks.map((w) => w.week_id);
  return (
    <Paper
      label="놀이 중심 월간계획안 미리보기"
      title={<Cell {...at} id={plan.display.title.item_id} value={plan.display.title.value} />}
      sub={
        <div className="flex justify-end">
          <Cell {...at} id={plan.display.age.item_id} value={plan.display.age.value} />
          <Cell
            {...at}
            id={plan.display.class_name.item_id}
            value={plan.display.class_name.value}
          />
        </div>
      }
      scale={scale}
    >
      <table className="w-full table-fixed border-collapse">
        <colgroup>
          <col style={{ width: "15%" }} />
          <col />
        </colgroup>
        <tbody>
          <tr>
            {/* 머리칸 글은 한글 양식 그대로(띄어 쓴 「놀 이 주 제」). */}
            <th scope="row" aria-label="놀이 주제" className={`${LINE} h-7 font-bold`}>
              놀 이 주 제
            </th>
            <td className={`${LINE} p-0`}>
              <Cell {...at} id={plan.theme.item_id} value={plan.theme.value} />
            </td>
          </tr>
          <tr>
            <th scope="row" aria-label="예상 기간" className={`${LINE} h-7 font-bold`}>
              예 상 기 간
            </th>
            <td className={`${LINE} p-0`}>
              <Cell {...at} id={plan.display.period.item_id} value={plan.display.period.value} />
            </td>
          </tr>
          <tr>
            <th scope="row" className={`${LINE} font-bold`}>
              주제선정이유
            </th>
            <td className={`${LINE} p-0 text-[11.5px]`}>
              <Cell {...at} id={plan.rationale.item_id} value={plan.rationale.value} />
            </td>
          </tr>
        </tbody>
      </table>
      <Band>예상되는 놀이 방향</Band>
      <table className="w-full table-fixed border-collapse">
        <colgroup>
          <col style={{ width: "35%" }} />
          <col style={{ width: "30%" }} />
          <col style={{ width: "35%" }} />
        </colgroup>
        <tbody>
          <tr>
            <th scope="col" className={`${LINE} h-6 font-normal text-[#d0479a]`}>
              함께 하는 활동
            </th>
            <td rowSpan={2} className={`${LINE} p-0 text-center font-bold`}>
              <Cell {...at} id={plan.direction.item_id} value={plan.direction.value} />
            </td>
            <th scope="col" className={`${LINE} font-normal text-[#d0479a]`}>
              유아 예상 자유놀이
            </th>
          </tr>
          <tr>
            {/* 한글 양식처럼 목록은 세로 가운데. */}
            <td className={`${LINE} p-0 align-middle`}>
              <Rows
                {...at}
                rows={plan.together}
                mark={(i) => N[i] ?? `${i + 1}.`}
                section="together"
                pick={plan.activity_pick}
                onMove={onMoveRow}
              />
            </td>
            <td className={`${LINE} p-0 align-middle`}>
              <Rows
                {...at}
                rows={plan.free_play}
                mark={() => "-"}
                section="free_play"
                pick={plan.activity_pick}
                onMove={onMoveRow}
              />
            </td>
          </tr>
        </tbody>
      </table>
      <div className="mt-2" />
      <table className="w-full table-fixed border-collapse text-[11.5px] leading-tight">
        <colgroup>
          <col style={{ width: "15%" }} />
          {weeks.map((week) => (
            <col key={week.week_id} />
          ))}
        </colgroup>
        <thead>
          <tr>
            {/* 한글 양식의 이 칸은 비어 있다. */}
            <th scope="col" className={`${LINE} ${HEAD} h-6`} />
            {weeks.map((week, i) => (
              <WeekHead key={week.week_id} index={i} week={week} />
            ))}
          </tr>
        </thead>
        <tbody className="text-center">
          <tr>
            <th scope="row" className={`${LINE} ${HEAD} h-9`}>
              기본생활습관
            </th>
            {weeks.map((week) => {
              const habit = plan.habits.find((h) => h.week_id === week.week_id);
              return habit ? (
                <WeekTd
                  key={week.week_id}
                  row="habit"
                  weekId={week.week_id}
                  cellId={habit.cell.item_id}
                  value={
                    habit.label && habit.cell.value.trim()
                      ? `[${habit.label}]\n${habit.cell.value}`
                      : habit.cell.value
                  }
                  weekIds={weekIds}
                  onMove={onMoveHabit}
                  {...at}
                />
              ) : (
                <td key={week.week_id} className={`${LINE} p-0`} />
              );
            })}
          </tr>
          <tr>
            <th scope="row" className={`${LINE} ${HEAD} h-9`}>
              안전교육
            </th>
            {weeks.map((week) => (
              <WeekTd
                key={week.week_id}
                row="safety"
                weekId={week.week_id}
                cellId={safetyCellId(week.week_id)}
                value={safetyText(week.week_id)}
                weekIds={weekIds}
                onMove={onMoveSafety}
                onPlace={onPlaceSafety}
                {...at}
              />
            ))}
          </tr>
          <tr>
            <th scope="row" className={`${LINE} ${HEAD} h-6`}>
              소방대피/재난대비
            </th>
            <td
              colSpan={weeks.length}
              className={`${LINE} p-0 transition-colors ${DROP}`}
              {...(onDropDrill && dropTo(onDropDrill, DRILL_DRAG))}
            >
              {drill && <Cell {...at} id={drill.item_id} value={drill.value} strong />}
            </td>
          </tr>
          <tr>
            <th scope="row" className={`${LINE} ${HEAD} h-7`}>
              건강·영양교육
            </th>
            <td colSpan={Math.ceil(weeks.length / 2)} className={`${LINE} h-px p-0`}>
              <Cell
                {...at}
                tag="건강"
                id={plan.health.cell.item_id}
                value={plan.health.cell.value}
              />
            </td>
            <td colSpan={Math.floor(weeks.length / 2)} className={`${LINE} h-px p-0`}>
              <Cell
                {...at}
                tag="영양"
                id={plan.nutrition.cell.item_id}
                value={plan.nutrition.cell.value}
              />
            </td>
          </tr>
        </tbody>
      </table>
      <Timetables plan={plan} {...at} onRatio={onRatio} onSize={onSize} />
      <div className="mt-2" />
      <Band>우리반 안내사항</Band>
      <table className="w-full table-fixed border-collapse text-[11.5px]">
        <tbody>
          {input("class_birthdays", "우리반 생일")}
          {input("home_connection", "가정연계")}
        </tbody>
      </table>
    </Paper>
  );
}

/** 1mm = 283.465 HWPUNIT — 용지와 같은 배율로 그린다. */
const mm = (n: number) => hu(n * 283.465);
/** 요일 머리 글자색(한글 양식). */
const DAY_COLOR = ["#b77045", "#ff5353", "#32a744", "#000", "#ff008b"];

/** 끌기 · 방향키로 바꾸는 값 하나. 보이는 동안은 미리 그리고, 놓을 때 한 번 저장한다. */
type Handle =
  | { kind: "split"; day: number; splitId: string; axis: "VERTICAL" | "HORIZONTAL"; value: number }
  | { kind: "column"; day: number; value: number }
  | { kind: "height"; value: number };

/**
 * 특성화 시간표(제목 · 내용 5열)와 특별활동 시간표(요일별 나눔 트리, ADR-047).
 * `onRatio` · `onSize` 가 있으면 경계선을 끌어 크기를 바꾼다 — 확정본 · 크게 보기에는 없다.
 * 한도(비율 10~90 · 열 5% · 칸 3.5% · 높이 16~80mm)는 화면이 미리 지키고 최종 검사는 서버가 한다.
 */
function Timetables({
  plan,
  onRatio,
  onSize,
  ...at
}: Pick & {
  plan: PlayMonthlyPlan;
  onRatio?: (splitId: string, ratio: number) => void;
  onSize?: (size: Size) => void;
}) {
  // 끄는 중인 값과 시작점(화면 좌표 · 값 1 의 길이 · 처음 값).
  const [drag, setDrag] = useState<{
    handle: Handle;
    x: number;
    y: number;
    length: number;
    from: number;
  } | null>(null);
  const resizable = !!(onRatio && onSize && at.onSelect);
  const size = plan.special_activity_size;

  // 미리 보기 값을 입힌 모양 · 크기.
  const shown = (handle: Handle | null) => {
    let days = plan.special_activity;
    let widths = size.column_widths;
    let height = size.height_mm;
    if (handle?.kind === "split")
      days = days.map((d, i) =>
        i === handle.day ? withRatio(d, handle.splitId, handle.value) : d,
      );
    if (handle?.kind === "column") {
      const pair = widths[handle.day] + widths[handle.day + 1];
      widths = widths.map((w, i) =>
        i === handle.day ? handle.value : i === handle.day + 1 ? pair - handle.value : w,
      );
    }
    if (handle?.kind === "height") height = handle.value;
    return { days, widths, height };
  };
  // 한도 안의 가장 가까운 값 — 칸이 너무 좁아지면 처음 값 쪽으로 물러선다.
  function fit(handle: Handle, wanted: number, from: number) {
    const [low, high] =
      handle.kind === "height"
        ? HEIGHT_RANGE
        : handle.kind === "split"
          ? RATIO_RANGE
          : [
              COLUMN_MIN,
              size.column_widths[handle.day] + size.column_widths[handle.day + 1] - COLUMN_MIN,
            ];
    let value = Math.min(high, Math.max(low, Math.round(wanted)));
    const ok = (v: number) => {
      const s = shown({ ...handle, value: v });
      return !tooNarrow(s.days, s.widths);
    };
    while (value !== from && !ok(value)) value += value < from ? 1 : -1;
    return value;
  }
  function commit(handle: Handle) {
    if (handle.kind === "split") return onRatio?.(handle.splitId, handle.value);
    const s = shown(handle);
    onSize?.({ column_widths: s.widths, height_mm: s.height });
  }

  const handleProps = (handle: Handle, label: string) => ({
    role: "separator",
    tabIndex: 0,
    "aria-label": label,
    "aria-valuenow": handle.value,
    "aria-orientation": (handle.kind === "height" ||
    (handle.kind === "split" && handle.axis === "VERTICAL")
      ? "horizontal"
      : "vertical") as "horizontal" | "vertical",
    title: "끌거나 방향키로 크기를 바꿔요",
    "data-resize": handle.kind,
    onClick: (e: { stopPropagation: () => void }) => e.stopPropagation(),
    onPointerDown: (e: PointerEvent<HTMLDivElement>) => {
      if (e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();
      e.currentTarget.setPointerCapture(e.pointerId);
      // 값 1 만큼의 화면 길이(px, 배율 포함) — 비율은 그 마디의 1%, 열은 표 폭의 1%, 높이는 1mm.
      const el = e.currentTarget;
      const box = el.parentElement!.getBoundingClientRect();
      const length =
        handle.kind === "height"
          ? el.parentElement!.querySelector("td > div")!.getBoundingClientRect().height /
            handle.value
          : handle.kind === "column"
            ? el.closest("table")!.getBoundingClientRect().width / 100
            : handle.axis === "HORIZONTAL"
              ? box.width / 100
              : box.height / 100;
      setDrag({ handle, x: e.clientX, y: e.clientY, length, from: handle.value });
    },
    onPointerMove: (e: PointerEvent<HTMLDivElement>) => {
      if (!drag) return;
      const h = drag.handle;
      const across = h.kind === "column" || (h.kind === "split" && h.axis === "HORIZONTAL");
      const moved = (across ? e.clientX - drag.x : e.clientY - drag.y) / drag.length;
      setDrag({ ...drag, handle: { ...h, value: fit(h, drag.from + moved, drag.from) } });
    },
    onPointerUp: () => {
      if (drag && drag.handle.value !== drag.from) commit(drag.handle);
      setDrag(null);
    },
    onPointerCancel: () => setDrag(null),
    onKeyDown: (e: KeyboardEvent<HTMLDivElement>) => {
      const back = handle.kind === "height" ? "ArrowUp" : "ArrowLeft";
      const ahead = handle.kind === "height" ? "ArrowDown" : "ArrowRight";
      const keys =
        handle.kind === "split" && handle.axis === "VERTICAL"
          ? ["ArrowUp", "ArrowDown"]
          : [back, ahead];
      if (!keys.includes(e.key)) return;
      e.preventDefault();
      const step = (handle.kind === "height" ? 1 : 5) * (e.key === keys[0] ? -1 : 1);
      const value = fit(handle, handle.value + step, handle.value);
      if (value !== handle.value) commit({ ...handle, value });
    },
  });

  const view = shown(drag?.handle ?? null);
  const tree = (part: Part, day: number): ReactNode => {
    if (part.cell)
      return (
        <div className="flex h-full min-h-0 min-w-0 overflow-auto [&>span]:flex [&>span]:min-h-full [&>span]:w-full [&>span]:flex-col [&>span]:justify-center [&>span]:text-center">
          <Cell {...at} hint={TEACHER_HINT} id={part.cell.item_id} value={part.cell.value} />
        </div>
      );
    const across = part.axis === "HORIZONTAL";
    const ratio = part.ratio!;
    return (
      <div
        className="relative grid h-full min-h-0 min-w-0"
        style={{
          [across ? "gridTemplateColumns" : "gridTemplateRows"]:
            `minmax(0,${ratio}fr) minmax(0,${100 - ratio}fr)`,
        }}
      >
        {part.children.map((child, i) => (
          <div
            key={i}
            className={`min-h-0 min-w-0 ${i ? (across ? "border-l" : "border-t") + " border-[#a9d3ee]" : ""}`}
          >
            {tree(child, day)}
          </div>
        ))}
        {resizable && (
          <div
            {...handleProps(
              { kind: "split", day, splitId: part.split_id!, axis: part.axis!, value: ratio },
              `${DAYS[day]}요일 칸 경계`,
            )}
            className={`absolute z-[3] touch-none select-none hover:bg-[#699b5b55] focus-visible:bg-[#699b5b55] ${across ? "inset-y-0 w-[9px] -translate-x-1/2 cursor-col-resize" : "inset-x-0 h-[9px] -translate-y-1/2 cursor-row-resize"}`}
            style={across ? { left: `${ratio}%` } : { top: `${ratio}%` }}
          />
        )}
      </div>
    );
  };

  const specialized = plan.specialized_timetable;
  return (
    <>
      <div className="mt-2" />
      <Band>특성화 시간표</Band>
      <table className="w-full table-fixed border-collapse text-[11.5px]">
        <tbody className="text-center">
          {[specialized.slice(0, 5), specialized.slice(5, 10)].map((row, r) => (
            <tr key={r}>
              {row.map((cell) => (
                <td
                  key={cell.item_id}
                  className={`${LINE} p-0 ${r ? "h-[40px]" : `h-[24px] ${HEAD}`}`}
                >
                  <Cell {...at} hint={TEACHER_HINT} id={cell.item_id} value={cell.value} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-2" />
      <Band>특별활동 시간표</Band>
      <div className="relative">
        <table className="w-full table-fixed border-collapse text-[11.5px]">
          <colgroup>
            {view.widths.map((w, i) => (
              <col key={i} style={{ width: `${w}%` }} />
            ))}
          </colgroup>
          <thead>
            <tr>
              {DAYS.map((day, i) => (
                <th
                  key={day}
                  scope="col"
                  className={`${LINE} ${HEAD} relative h-6`}
                  style={{ color: DAY_COLOR[i] }}
                >
                  {day}
                  {resizable && i < 4 && (
                    <div
                      {...handleProps(
                        { kind: "column", day: i, value: size.column_widths[i] },
                        `${day}요일 오른쪽 열 경계`,
                      )}
                      className="absolute inset-y-0 left-full z-[3] w-[9px] -translate-x-1/2 cursor-col-resize touch-none select-none hover:bg-[#699b5b55] focus-visible:bg-[#699b5b55]"
                    />
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              {view.days.map((day, i) => (
                <td key={i} className={`${LINE} p-0 align-top`}>
                  <div style={{ height: mm(view.height) }}>{tree(day, i)}</div>
                </td>
              ))}
            </tr>
          </tbody>
        </table>
        {resizable && (
          <div
            {...handleProps({ kind: "height", value: size.height_mm }, "특별활동 시간표 전체 높이")}
            className="absolute inset-x-0 top-full z-[3] h-[9px] -translate-y-1/2 cursor-row-resize touch-none select-none hover:bg-[#699b5b55] focus-visible:bg-[#699b5b55]"
          />
        )}
      </div>
    </>
  );
}
