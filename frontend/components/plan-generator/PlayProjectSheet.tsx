"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { PlayProjectAnnualPlan } from "@/lib/api/types";
import {
  buildPlayProjectPreviewRows,
  fields,
  paginatePlaySheet,
  stepPlaySheetZoom,
  type PlayField,
  type PreviewRow,
  type SheetZoom,
} from "./playProjectPagination";
import styles from "./PlayProjectResult.module.css";

type Props = {
  plan: PlayProjectAnnualPlan;
  picks: Record<string, string[]>;
  interactive: boolean;
  selectedCell: { periodKey: string; rowKey: string; field: PlayField } | null;
  onSelectCell: (periodIndex: number, rowKey: string, field: PlayField) => void;
  zoom: SheetZoom;
  onZoomChange: (zoom: SheetZoom) => void;
  scrollPeriod: {
    periodKey: string;
    request: number;
    cell?: { rowKey: string; field: PlayField };
  } | null;
};

export function windowScrollDelta(rect: { top: number; bottom: number }, height: number) {
  if (rect.top < 0) return rect.top;
  return Math.max(0, rect.top + Math.min(rect.bottom - rect.top, 80) - height);
}

export default function PlayProjectSheet({
  plan,
  picks,
  interactive,
  selectedCell,
  onSelectCell,
  zoom,
  onZoomChange,
  scrollPeriod,
}: Props) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const measureRef = useRef<HTMLDivElement>(null);
  const consumedScroll = useRef<Props["scrollPeriod"]>(null);
  const groups = useMemo(() => {
    const rows = buildPlayProjectPreviewRows(plan, picks);
    return [0, 2].map((start) =>
      rows.filter((row) => plan.periods.slice(start, start + 2).includes(row.period)),
    );
  }, [plan, picks]);
  const [measurement, setMeasurement] = useState<{
    groups: PreviewRow[][];
    pages: ReturnType<typeof paginatePlaySheet>;
    dimensions: { contentHeight: number; titleHeight: number; headerHeight: number };
  } | null>(null);
  const [fit, setFit] = useState(100);
  const measuredRows = measurement?.pages.flatMap((page) => page.rows) ?? [];
  // 다시 재기 전에는 위치별 높이를 재사용해 내장 브라우저의 행을 유지한다.
  const pages =
    measurement?.groups === groups
      ? measurement.pages
      : paginatePlaySheet(
          groups.map((rows) =>
            rows.map((row) => {
              const measured =
                measuredRows.find((item) => item.key === row.key) ??
                measuredRows.find((item) => item.period.period_key === row.period.period_key);
              return { ...row, height: measured?.height, labelHeight: measured?.labelHeight };
            }),
          ),
          measurement?.dimensions ?? { contentHeight: Infinity, titleHeight: 0, headerHeight: 0 },
        );
  const percent = zoom.mode === "fit" ? fit : zoom.percent;

  useEffect(() => {
    const measuring = measureRef.current;
    if (!measuring) return;
    let cancelled = false;
    let frame = 0;
    const measure = () => {
      if (cancelled) return;
      const height = (selector: string) =>
        measuring.querySelector(selector)!.getBoundingClientRect().height;
      const rowElements = [...measuring.querySelectorAll<HTMLTableRowElement>("tbody tr")];
      const measuredGroups = groups.map((rows) =>
        rows.map((row) => {
          const element = rowElements.find((item) => item.dataset.row === row.key)!;
          const label = [
            ...element.parentElement!.querySelectorAll<HTMLElement>("[data-label]"),
          ].find((item) => item.dataset.label === row.period.period_key)!;
          return {
            ...row,
            height: element.getBoundingClientRect().height,
            labelHeight: label.getBoundingClientRect().height + 1,
          };
        }),
      );
      const dimensions = {
        contentHeight: height(`.${styles.sheetContentHeight}`),
        titleHeight: height(`.${styles.sheetTitle}`),
        headerHeight: height("thead") + 1,
      };
      setMeasurement({ groups, pages: paginatePlaySheet(measuredGroups, dimensions), dimensions });
    };
    const schedule = () => {
      if (!cancelled) {
        cancelAnimationFrame(frame);
        frame = requestAnimationFrame(measure);
      }
    };
    schedule();
    document.fonts.ready.then(schedule);
    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
    };
  }, [groups]);

  useEffect(() => {
    const viewport = viewportRef.current;
    const page = measureRef.current?.querySelector<HTMLElement>(`.${styles.sheetPage}`);
    if (!viewport || !page) return;
    let frame = 0;
    const update = () => {
      const padding = getComputedStyle(viewport);
      const width =
        viewport.clientWidth - parseFloat(padding.paddingLeft) - parseFloat(padding.paddingRight);
      setFit(Math.min(150, (width / page.getBoundingClientRect().width) * 100));
    };
    const schedule = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(update);
    };
    schedule();
    const observer = new ResizeObserver(schedule);
    observer.observe(viewport);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
    };
  }, [interactive]);

  function scrollTo(target: HTMLElement | undefined, block: "start" | "nearest") {
    const viewport = viewportRef.current;
    if (!target || !viewport) return;
    if (!window.matchMedia("(min-width: 1024px)").matches) {
      target.scrollIntoView({ block, inline: "nearest" });
      return;
    }
    const box = viewport.getBoundingClientRect();
    const rect = target.getBoundingClientRect();
    const nearest = (start: number, end: number, min: number, max: number) => {
      if (start < min && end > max) return 0;
      const oversized = end - start > max - min;
      if (start < min) return oversized ? end - max : start - min;
      if (end > max) return oversized ? start - min : end - max;
      return 0;
    };
    const top =
      block === "start" ? rect.top - box.top : nearest(rect.top, rect.bottom, box.top, box.bottom);
    const left = nearest(rect.left, rect.right, box.left, box.right);
    viewport.scrollBy({ top, left });
    const delta = windowScrollDelta(target.getBoundingClientRect(), window.innerHeight);
    if (delta) window.scrollBy({ top: delta });
  }

  useEffect(() => {
    if (!scrollPeriod || consumedScroll.current === scrollPeriod) return;
    const frame = requestAnimationFrame(() => {
      if (consumedScroll.current === scrollPeriod) return;
      const viewport = viewportRef.current;
      if (!viewport) return;
      const target = scrollPeriod.cell
        ? [...viewport.querySelectorAll<HTMLElement>("[data-cell]")].find(
            (item) =>
              item.dataset.period === scrollPeriod.periodKey &&
              item.dataset.rowKey === scrollPeriod.cell?.rowKey &&
              item.dataset.cell === scrollPeriod.cell?.field,
          )
        : [...viewport.querySelectorAll<HTMLElement>("tbody tr")].find(
            (item) => item.dataset.period === scrollPeriod.periodKey,
          );
      if (!target) return;
      consumedScroll.current = scrollPeriod;
      if (scrollPeriod.cell && !window.matchMedia("(min-width: 1024px)").matches) return;
      scrollTo(target, scrollPeriod.cell ? "nearest" : "start");
    });
    return () => cancelAnimationFrame(frame);
  }, [scrollPeriod, pages]);

  function renderTable(rows: PreviewRow[], measuring = false) {
    return (
      <table className={styles.preview}>
        <thead>
          <tr>
            <th scope="col">시기</th>
            {fields.map((field) => (
              <th scope="col" key={field.key}>
                {field.heading}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const candidate = row.candidate;
            // 내장 브라우저가 옮긴 행을 다시 그리지 않아 구간 안 위치를 고정한다.
            return (
              <tr key={row.key} data-row={row.key} data-period={row.period.period_key}>
                {row.rowSpan ? (
                  <th scope="rowgroup" rowSpan={row.rowSpan}>
                    <span className={styles.cellContent} data-label={row.period.period_key}>
                      {row.period.label}
                    </span>
                  </th>
                ) : null}
                {candidate ? (
                  fields.map((field) => {
                    const selected =
                      !measuring &&
                      interactive &&
                      selectedCell?.periodKey === row.period.period_key &&
                      selectedCell?.rowKey === candidate.row_key &&
                      selectedCell?.field === field.key;
                    if (measuring || !interactive)
                      return (
                        <td key={field.key} className={styles.plainCell}>
                          <span className={styles.cellContent}>{candidate[field.key].value}</span>
                        </td>
                      );
                    return (
                      <td
                        key={field.key}
                        data-period={row.period.period_key}
                        data-row-key={candidate.row_key}
                        data-cell={field.key}
                        className={selected ? styles.selectedCell : undefined}
                      >
                        <button
                          type="button"
                          aria-label={`${candidate.play_name.value} ${field.heading}`}
                          aria-pressed={selected}
                          className={`${styles.cellButton} ${styles.cellContent}`}
                          onClick={() =>
                            onSelectCell(
                              plan.periods.indexOf(row.period),
                              candidate.row_key,
                              field.key,
                            )
                          }
                        >
                          {candidate[field.key].value}
                        </button>
                      </td>
                    );
                  })
                ) : (
                  <td colSpan={4} className={styles.empty}>
                    <span className={styles.cellContent}>아직 고른 놀이가 없어요</span>
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    );
  }

  return (
    <section className={styles.sheet} aria-label="연간놀이계획안 미리보기">
      <div className={styles.sheetToolbar}>
        <button
          type="button"
          aria-label="축소"
          onClick={() => onZoomChange({ mode: "manual", percent: stepPlaySheetZoom(percent, -1) })}
        >
          −
        </button>
        <button
          type="button"
          aria-label="확대"
          onClick={() => onZoomChange({ mode: "manual", percent: stepPlaySheetZoom(percent, 1) })}
        >
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
        {pages.map((_page, index) => (
          <button
            type="button"
            key={index}
            onClick={() => {
              consumedScroll.current = scrollPeriod;
              scrollTo(
                viewportRef.current?.querySelectorAll<HTMLElement>(`[data-page]`)[index],
                "start",
              );
            }}
          >
            {index + 1}쪽
          </button>
        ))}
      </div>
      <div ref={viewportRef} className={styles.sheetViewport}>
        <div className={styles.sheetPages} style={{ zoom: percent / 100 }}>
          {pages.map((page, index) => (
            <article
              key={index}
              className={styles.sheetPage}
              data-page={index}
              aria-label={`${index + 1}쪽`}
            >
              {page.title && (
                <h2 className={styles.sheetTitle}>{plan.school_year} 연간놀이계획안</h2>
              )}
              {renderTable(page.rows)}
            </article>
          ))}
        </div>
      </div>
      <div ref={measureRef} className={styles.sheetMeasure} aria-hidden="true" inert>
        <div className={styles.sheetPage}>
          <div className={styles.sheetContentHeight} />
          <h2 className={styles.sheetTitle}>{plan.school_year} 연간놀이계획안</h2>
          {groups.map((rows, index) => (
            <div key={index}>{renderTable(rows, true)}</div>
          ))}
        </div>
      </div>
    </section>
  );
}
