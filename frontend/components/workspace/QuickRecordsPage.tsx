"use client";

/**
 * 주간 기록 — 한 주를 한눈에 놓고, 하루를 골라 그날 기록을 본다 (S-J6 · FR-705).
 *
 * 관찰 기록 화면은 아이별로 찾을 때 쓰고, 이 화면은 「이번 주 뭐가 비었지」를 볼 때 쓴다.
 * 그래서 주간 띠가 먼저 오고 목록이 뒤에 온다.
 *
 * 관찰 기록과 일과 기록을 같이 보여준다 — 둘 다 일지의 근거라 교사는 섞어서 본다.
 * 둘 다 고른 반(`class_id`)과 그 주로만 부른다. 반을 빼면 원 전체가 섞인다 (FR-405).
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { WorkspacePage, Message, useClasses } from "./WorkspaceUI";
import { Icon, type IconName } from "@/components/app/icons";
import { listRecords } from "@/lib/api/records";
import type { ServerObservation } from "@/lib/api/observations";
import { listRoutines, timeRange, type ApiRoutine } from "@/lib/api/routines";
import { classServerId } from "@/lib/api/onboarding";
import { today, localTime } from "@/lib/workspace/model";
import { ROUTINES_UNMAPPED, routinesPath } from "@/lib/workspace/routines-route";
import { useClientState } from "@/lib/hooks/use-client-state";
import { chosenClassFor, loadClassSettings } from "@/lib/onboarding/settings";

const DAY_NAMES = ["월", "화", "수", "목", "금", "토", "일"];
const DOMAIN_ICON: Record<string, IconName> = {
  "신체운동·건강": "body",
  의사소통: "talk",
  사회관계: "social",
  예술경험: "art",
  자연탐구: "nature",
};

/** 그 날이 든 주의 월요일. 날짜 계산은 전부 현지 시간으로 한다 — UTC 로 돌면 하루가 밀린다. */
function mondayOf(iso: string) {
  const date = new Date(iso + "T00:00:00");
  const weekday = (date.getDay() + 6) % 7; // 일요일 0 을 6 으로 옮긴다
  date.setDate(date.getDate() - weekday);
  return date;
}
function isoOf(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}
function shift(iso: string, days: number) {
  const date = new Date(iso + "T00:00:00");
  date.setDate(date.getDate() + days);
  return isoOf(date);
}
const label = (iso: string) => `${Number(iso.slice(5, 7))}월 ${Number(iso.slice(8, 10))}일`;

/** 그 주에 받은 두 종류. 반 · 주를 key 로 둬서 다른 주로 넘기면 「불러오는 중」이 된다. */
type WeekRecords = {
  key: string;
  observations: ServerObservation[];
  routines: ApiRoutine[];
  error: string;
  /** 관찰 · 일과 둘 다 못 불러왔다. 그릴 것이 없다. */
  failedAll: boolean;
};

