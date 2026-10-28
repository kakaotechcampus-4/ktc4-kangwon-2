"use client";
import { useEffect, useRef, useState } from "react";
import type { PlayMonthlyActivity, PlayMonthlyPlan } from "@/lib/api/types";
import { stepPlaySheetZoom, type SheetZoom } from "./playProjectPagination";
import sheet from "./PlayProjectResult.module.css";
import styles from "./PlayMonthlyView.module.css";

// 칸은 글자로만 그린다. 고치기(④ · ⑤)는 data-cell 자리에 붙인다.
const Cell = ({ id, value }: { id: string; value: string }) => (
  <span className={styles.cell} data-cell={id}>
    {value}
  </span>
);
const md = (date: string) => date.slice(5).replace("-", ".");
const Rows = ({ rows }: { rows: PlayMonthlyActivity[] }) => (
  <ol>
    {rows.map((row) => (
      <li key={row.activity_id}>
        <Cell id={row.name.item_id} value={row.name.value} />
      </li>
    ))}
  </ol>
);

export default function PlayMonthlySheet({
  plan,
  className,
  zoom,
  onZoomChange,
}: {
  plan: PlayMonthlyPlan;
  className: string;
  zoom: SheetZoom;
  onZoomChange: (zoom: SheetZoom) => void;
}) {
  const viewport = useRef<HTMLDivElement>(null);
  const page = useRef<HTMLElement>(null);
  const [fit, setFit] = useState(100);
  const percent = zoom.mode === "fit" ? fit : zoom.percent;
  // 맞춤: 문서 폭이 상자에 들어오는 배율. 쪽 나누기는 계산하지 않는다(한 장 스케일).
  useEffect(() => {
    const box = viewport.current;
    if (!box || !page.current) return;
    const update = () => {
      const pad = getComputedStyle(box);
      const width = box.clientWidth - parseFloat(pad.paddingLeft) - parseFloat(pad.paddingRight);
      setFit(Math.min(150, (width / page.current!.offsetWidth) * 100));
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(box);
    return () => observer.disconnect();
  }, []);

  const teacher = (key: string) =>
    plan.teacher_inputs.find((input) => input.key === key)?.cell ?? null;
  const input = (key: string, label: string) => {
    const cell = teacher(key);
    return (
      <tr key={key}>
        <th scope="row">{label}</th>
        <td>{cell && <Cell id={cell.item_id} value={cell.value} />}</td>
      </tr>
    );
  };
  const safetyText = (weekId: string) => {
    const picked = plan.safety_weeks.find((w) => w.week_id === weekId)?.candidate_item_id;
    return plan.safety_candidates.find((c) => c.cell.item_id === picked)?.cell ?? null;
  };
  const drill = teacher("fire_disaster_drill");
  const step = (delta: -1 | 1) =>
    onZoomChange({ mode: "manual", percent: stepPlaySheetZoom(percent, delta) });
  const timetables = [
    ["specialized_timetable", "특성화 시간표"],
    ["special_activity_timetable", "특별활동 시간표"],
  ];
  return (
    <section className={sheet.sheet} aria-label="놀이 중심 월간계획안 미리보기">
      <div className={sheet.sheetToolbar}>
        <button type="button" aria-label="축소" onClick={() => step(-1)}>
          −
        </button>
        <button type="button" aria-label="확대" onClick={() => step(1)}>
          +
        </button>
        <button
          type="button"
          aria-label="맞춤"
          onClick={() => onZoomChange({ ...zoom, mode: "fit" })}
        >
          맞춤
        </button>
        <output>{zoom.mode === "fit" ? `맞춤 ${Math.round(percent)}%` : `${percent}%`}</output>
      </div>
      <div ref={viewport} className={sheet.sheetViewport}>
        <div className={sheet.sheetPages} style={{ zoom: percent / 100 }}>
          <article ref={page} className={sheet.sheetPage}>
            <h2 className={sheet.sheetTitle}>
              {plan.target_month.slice(0, 4)}년 {plan.month}월 놀이계획안
            </h2>
            <table className={styles.doc}>
              <tbody>
                <tr>
                  <th scope="row">놀이 주제</th>
                  <td colSpan={3}>
                    <Cell id={plan.theme.item_id} value={plan.theme.value} />
                  </td>
                </tr>
                <tr>
                  <th scope="row">예상 기간</th>
                  <td>
                    {plan.target_month.slice(0, 4)}년 {plan.month}월
                  </td>
                  <th scope="row">만 {plan.target_ages.join("·")}세</th>
                  <td>{className}</td>
                </tr>
                <tr>
                  <th scope="row">주제선정이유</th>
                  <td colSpan={3}>
                    <Cell id={plan.rationale.item_id} value={plan.rationale.value} />
                  </td>
                </tr>
              </tbody>
            </table>
            <div className={styles.bar}>[ 예상되는 놀이 방향 ]</div>
            <div className={styles.board}>
              <section>
                <h3>함께 하는 활동</h3>
                <Rows rows={plan.together} />
              </section>
              <div className={styles.center}>
                <small>우리의 놀이</small>
                <strong>{plan.theme.value}</strong>
              </div>
              <section>
                <h3>유아 예상 자유놀이</h3>
                <Rows rows={plan.free_play} />
              </section>
            </div>
            <table className={styles.doc}>
              <thead>
                <tr>
                  <th scope="col">구분</th>
                  {plan.weeks.map((week) => (
                    <th scope="col" key={week.week_id}>
                      {week.label}
                      <small>
                        {md(week.start_date)} ~ {md(week.end_date)}
                      </small>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th scope="row">기본생활습관</th>
                  {plan.weeks.map((week) => {
                    const habit = plan.habits.find((h) => h.week_id === week.week_id);
                    return (
                      <td key={week.week_id}>
                        {habit && <Cell id={habit.cell.item_id} value={habit.cell.value} />}
                      </td>
                    );
                  })}
                </tr>
                <tr>
                  <th scope="row">안전교육</th>
                  {plan.weeks.map((week) => {
                    const cell = safetyText(week.week_id);
                    return (
                      <td key={week.week_id}>
                        {cell && <Cell id={cell.item_id} value={cell.value} />}
                      </td>
                    );
                  })}
                </tr>
                <tr>
                  <th scope="row">소방대피/재난대비</th>
                  <td colSpan={plan.weeks.length}>
                    {drill && <Cell id={drill.item_id} value={drill.value} />}
                  </td>
                </tr>
              </tbody>
            </table>
            <table className={styles.doc}>
              <tbody>
                <tr>
                  <th scope="row">건강‧영양교육</th>
                  <td>
                    <b>[건강]</b>{" "}
                    <Cell id={plan.health.cell.item_id} value={plan.health.cell.value} />
                  </td>
                  <td>
                    <b>[영양]</b>{" "}
                    <Cell id={plan.nutrition.cell.item_id} value={plan.nutrition.cell.value} />
                  </td>
                </tr>
              </tbody>
            </table>
            {timetables.map(([key, label]) => (
              <div key={key}>
                <div className={styles.bar}>[ {label} ]</div>
                <table className={styles.doc}>
                  <tbody>
                    <tr>
                      <td>
                        {teacher(key) && (
                          <Cell id={teacher(key)!.item_id} value={teacher(key)!.value} />
                        )}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            ))}
            <div className={styles.bar}>[ 우리반 안내사항 ]</div>
            <table className={styles.doc}>
              <tbody>
                {input("class_notice", "안내사항")}
                {input("class_birthdays", "우리반 생일")}
                {input("home_connection", "가정연계")}
              </tbody>
            </table>
            <p className={styles.footer}>놀이 방향은 유아의 관심에 따라 달라질 수 있습니다.</p>
          </article>
        </div>
      </div>
    </section>
  );
}
