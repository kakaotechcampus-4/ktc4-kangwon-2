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
import { WorkspacePage, JournalTabs, Message, Notice, useClasses, ws } from "./WorkspaceUI";
import WeeklyJournalCard, {
  WeeklyJournalEditor,
  useWeeklyJournal,
  type WeeklyJournal,
} from "./WeeklyJournalCard";
import { Icon, type IconName } from "@/components/app/icons";
import { Posty } from "@/components/app/Posty";
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

/**
 * 「주간 일지 만들기」를 못 누르는 이유. 흐린 단추만 두면 고장으로 읽혀서, 눌렀을 때
 * 스르륵 알림으로 말한다. `null` 이면 누를 수 있다.
 */
function journalBlock(journal: WeeklyJournal) {
  if (journal.doc === undefined)
    return "이번 주 일지를 아직 찾고 있어요. 잠시 뒤 다시 눌러 주세요.";
  if (journal.doc)
    return "이번 주 일지는 이미 만들었어요. 「이번 주 보육일지」 칸에서 이어서 쓰세요.";
  if (journal.busy) return "일지를 만드는 중이에요.";
  if (!journal.sources.length)
    return journal.from === "routine"
      ? "이 주 일과 기록에 「실제로 한 것」이 아직 없어요. 일과 기록을 먼저 적어 주세요."
      : journal.draftDailies.length
        ? `일일 보육일지 ${journal.draftDailies.length}건이 아직 초안이에요. 「이번 주 보육일지」 칸에서 확정하러 가세요.`
        : "이 주에 확정한 일일 보육일지가 없어요. 일지를 확정하거나 근거를 「일과 기록」으로 바꿔 주세요.";
  return null;
}

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