export default function QuickRecordsPage() {
  const [loaded, setLoaded] = useState<WeekRecords | null>(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useClientState(() => today(), "");
  // 일과 기록은 반 하나의 하루다. 이 화면은 반을 안 가리므로 여기서 한 번 고르게 한다 (S-J1 들어오는 길).
  const classes = useClasses(setError);
  const [pickedClass, setClassId] = useState<string | null>(null);
  const [primaryClass] = useClientState(() => chosenClassFor(loadClassSettings())?.id ?? "", "");
  const classId = pickedClass ?? primaryClass;
  const routines = routinesPath(classId, selected);

  const weekStart = useMemo(() => (selected ? isoOf(mondayOf(selected)) : ""), [selected]);
  const weekEnd = weekStart ? shift(weekStart, 6) : "";
  const weekKey = classId && weekStart ? `${classId}|${weekStart}` : "";

  // 주를 넘길 때마다 그 주만 부른다. 날짜를 고르는 것은 서버를 다시 부르지 않는다.
  useEffect(() => {
    if (!weekKey) return;
    let live = true;
    const serverClass = classServerId(classId);
    Promise.allSettled([
      listRecords(classId, { from: weekStart, to: weekEnd }),
      serverClass === null
        ? Promise.reject(new Error(ROUTINES_UNMAPPED))
        : listRoutines({ class_id: serverClass, from: weekStart, to: weekEnd }),
    ]).then(([observations, routineRows]) => {
      if (!live) return;
      // 한쪽이 실패해도 다른 쪽은 그린다.
      const failed = [
        observations.status === "rejected" && "관찰 기록",
        routineRows.status === "rejected" && "일과 기록",
      ].filter(Boolean);
      setLoaded({
        key: weekKey,
        observations: observations.status === "fulfilled" ? observations.value : [],
        routines: routineRows.status === "fulfilled" ? routineRows.value : [],
        error: failed.length ? `${failed.join("과 ")}을 불러오지 못했어요. 새로고침해주세요.` : "",
        failedAll: failed.length === 2,
      });
    });
    return () => {
      live = false;
    };
  }, [classId, weekKey, weekStart, weekEnd]);

  const week = loaded?.key === weekKey ? loaded : null;
  const observations = (week?.observations ?? []).filter((r) => r.classId === classId);
  const routineRows = week?.routines ?? [];

  const days = useMemo(
    () => (weekStart ? Array.from({ length: 7 }, (_, i) => shift(weekStart, i)) : []),
    [weekStart],
  );
  const countOf = (iso: string) => ({
    observations: observations.filter((r) => r.date === iso).length,
    routines: routineRows.filter((r) => r.date === iso).length,
  });
  // 일과는 그 날의 순서(서버가 정한 행 순서)대로 먼저, 관찰 기록은 그 뒤에 둔다.
  const dayRoutines = routineRows.filter((r) => r.date === selected);
  const dayRecords = observations.filter((r) => r.date === selected);
  const dayCount = dayRoutines.length + dayRecords.length;

  // 반을 못 불러왔거나 관찰 · 일과 둘 다 못 불러왔으면 안내만 둔다. 빈 달력과 「남긴 기록이 없어요」가
  // 같이 보이면 기록이 사라진 것으로 읽힌다. 한쪽만 실패했으면 다른 쪽은 그대로 그린다.
  if (error || week?.failedAll) {
    return (
      <WorkspacePage
        title="주간 기록"
        description="한 주를 펼쳐 놓고, 어느 날이 비었는지 확인하세요."
      >
        <Message error>{error || week?.error}</Message>
      </WorkspacePage>
    );
  }

  return (
    <WorkspacePage
      title="주간 기록"
      description="한 주를 펼쳐 놓고, 어느 날이 비었는지 확인하세요."
      action={
        <Link
          href="/"
          className="inline-flex min-h-11 items-center gap-2 rounded-md border border-primary-line bg-primary px-4 text-xs font-semibold text-white shadow-pg-card hover:bg-primary-hover"
        >
          <Icon name="plus" className="h-4 w-4" />
          기록 남기기
        </Link>
      }
    >
      <Message error>{week?.error}</Message>

      <section className="rounded-sm border border-line bg-paper p-5 shadow-pg-card">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-display text-[26px] font-bold">우리 반 기록</h2>
          <div className="flex items-center gap-3 text-xs text-ink-soft">
            <label className="flex items-center gap-2">
              반
              <select
                value={classId}
                onChange={(e) => setClassId(e.target.value)}
                className="min-h-11 rounded-md border border-line bg-paper px-2 text-xs text-ink"
              >
                <option value="">반 선택</option>
                {classes.map((room) => (
                  <option key={room.id} value={room.id}>
                    {room.className || "이름 없는 반"}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              aria-label="지난 주"
              onClick={() => setSelected(shift(selected, -7))}
              className="flex h-11 w-11 items-center justify-center rounded-full hover:bg-cream"
            >
              <Icon name="arrow" className="h-4 w-4 rotate-180" />
            </button>
            <span>
              {days.length > 0 && `${label(days[0])} – ${Number(days[6].slice(8, 10))}일`}
            </span>
            <button
              type="button"
              aria-label="다음 주"
              onClick={() => setSelected(shift(selected, 7))}
              className="flex h-11 w-11 items-center justify-center rounded-full hover:bg-cream"
            >
              <Icon name="arrow" className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* 건수만 보여주면 「관찰만 있고 일과가 없는 날」을 못 본다. 종류마다 점 색을 나눈다. */}
        <p className="mb-3 flex justify-end gap-4 text-[12px] text-ink-soft">
          <span className="flex items-center gap-1.5">
            <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-primary" />
            관찰
          </span>
          <span className="flex items-center gap-1.5">
            <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-sage-ink" />
            일과
          </span>
        </p>
        <ul className="grid grid-cols-7 gap-2">
          {days.map((iso, index) => {
            const count = countOf(iso);
            const total = count.observations + count.routines;
            const active = iso === selected;
            return (
              <li key={iso}>
                <button
                  type="button"
                  aria-pressed={active}
                  onClick={() => setSelected(iso)}
                  className={`flex w-full flex-col items-center gap-1.5 rounded-md border px-1 py-3 transition-colors ${
                    active
                      ? "border-primary-tint-line bg-primary-tint"
                      : "border-line bg-paper hover:bg-cream"
                  }`}
                >
                  <span className="text-[12px] text-ink-soft">{DAY_NAMES[index]}</span>
                  <span className="font-display text-[22px] font-bold text-ink">
                    {Number(iso.slice(8, 10))}
                  </span>
                  <span aria-hidden="true" className="flex h-1.5 gap-1">
                    {count.observations > 0 && (
                      <span className="h-1.5 w-1.5 rounded-full bg-primary" />
                    )}
                    {count.routines > 0 && (
                      <span className="h-1.5 w-1.5 rounded-full bg-sage-ink" />
                    )}
                  </span>
                  <span className="text-[12px] text-ink-soft">{total ? `${total}건` : "—"}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </section>

      <section className="mt-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <span className="text-sm font-semibold">
            {selected && label(selected)}{" "}
            <span className="ml-1 text-xs font-normal text-ink-soft">{dayCount}건</span>
          </span>
          <div className="flex flex-wrap items-center gap-3">
            {routines ? (
              <Link
                href={routines}
                className="inline-flex min-h-11 items-center gap-2 rounded-md border border-primary-tint-line bg-primary-tint px-3 text-xs font-semibold text-primary-ink"
              >
                <Icon name="edit" className="h-4 w-4" />
                일과 적기
              </Link>
            ) : (
              <span className="text-xs text-ink-soft">{ROUTINES_UNMAPPED}</span>
            )}
            <Link href="/records" className="text-xs font-semibold text-primary">
              전체 기록 →
            </Link>
          </div>
        </div>

        {weekKey && !week ? null : dayCount === 0 ? (
          <p className="rounded-sm border border-line bg-paper p-10 text-center text-xs text-ink-soft shadow-pg-card">
            이 날은 남긴 기록이 없어요.
          </p>
        ) : (
          <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {dayRoutines.map((row) => (
              <li
                key={`routine-${row.id}`}
                className="rounded-sm border border-line bg-paper p-5 shadow-pg-card"
              >
                <div className="flex items-start gap-3">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[14px] bg-sage-tint text-sage-ink">
                    <Icon name="edit" className="h-5 w-5" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <span className="block truncate font-semibold text-ink">{row.class_name}</span>
                    <span className="text-[12px] text-ink-soft">{row.name}</span>
                  </div>
                  <span className="shrink-0 text-[12px] text-ink-soft">
                    {timeRange(row.start, row.end)}
                  </span>
                </div>
                {/* 계획을 대신 띄우지 않는다. 하지 않은 일이 한 일처럼 보인다. */}
                {row.execution ? (
                  <p className="mt-3 text-[13px] leading-relaxed text-ink">{row.execution}</p>
                ) : (
                  <p className="mt-3 text-[13px] text-ink-soft">활동실행을 아직 적지 않았어요.</p>
                )}
                <div className="mt-4 border-t border-line pt-3">
                  <span className="rounded bg-sage-tint px-2 py-1 text-[12px] text-sage-ink">
                    일과 기록
                  </span>
                </div>
              </li>
            ))}
            {dayRecords.map((record) => (
              <li
                key={record.id}
                className="rounded-sm border border-line bg-paper p-5 shadow-pg-card"
              >
                <div className="flex items-start gap-3">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[14px] bg-primary-tint text-primary-ink">
                    <Icon name={DOMAIN_ICON[record.domain] ?? "edit"} className="h-5 w-5" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <span className="block truncate font-semibold text-ink">
                      {record.childName}
                    </span>
                    <span className="text-[12px] text-ink-soft">{record.domain}</span>
                  </div>
                  <span className="shrink-0 text-[12px] text-ink-soft">
                    {localTime(record.createdAt)}
                  </span>
                </div>
                <p className="mt-3 text-[13px] leading-relaxed text-ink">{record.fact}</p>
                <div className="mt-4 border-t border-line pt-3">
                  <span className="rounded bg-primary-tint px-2 py-1 text-[12px] text-primary-ink">
                    관찰 기록
                  </span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </WorkspacePage>
  );
}
