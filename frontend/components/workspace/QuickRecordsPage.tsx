"use client";

/**
 * 기록 모아보기 — 한 주를 한눈에 놓고, 하루를 골라 그날 기록을 본다.
 *
 * 관찰 기록 화면은 아이별로 찾을 때 쓰고, 이 화면은 「이번 주 뭐가 비었지」를 볼 때 쓴다.
 * 그래서 주간 띠가 먼저 오고 목록이 뒤에 온다.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { WorkspacePage, Message } from "./WorkspaceUI";
import { Icon, type IconName } from "@/components/app/icons";
import { listRecords } from "@/lib/api/records";
import type { ServerObservation } from "@/lib/api/observations";
import { today, localTime } from "@/lib/workspace/model";
import { useClientState } from "@/lib/hooks/use-client-state";

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

export default function QuickRecordsPage() {
  const [records, setRecords] = useState<ServerObservation[] | null>(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useClientState(() => today(), "");

  useEffect(() => {
    listRecords()
      .then(setRecords)
      .catch(() => {
        setRecords([]);
        setError("기록을 불러오지 못했어요. 새로고침해주세요.");
      });
  }, []);

  const weekStart = useMemo(() => (selected ? isoOf(mondayOf(selected)) : ""), [selected]);
  const days = useMemo(
    () => (weekStart ? Array.from({ length: 7 }, (_, i) => shift(weekStart, i)) : []),
    [weekStart],
  );
  const countOf = useCallback(
    (iso: string) => (records ?? []).filter((r) => r.date === iso).length,
    [records],
  );
  const dayRecords = (records ?? []).filter((r) => r.date === selected);

  return (
    <WorkspacePage
      title="기록 모아보기"
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
      <Message error>{error}</Message>

      <section className="rounded-sm border border-line bg-paper p-5 shadow-pg-card">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-display text-[26px] font-bold">우리 반 기록</h2>
          <div className="flex items-center gap-3 text-xs text-ink-soft">
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

        <ul className="grid grid-cols-7 gap-2">
          {days.map((iso, index) => {
            const count = countOf(iso);
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
                  <span className="text-[10px] text-ink-soft">{DAY_NAMES[index]}</span>
                  <span className="font-display text-[22px] font-bold text-ink">
                    {Number(iso.slice(8, 10))}
                  </span>
                  <span
                    aria-hidden="true"
                    className={`h-1.5 w-4 rounded-full ${count ? "bg-primary" : "bg-transparent"}`}
                  />
                  <span className="text-[10px] text-ink-soft">{count ? `${count}건` : "—"}</span>
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
            <span className="ml-1 text-xs font-normal text-ink-soft">{dayRecords.length}건</span>
          </span>
          <Link href="/records" className="text-xs font-semibold text-primary">
            전체 기록 →
          </Link>
        </div>

        {records === null ? null : dayRecords.length === 0 ? (
          <p className="rounded-sm border border-line bg-paper p-10 text-center text-xs text-ink-soft shadow-pg-card">
            이 날은 남긴 기록이 없어요.
          </p>
        ) : (
          <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
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
                    <span className="text-[11px] text-ink-soft">{record.domain}</span>
                  </div>
                  <span className="shrink-0 text-[11px] text-ink-soft">
                    {localTime(record.createdAt)}
                  </span>
                </div>
                <p className="mt-3 text-[13px] leading-relaxed text-ink">{record.fact}</p>
                <div className="mt-4 border-t border-line pt-3">
                  <span className="rounded bg-primary-tint px-2 py-1 text-[10px] text-primary-ink">
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