export default function WeeklyRecordsPage() {
  const [loaded, setLoaded] = useState<WeekRecords | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [selected, setSelected] = useClientState(() => today(), "");
  // 서버에만 있는 반을 저장소로 들여오는 일을 겸한다. 반 이름은 주간 일지 칸이 쓴다.
  const classes = useClasses(setError);
  // 반은 사이드바가 정한다. 이 화면은 그 반의 한 주를 편다.
  const [classId] = useClientState(() => chosenClassFor(loadClassSettings())?.id ?? "", "");
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
        error: failed.length
          ? `${failed.join("과 ")}을 불러오지 못했습니다. 새로 고쳐 주세요.`
          : "",
        failedAll: failed.length === 2,
      });
    });
    return () => {
      live = false;
    };
  }, [classId, weekKey, weekStart, weekEnd]);

  const week = loaded?.key === weekKey ? loaded : null;
  const routinesForWeek = week?.routines ?? [];
  const journal = useWeeklyJournal({
    classId,
    weekStart,
    weekEnd,
    routines: routinesForWeek,
  });
  const observations = (week?.observations ?? []).filter((r) => r.classId === classId);
  const routineRows = routinesForWeek;

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
      <WorkspacePage title="보육일지" description="한 주를 펴 놓고 주간 보육일지를 만듭니다.">
        <Message error>{error || week?.error}</Message>
      </WorkspacePage>
    );
  }

  const blocked = journalBlock(journal);
  const todayIso = today();

  return (
    <WorkspacePage
      title="보육일지"
      description="한 주를 펴 놓고 주간 보육일지를 만듭니다."
      action={
        journal.off ? undefined : (
          /* `disabled` 면 눌러도 아무 일이 없어 이유를 말할 수 없다. 눌리게 두고 막는다. */
          <button
            type="button"
            className={ws.primary}
            data-tour="weekly-make"
            aria-disabled={blocked ? true : undefined}
            onClick={() => (blocked ? setNotice(blocked) : journal.make())}
          >
            <Icon name="plus" className="h-4 w-4" />
            {journal.busy ? "만드는 중…" : "주간 일지 만들기"}
          </button>
        )
      }
    >
      <JournalTabs at="weekly" daily={routines ?? "/routines"} weekly="/weekly-records" />
      {/* 왼쪽에서 날을 고르고 오른쪽에 그날을 본다 — 일일 보육일지와 같은 짜임이다. */}
      <div className={ws.grid}>
        <div className={ws.side}>
          <aside className={`${ws.card} ${ws.weekCard}`} data-tour="weekly-week">
            <span aria-hidden="true" className={ws.tape} />
            <div className={ws.weekHead}>
              <button
                type="button"
                aria-label="지난 주"
                className={ws.weekStep}
                onClick={() => setSelected(shift(selected, -7))}
              >
                <Icon name="arrow" className="h-4 w-4 rotate-180" />
              </button>
              <h2 className={ws.weekTitle}>
                {days.length > 0 && `${label(days[0])} – ${Number(days[6].slice(8, 10))}일`}
              </h2>
              <button
                type="button"
                aria-label="다음 주"
                className={ws.weekStep}
                onClick={() => setSelected(shift(selected, 7))}
              >
                <Icon name="arrow" className="h-4 w-4" />
              </button>
            </div>
            {/* 한 주를 수첩처럼 세로로 편다. 건수만 두면 「관찰만 있고 일과가 없는 날」을
                못 보니 종류마다 따로 센다. 빈 날은 점선으로 비워 둔다. */}
            <ul className={ws.weekDays}>
              {days.map((iso, index) => {
                const count = countOf(iso);
                const total = count.observations + count.routines;
                return (
                  <li key={iso}>
                    <button
                      type="button"
                      aria-pressed={iso === selected}
                      className={ws.weekDay}
                      data-empty={total ? undefined : true}
                      data-today={iso === todayIso ? true : undefined}
                      data-weekend={index > 4 ? true : undefined}
                      onClick={() => setSelected(iso)}
                    >
                      <span className={ws.weekDow}>{DAY_NAMES[index]}</span>
                      <span className={ws.weekDate}>{Number(iso.slice(8, 10))}</span>
                      <span className={ws.weekCounts}>
                        {count.routines > 0 && (
                          <span className={ws.weekCount} data-kind="routine">
                            {`일과 ${count.routines}`}
                          </span>
                        )}
                        {count.observations > 0 && (
                          <span className={ws.weekCount} data-kind="observation">
                            {`관찰 ${count.observations}`}
                          </span>
                        )}
                        {!total && <span className={ws.weekNone}>비었어요</span>}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </aside>
          <WeeklyJournalCard
            state={journal}
            className={classes.find((c) => c.id === classId)?.className ?? ""}
            weekStart={weekStart}
            weekEnd={weekEnd}
          />
        </div>

        <section className={ws.stack}>
          <Message error>{week?.error}</Message>
          <div className={ws.weekDayHead}>
            <h2 className={ws.sheetDay}>
              {selected && label(selected)}
              <span>
                {selected &&
                  `${DAY_NAMES[(new Date(selected + "T00:00:00").getDay() + 6) % 7]}요일`}
              </span>
            </h2>
            <span className={ws.weekDayTotal}>{`${dayCount}건`}</span>
            {routines ? (
              <Link href={routines} className={ws.secondary}>
                <Icon name="edit" className="h-4 w-4" />
                일과 적기
              </Link>
            ) : (
              <span className={ws.hint}>{ROUTINES_UNMAPPED}</span>
            )}
          </div>

          {/* 교실 칠판에 그날 쪽지를 붙인 모습 — 일과 기록 화면과 같은 판이다. */}
          <div
            className={`${ws.weekBoard} chalkboard`}
            aria-label="그날 기록"
            data-tour="weekly-board"
          >
            {weekKey && !week ? (
              <p className={ws.weekChalk}>불러오는 중…</p>
            ) : dayCount === 0 ? (
              <div className={ws.weekBlank}>
                <Posty pose="sitWave" face="empty" tone="shell" size={84} wave label={null} />
                <p className={ws.weekChalk}>이 날은 아직 비어 있어요</p>
              </div>
            ) : (
              <>
                {dayRoutines.length > 0 && (
                  <div className={ws.weekGroup}>
                    <h3 className={ws.weekChalk}>
                      일과 기록 <small>{dayRoutines.length}</small>
                    </h3>
                    <ul className={ws.weekSlips}>
                      {dayRoutines.map((row) => (
                        <li
                          key={`routine-${row.id}`}
                          className={ws.weekSlip}
                          data-tone={row.id % 4}
                          data-lean={row.id % 2}
                        >
                          <div className={ws.weekSlipHead}>
                            <b>{row.name}</b>
                            <span>{timeRange(row.start, row.end)}</span>
                          </div>
                          {/* 계획을 대신 띄우지 않는다. 하지 않은 일이 한 일처럼 보인다. */}
                          {row.execution ? (
                            <p className={ws.weekSlipText}>{row.execution}</p>
                          ) : (
                            <p className={ws.weekSlipNone}>실제로 한 것을 아직 적지 않았습니다.</p>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {dayRecords.length > 0 && (
                  <div className={ws.weekGroup}>
                    <h3 className={ws.weekChalk}>
                      관찰 기록 <small>{dayRecords.length}</small>
                    </h3>
                    <ul className={ws.weekSlips}>
                      {dayRecords.map((record) => (
                        <li key={record.id} className={ws.weekIndex}>
                          <div className={ws.weekSlipHead}>
                            <b>{record.childName}</b>
                            <span
                              className={ws.recordDomain}
                              data-tone={DOMAIN_ICON[record.domain]}
                            >
                              <Icon
                                name={DOMAIN_ICON[record.domain] ?? "edit"}
                                className="h-3.5 w-3.5"
                              />
                              {record.domain}
                            </span>
                            <span>{localTime(record.createdAt)}</span>
                          </div>
                          <p className={ws.weekSlipText}>{record.fact}</p>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}
          </div>
          {/* 편집기는 칠판 바로 아래다 — 그 주 기록을 보며 손봐야 한다. */}
          <WeeklyJournalEditor state={journal} />
        </section>
      </div>
      <Notice onDone={() => setNotice("")}>{notice}</Notice>
    </WorkspacePage>
  );
}
