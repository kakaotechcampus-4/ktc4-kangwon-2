"use client";
import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
} from "react";
import type { PlayMonthlyActivity, PlayMonthlyPlan } from "@/lib/api/types";

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
/** 빈 칸은 다듬는 동안만 `hint`(기본 빨간 「비어 있어요」)를 보인다. 확정본에는 보이지 않는다. */
export const Cell = ({
  id,
  value,
  selected,
  onSelect,
  hint = "비어 있어요",
}: Pick & { id: string; value: string; hint?: string }) => (
  <span
    className={`${!value.trim() && onSelect ? "flex items-center justify-center" : "block"} min-h-[1.5em] whitespace-pre-line px-[7px] py-[2px] ${onSelect ? "cursor-pointer hover:bg-[#faf7fd]" : ""} ${selected === id ? SELECTED : ""}`}
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
    {value.trim() || !onSelect ? (
      value
    ) : (
      <span
        data-hint
        className={`text-[11px] ${hint === TEACHER_HINT ? "text-[#8a8178]" : "text-[#c2473d]"}`}
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
  title: string;
  sub: string;
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
          className="mx-auto w-[853px] bg-white px-[61px] py-[41px] text-[13px] leading-[1.2] text-[#2b2826] shadow-[0_8px_24px_-12px_rgba(43,40,38,0.25)] [&_td:has([data-cell][role=button])]:cursor-pointer [&_td:has([data-hint]):not(:has([data-area]))]:align-middle"
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
          <p className="m-0 mt-[12px] bg-[#e6f3fc] px-3 py-[3px] text-center text-[10px] leading-snug text-[#3d3a36]">
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
const N = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩"];
const Rows = ({
  rows,
  mark,
  ...at
}: Pick & { rows: PlayMonthlyActivity[]; mark: (i: number) => string }) => (
  <ol className="m-0 list-none p-0">
    {rows.map((row, i) => (
      <li key={row.activity_id} className="flex items-start">
        <span aria-hidden="true" className="shrink-0 py-1 pl-1.5">
          {mark(i)}
        </span>
        <span className="min-w-0 flex-1">
          <Cell {...at} id={row.name.item_id} value={row.name.value} />
        </span>
      </li>
    ))}
  </ol>
);

const Tagged = ({ tag, children }: { tag: string; children: ReactNode }) => (
  <div className="flex items-start text-left">
    <b className="shrink-0 py-1 pl-1.5">[{tag}]</b>
    <span className="min-w-0 flex-1">{children}</span>
  </div>
);

export default function PlayMonthlySheet({
  plan,
  className,
  selected,
  onSelect,
  scale,
}: {
  plan: PlayMonthlyPlan;
  className: string;
  /** 문서 배율(다듬기). 없으면 칸에 맞춰 줄이기만. */
  scale?: number;
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
  const safetyText = (weekId: string) => {
    const picked = plan.safety_weeks.find((w) => w.week_id === weekId)?.candidate_item_id;
    return plan.safety_candidates.find((c) => c.cell.item_id === picked)?.cell.value ?? "";
  };
  const drill = teacher("fire_disaster_drill");
  const timetables = [
    ["specialized_timetable", "특성화 시간표"],
    ["special_activity_timetable", "특별활동 시간표"],
  ];
  const weeks = plan.weeks;
  return (
    <Paper
      label="놀이 중심 월간계획안 미리보기"
      title={`${plan.month}월 놀이계획안`}
      sub={`만 ${plan.target_ages.join("·")}세 ${className}`.trim()}
      scale={scale}
    >
      <table className="w-full table-fixed border-collapse">
        <colgroup>
          <col style={{ width: "15%" }} />
          <col />
        </colgroup>
        <tbody>
          <tr>
            <th scope="row" className={`${LINE} h-7 font-bold`}>
              놀이 주제
            </th>
            <td className={`${LINE} p-0`}>
              <Cell {...at} id={plan.theme.item_id} value={plan.theme.value} />
            </td>
          </tr>
          <tr>
            <th scope="row" className={`${LINE} h-7 font-bold`}>
              예상 기간
            </th>
            <td className={`${LINE} px-1.5`}>{period(weeks)}</td>
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
            <td rowSpan={2} className={`${LINE} px-2 text-center font-bold`}>
              {plan.theme.value}
            </td>
            <th scope="col" className={`${LINE} font-normal text-[#d0479a]`}>
              유아 예상 자유놀이
            </th>
          </tr>
          <tr>
            <td className={`${LINE} p-0 align-top`}>
              <Rows {...at} rows={plan.together} mark={(i) => N[i] ?? `${i + 1}.`} />
            </td>
            <td className={`${LINE} p-0 align-top`}>
              <Rows {...at} rows={plan.free_play} mark={() => "-"} />
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
            <th scope="col" className={`${LINE} ${HEAD} h-6`}>
              구분
            </th>
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
              return (
                <td key={week.week_id} className={`${LINE} p-0`}>
                  {habit && <Cell {...at} id={habit.cell.item_id} value={habit.cell.value} />}
                </td>
              );
            })}
          </tr>
          <tr>
            <th scope="row" className={`${LINE} ${HEAD} h-9`}>
              안전교육
            </th>
            {weeks.map((week) => (
              <td key={week.week_id} className={`${LINE} p-0`}>
                <Cell {...at} id={safetyCellId(week.week_id)} value={safetyText(week.week_id)} />
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row" className={`${LINE} ${HEAD} h-6`}>
              소방대피/재난대비
            </th>
            <td colSpan={weeks.length} className={`${LINE} p-0 text-left`}>
              {drill && <Cell {...at} hint={TEACHER_HINT} id={drill.item_id} value={drill.value} />}
            </td>
          </tr>
          <tr>
            <th scope="row" className={`${LINE} ${HEAD} h-7`}>
              건강·영양교육
            </th>
            <td colSpan={Math.ceil(weeks.length / 2)} className={`${LINE} p-0`}>
              <Tagged tag="건강">
                <Cell {...at} id={plan.health.cell.item_id} value={plan.health.cell.value} />
              </Tagged>
            </td>
            <td colSpan={Math.floor(weeks.length / 2)} className={`${LINE} p-0`}>
              <Tagged tag="영양">
                <Cell {...at} id={plan.nutrition.cell.item_id} value={plan.nutrition.cell.value} />
              </Tagged>
            </td>
          </tr>
        </tbody>
      </table>
      {timetables.map(([key, label]) => {
        const cell = teacher(key);
        return (
          <div key={key} className="mt-2">
            <Band>{label}</Band>
            <div className={`${LINE} border-t-0 text-[11.5px]`}>
              {cell && <Cell {...at} hint={TEACHER_HINT} id={cell.item_id} value={cell.value} />}
            </div>
          </div>
        );
      })}
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
