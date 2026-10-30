"use client";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { Icon, type IconName } from "@/components/app/icons";
import { DOCUMENT_KINDS, localDate, today, type DocumentKind } from "@/lib/workspace/model";
import {
  ARCHIVE_STATUS_LABEL,
  archiveStatus,
  monthLabel,
  journalsInView,
  monthOf,
  openableIn,
  planStatus,
  schoolYearOf,
  shiftDays,
  shiftMonth,
  shortDate,
  weekDays,
  weekIdLabel,
  weekRangeLabel,
  WEEKDAY,
  type ArchiveStatus,
  type JournalView,
} from "@/lib/workspace/document-archive";
import { classServerId } from "@/lib/api/onboarding";
import { listMonthlyPlans } from "@/lib/api/monthly";
import { listWeeklyPlans } from "@/lib/api/weekly";
import type { AnnualPlanSummary, MonthlyPlanSummary, WeeklyPlanSummary } from "@/lib/api/types";
import { ageSelectionLabel, selectedAgesFor, type ClassroomEntry } from "@/lib/onboarding/types";
import type { RecordKind } from "@/lib/api/documents";
import { Message, ws } from "./WorkspaceUI";
import {
  AnnualCover,
  CareArt,
  CareSunArt,
  CareDayDecor,
  CareNotebookArt,
  MonthlyCover,
  ObservationArt,
  OverviewArt,
  SidebarDecor,
  StartArt,
  WeeklyCover,
} from "./DocumentArchiveArt";
import styles from "./DocumentArchive.module.css";
import { PlanArchivePreview, type PlanPreviewTarget } from "./DocumentArchivePreview";

/** 보관함이 목록에 그리는 일지 하나. 상세(sections · sources)는 열어야 온다 (§11). */
export type ArchiveDoc = {
  id: string;
  kind: DocumentKind;
  title: string;
  classId: string;
  childId: string;
  start: string;
  status: "draft" | "confirmed";
  createdAt: string;
  updatedAt: string;
};

type ArchiveType = "annual" | "monthly" | "weekly" | "care" | "observation";

const TYPES: { key: ArchiveType; name: string; desc: string; icon: IconName }[] = [
  { key: "annual", name: "연간 계획안", desc: "한 해의 흐름을 잡아요.", icon: "nature" },
  { key: "monthly", name: "월간 계획안", desc: "이달의 주제를 정해요.", icon: "plan" },
  { key: "weekly", name: "주간 계획안", desc: "한 주의 놀이를 그려요.", icon: "art" },
  { key: "care", name: "보육일지", desc: "하루 일과를 남겨요.", icon: "doc" },
  { key: "observation", name: "관찰일지", desc: "아이의 순간을 적어요.", icon: "record" },
];

function StatusBadge({ state }: { state: ArchiveStatus }) {
  return (
    <span className={styles.status} data-state={state}>
      {ARCHIVE_STATUS_LABEL[state]}
    </span>
  );
}

/** 기간 앞뒤로 움직이는 머리줄. `onPick` 이 있으면 직접 고르기 칸도 띄운다. */
function PeriodNav({
  label,
  onPrev,
  onNext,
  picker,
}: {
  label: string;
  onPrev: () => void;
  onNext: () => void;
  picker?: ReactNode;
}) {
  return (
    <div className={styles.periodBar}>
      <div className={styles.periodNav}>
        <button type="button" aria-label="이전 기간" onClick={onPrev}>
          <Icon name="chevronLeft" />
        </button>
        <strong>{label}</strong>
        <button type="button" aria-label="다음 기간" onClick={onNext}>
          <Icon name="chevron" />
        </button>
      </div>
      {picker}
    </div>
  );
}

function Blank({ art, title, children }: { art: ReactNode; title: string; children: ReactNode }) {
  return (
    <div className={styles.blank}>
      {art}
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}

export default function DocumentArchiveView({
  classes,
  classId,
  onPickClass,
  documents,
  annual,
  activeId,
  editingId,
  onBackToPreview,
  preview,
  onOpen,
  onCloseDetail,
  onCreate,
  detail,
  header,
}: {
  classes: ClassroomEntry[];
  classId: string;
  onPickClass: (id: string) => void;
  documents: ArchiveDoc[];
  annual: AnnualPlanSummary[] | null;
  activeId: string;
  editingId: string;
  onBackToPreview: () => void;
  preview: ReactNode;
  onOpen: (id: string) => void;
  onCloseDetail: () => void;
  onCreate: (kind: RecordKind, options: { date: string; childId?: string }) => void;
  detail: ReactNode;
  /** 페이지 제목 · 설명 · 기존 생성 액션. **오른쪽 본문 안에만** 그린다. */
  header: ReactNode;
}) {
  // 생성 화면에서 돌아오면 선택된 문서에 맞춰 탐색도 시작한다.
  // 이후 목록 탐색은 이 상태를 그대로 쓰므로 다른 종류의 편집기가 끼어들지 않는다.
  const initialDoc = documents.find((d) => d.id === activeId && d.classId === classId);
  const [type, setType] = useState<ArchiveType | null>(() => {
    if (initialDoc?.kind === "observation") return "observation";
    if (initialDoc?.kind === "dailyLog" || initialDoc?.kind === "weeklyLog") return "care";
    return null;
  });
  const [day, setDay] = useState(() => initialDoc?.start ?? today());
  const [month, setMonth] = useState(() => monthOf(initialDoc?.start ?? today()));
  const [schoolYear, setSchoolYear] = useState(() => schoolYearOf(today()));
  const [childId, setChildId] = useState(() =>
    initialDoc?.kind === "observation" ? initialDoc.childId : "",
  );
  const [childSearch, setChildSearch] = useState("");
  const [scope, setScope] = useState<"dailyLog" | "weeklyLog">(() =>
    initialDoc?.kind === "weeklyLog" ? "weeklyLog" : "dailyLog",
  );
  const [oldestFirst, setOldestFirst] = useState(false);
  const [planPreview, setPlanPreview] = useState<PlanPreviewTarget | null>(null);
  const previewRef = useRef<HTMLElement>(null);
  const [mobileList, setMobileList] = useState(false);

  const classroom = classes.find((c) => c.id === classId);
  const serverClassId = classId ? classServerId(classId) : null;

  // 반을 바꾸면 고른 문서 종류 · 아동을 비운다 — 다른 반의 선택이 남으면 섞여 보인다.
  // ref 가 아니라 state 로 비교한다(react-hooks/refs). 렌더 중 setState 는 같은 렌더에서 걷힌다.
  const [seenClass, setSeenClass] = useState(classId);
  if (seenClass !== classId) {
    setSeenClass(classId);
    setPlanPreview(null);
    setType(null);
    setChildId("");
    setChildSearch("");
  }

  const [monthly, setMonthly] = useState<{
    classId: number;
    items: MonthlyPlanSummary[];
    error: string;
  } | null>(null);
  const [weekly, setWeekly] = useState<{
    key: string;
    items: WeeklyPlanSummary[];
    error: string;
  } | null>(null);

  const needMonthly = serverClassId !== null && (type === "monthly" || type === "weekly");
  useEffect(() => {
    if (!needMonthly || serverClassId === null) return;
    let live = true;
    listMonthlyPlans(serverClassId)
      .then(({ items }) => live && setMonthly({ classId: serverClassId, items, error: "" }))
      .catch(
        (e: unknown) =>
          live &&
          setMonthly({
            classId: serverClassId,
            items: [],
            error: e instanceof Error ? e.message : "월간계획안을 불러오지 못했어요.",
          }),
      );
    return () => {
      live = false;
    };
  }, [needMonthly, serverClassId]);

  const weekKey = type === "weekly" && serverClassId !== null ? `${serverClassId}|${month}` : "";
  useEffect(() => {
    if (!weekKey) return;
    let live = true;
    const [cls, ym] = weekKey.split("|");
    listWeeklyPlans(Number(cls), Number(ym.slice(5, 7)))
      .then(({ items }) => live && setWeekly({ key: weekKey, items, error: "" }))
      .catch(
        (e: unknown) =>
          live &&
          setWeekly({
            key: weekKey,
            items: [],
            error: e instanceof Error ? e.message : "주간계획안을 불러오지 못했어요.",
          }),
      );
    return () => {
      live = false;
    };
  }, [weekKey]);

  // 서버 반 번호로 거른다. 반 이름이 같아도 다른 반의 문서가 섞이면 안 된다.
  const annualOfClass = useMemo(
    () => (annual ?? []).filter((p) => serverClassId !== null && p.class_id === serverClassId),
    [annual, serverClassId],
  );
  const monthlyOfClass = useMemo(
    () => (monthly?.classId === serverClassId ? monthly.items : []),
    [monthly, serverClassId],
  );
  const weeklyOfMonth = weekly?.key === weekKey ? weekly.items : [];

  /**
   * 지금 화면이 보여 주는 일지들. **상세는 이 안에 있는 문서만 연다** — 종류 · 반 · 아동 ·
   * 날짜가 어긋난 편집기가 목록 아래에 딸려 나오면 안 된다(보육일지 화면의 관찰일지 편집기).
   */
  const view: JournalView | null =
    type === "observation"
      ? childId
        ? { kind: "observation", classId, childId, day }
        : null
      : type === "care"
        ? scope === "dailyLog"
          ? { kind: "dailyLog", classId, day }
          : { kind: "weeklyLog", classId, month }
        : null;
  const openDoc = openableIn(documents, view, activeId);
  const shownPlan =
    planPreview &&
    planPreview.kind === type &&
    planPreview.classId === serverClassId &&
    planPreview.periodKey === (type === "annual" ? String(schoolYear) : month) &&
    (type === "annual" ? annualOfClass : type === "monthly" ? monthlyOfClass : weeklyOfMonth).some(
      (p) => p.id === planPreview.id,
    )
      ? planPreview
      : null;
  const previewKey = openDoc?.id ?? (shownPlan ? `${shownPlan.kind}:${shownPlan.id}` : "");
  useEffect(() => {
    if (previewKey && !mobileList) previewRef.current?.focus();
  }, [previewKey, mobileList]);

  function openJournal(id: string) {
    setMobileList(false);
    setPlanPreview(null);
    onOpen(id);
  }
  function openPlan(target: PlanPreviewTarget) {
    setMobileList(false);
    onCloseDetail();
    setPlanPreview(target);
  }
  function closePreview() {
    setPlanPreview(null);
    onCloseDetail();
  }

  const days = useMemo(() => weekDays(day), [day]);
  const sorted = <T,>(items: T[]) => (oldestFirst ? [...items].reverse() : items);

  if (!classId || !classroom) {
    return (
      <div className={styles.archive}>
        <ClassRail classes={classes} classId={classId} onPick={onPickClass} />
        <div className={styles.content}>
          {header}
          <Blank art={<StartArt className={styles.blankArt} />} title="반을 선택해 주세요">
            왼쪽에서 반을 선택하면 해당 반의 문서 보관함을 확인할 수 있어요.
          </Blank>
        </div>
      </div>
    );
  }

  const sortButton = (
    <button type="button" className={ws.secondary} onClick={() => setOldestFirst((v) => !v)}>
      {oldestFirst ? "오래된순" : "최신순"}
    </button>
  );

  function annualView() {
    const items = sorted(
      annualOfClass
        .filter((p) => p.school_year === schoolYear)
        .sort((a, b) => b.school_year - a.school_year || b.id - a.id),
    );
    return (
      <>
        <PeriodNav
          label={`${schoolYear}학년도`}
          onPrev={() => setSchoolYear((y) => y - 1)}
          onNext={() => setSchoolYear((y) => y + 1)}
        />
        <PlanGrid
          title="연간 계획안"
          count={items.length}
          hint="학년도별 문서를 확인해 보세요."
          blocked={
            annualOfClass.some((p) => p.school_year === schoolYear)
              ? "이 학년도의 연간계획안이 이미 있어요."
              : ""
          }
          createHref="/plans/annual/new"
          createLabel="새 연간 계획안 작성"
          sort={sortButton}
        >
          {items.map((p, i) => (
            <button
              type="button"
              key={p.id}
              className={styles.docCard}
              aria-pressed={shownPlan?.kind === "annual" && shownPlan.id === p.id}
              onClick={() =>
                openPlan({
                  kind: "annual",
                  id: p.id,
                  classId: p.class_id,
                  className: classroom?.className ?? "",
                  title: `${p.school_year}학년도 연간계획안`,
                  period: `${p.school_year}학년도`,
                  periodKey: String(p.school_year),
                  createdAt: p.created_at,
                  href: `/plans/annual/${p.id}`,
                })
              }
            >
              <div className={styles.cover} data-type="annual">
                <b>{p.school_year}학년도</b>
                <small>{classroom?.className}</small>
                <AnnualCover index={i} className={styles.coverArt} />
              </div>
              <div className={styles.docTitle}>{p.school_year}학년도 연간계획안</div>
              <div className={styles.docFoot}>
                <span>{localDate(p.created_at)}</span>
                <StatusBadge state={planStatus(p.status)} />
              </div>
            </button>
          ))}
        </PlanGrid>
      </>
    );
  }

  function monthlyView() {
    const ym = month;
    const items = sorted(
      monthlyOfClass
        .filter((p) => p.target_month === ym)
        .sort((a, b) => (a.target_month < b.target_month ? 1 : -1)),
    );
    const confirmedAnnual = annualOfClass.some((p) => p.status === "CONFIRMED");
    return (
      <>
        <PeriodNav
          label={monthLabel(ym)}
          onPrev={() => setMonth((m) => shiftMonth(m, -1))}
          onNext={() => setMonth((m) => shiftMonth(m, 1))}
          picker={
            <input
              type="month"
              className={styles.periodDate}
              aria-label="월 선택"
              value={ym}
              onChange={(e) => e.target.value && setMonth(e.target.value)}
            />
          }
        />
        {monthly?.error && <Message error>{monthly.error}</Message>}
        <PlanGrid
          title="월간 계획안"
          count={items.length}
          hint="연간계획안을 바탕으로 작성해요."
          blocked={
            !confirmedAnnual
              ? "연간계획안을 먼저 확정해야 월간계획안을 만들 수 있어요."
              : items.length
                ? "이 달의 월간계획안이 이미 있어요."
                : ""
          }
          createHref="/plans/monthly"
          createLabel="새 월간 계획안 작성"
          sort={sortButton}
        >
          {items.map((p) => (
            <button
              type="button"
              key={p.id}
              className={styles.docCard}
              aria-pressed={shownPlan?.kind === "monthly" && shownPlan.id === p.id}
              onClick={() =>
                openPlan({
                  kind: "monthly",
                  id: p.id,
                  classId: p.class_id,
                  className: classroom?.className ?? "",
                  title: `${p.month}월 월간계획안`,
                  period: p.target_month,
                  periodKey: p.target_month,
                  createdAt: p.created_at,
                  href: `/plans/monthly?plan_id=${p.id}&class_id=${p.class_id}&month=${p.month}`,
                })
              }
            >
              <div className={styles.cover} data-type="monthly">
                <b>{monthLabel(p.target_month)}</b>
                <small>{classroom?.className}</small>
                <MonthlyCover month={p.month} className={styles.coverArt} />
              </div>
              <div className={styles.docTitle}>{p.month}월 월간계획안</div>
              <div className={styles.docFoot}>
                <span>{localDate(p.created_at)}</span>
                <StatusBadge state={planStatus(p.status)} />
              </div>
            </button>
          ))}
        </PlanGrid>
      </>
    );
  }

  function weeklyView() {
    const items = sorted([...weeklyOfMonth].sort((a, b) => (a.week_id < b.week_id ? 1 : -1)));
    const parent = monthlyOfClass.find((p) => p.target_month === month);
    return (
      <>
        <PeriodNav
          label={monthLabel(month)}
          onPrev={() => setMonth((m) => shiftMonth(m, -1))}
          onNext={() => setMonth((m) => shiftMonth(m, 1))}
          picker={
            <input
              type="month"
              className={styles.periodDate}
              aria-label="월 선택"
              value={month}
              onChange={(e) => e.target.value && setMonth(e.target.value)}
            />
          }
        />
        {weekly?.error && <Message error>{weekly.error}</Message>}
        <PlanGrid
          title="주간 계획안"
          count={items.length}
          hint="월간계획안을 바탕으로 작성해요."
          blocked={
            parent?.status === "CONFIRMED"
              ? ""
              : `${monthLabel(month)} 월간계획안을 먼저 확정해야 주간계획안을 만들 수 있어요.`
          }
          createHref="/plans/weekly"
          createLabel="새 주간 계획안 작성"
          sort={sortButton}
        >
          {items.map((p, i) => (
            <button
              type="button"
              key={p.id}
              className={styles.docCard}
              aria-pressed={shownPlan?.kind === "weekly" && shownPlan.id === p.id}
              onClick={() =>
                openPlan({
                  kind: "weekly",
                  id: p.id,
                  classId: p.class_id,
                  className: classroom?.className ?? "",
                  title: `${weekIdLabel(p.week_id)} 주간계획안`,
                  period: p.week_id,
                  periodKey: month,
                  createdAt: p.created_at,
                  href: `/plans/weekly?plan_id=${p.id}&class_id=${p.class_id}&week_id=${p.week_id}`,
                })
              }
            >
              <div className={styles.cover} data-type="weekly">
                {/* 주차는 서버가 준 week_id 를 읽기만 한다 — 화면이 세지 않는다. */}
                <b>{weekIdLabel(p.week_id)}</b>
                <small>{classroom?.className}</small>
                <WeeklyCover index={i} className={styles.coverArt} />
              </div>
              <div className={styles.docTitle}>{weekIdLabel(p.week_id)} 주간계획안</div>
              <div className={styles.docFoot}>
                <span>{localDate(p.created_at)}</span>
                <StatusBadge state={planStatus(p.status)} />
              </div>
            </button>
          ))}
        </PlanGrid>
      </>
    );
  }

  /** 관찰일지는 아동을 고른 뒤 그 아동의 기록을 탐색한다. */
  function observationView() {
    const roster = (classroom?.children ?? []).filter((c) => c.name.includes(childSearch));
    return (
      <section className={`${styles.panel} ${styles.journalPanel}`}>
        <div className={styles.journal}>
          <aside className={styles.roster}>
            <h4>
              {classroom?.className} 아이들 <span>{classroom?.children.length ?? 0}명</span>
            </h4>
            <input
              className={ws.input}
              aria-label="아동 이름 검색"
              placeholder="이름을 검색해 보세요."
              value={childSearch}
              onChange={(e) => setChildSearch(e.target.value)}
            />
            <div className={styles.rosterList}>
              {roster.map((c) => (
                <button
                  type="button"
                  key={c.id}
                  className={styles.childRow}
                  aria-pressed={c.id === childId}
                  onClick={() => {
                    setChildId(c.id);
                    onCloseDetail();
                  }}
                >
                  <span>{c.name}</span>
                  <Icon name="chevron" />
                </button>
              ))}
              {!roster.length && <p className={ws.muted}>찾는 이름이 없어요.</p>}
            </div>
          </aside>
          <div className={styles.journalMain}>{journalContent("observation")}</div>
        </div>
      </section>
    );
  }

  /** 보육일지는 반 · 날짜/월만 고른다. 아동 명단이 없어도 탐색·작성할 수 있다. */
  function careView() {
    return (
      <section className={`${styles.panel} ${styles.journalPanel}`}>
        <div className={styles.journalMain}>{journalContent("care")}</div>
      </section>
    );
  }

  /** 날짜 탐색과 기존 문서 카드만 공유한다. 아동 선택은 관찰일지에만 필요하다. */
  function journalContent(mode: "observation" | "care") {
    const observation = mode === "observation";
    const child = classroom?.children.find((c) => c.id === childId);
    if (observation && !child) {
      return (
        <Blank
          art={<ObservationArt className={styles.blankArt} />}
          title="왼쪽에서 아이를 선택해 주세요"
        >
          선택한 아이의 관찰일지를 확인하고 작성할 수 있어요.
        </Blank>
      );
    }
    const name = observation ? "관찰일지" : "보육일지";
    const weeklyDocs = sorted(
      journalsInView(documents, { kind: "weeklyLog", classId, month }).sort((a, b) =>
        a.start < b.start ? 1 : -1,
      ),
    );
    const byWeek = !observation && scope === "weeklyLog";
    return (
      <>
        <div className={`${styles.panelHead} ${styles.journalHeader}`}>
          <div>
            <div className={styles.journalTitle}>
              <h3>{observation ? child?.name : `${classroom?.className} 보육일지`}</h3>
              {!observation && <CareSunArt className={styles.careSun} />}
            </div>
            <p className={ws.muted}>
              {observation
                ? classroom?.className
                : ageSelectionLabel(selectedAgesFor(classroom ?? {}))}
              {observation && classroom?.ageGroup ? ` · ${classroom.ageGroup}` : ""}
              {!observation && " · 반별 문서"}
            </p>
          </div>
          {!observation && (
            <div className={styles.panelHeadLeft}>
              <div className={styles.scopeTabs}>
                <button
                  type="button"
                  aria-pressed={scope === "dailyLog"}
                  onClick={() => {
                    setScope("dailyLog");
                    onCloseDetail();
                  }}
                >
                  일일
                </button>
                <button
                  type="button"
                  aria-pressed={scope === "weeklyLog"}
                  onClick={() => {
                    setScope("weeklyLog");
                    onCloseDetail();
                  }}
                >
                  주간
                </button>
              </div>
            </div>
          )}
        </div>
        {byWeek ? (
          <>
            <PeriodNav
              label={monthLabel(month)}
              onPrev={() => setMonth((m) => shiftMonth(m, -1))}
              onNext={() => setMonth((m) => shiftMonth(m, 1))}
              picker={sortButton}
            />
            <div className={styles.docGrid}>
              {weeklyDocs.map((d) => (
                <JournalCard
                  key={d.id}
                  doc={d}
                  cover="care"
                  art={<CareArt className={styles.coverArt} />}
                  onOpen={openJournal}
                />
              ))}
              {/* 상단 생성 버튼 대신 같은 생성 진입을 목록 아래에 둔다. */}
              <button
                type="button"
                className={`${styles.addCard} ${styles.journalCreateCard}`}
                onClick={() => onCreate("weeklyLog", { date: day })}
              >
                <CareNotebookArt className={styles.journalCreateArt} />새 주간 보육일지 작성
                <span className={styles.addNote}>
                  확정한 일일 보육일지 또는 일과 기록을 근거로 만들어요.
                </span>
              </button>
            </div>
          </>
        ) : (
          <>
            <PeriodNav
              label={weekRangeLabel(days)}
              onPrev={() => setDay((d) => shiftDays(d, -7))}
              onNext={() => setDay((d) => shiftDays(d, 7))}
              picker={
                <input
                  type="date"
                  className={styles.periodDate}
                  aria-label="날짜 선택"
                  value={day}
                  onChange={(e) => e.target.value && setDay(e.target.value)}
                />
              }
            />
            <Legend />
            <DayStrip
              days={days}
              day={day}
              onPickDay={setDay}
              onOpen={openJournal}
              cover={observation ? "observation" : "care"}
              art={
                observation ? (
                  <ObservationArt className={styles.coverArt} />
                ) : (
                  <CareArt className={styles.coverArt} />
                )
              }
              emptyHint={
                observation
                  ? "이 날짜에 작성된 관찰일지가 없어요."
                  : "일과 기록을 확인한 뒤 작성해 보세요."
              }
              createLabel={`이 날짜 ${name} 작성`}
              onCreate={() =>
                observation
                  ? onCreate("observation", { date: day, childId })
                  : onCreate("dailyLog", { date: day })
              }
              docsFor={(date) =>
                observation
                  ? journalsInView(documents, {
                      kind: "observation",
                      classId,
                      childId,
                      day: date,
                    })
                  : journalsInView(documents, { kind: "dailyLog", classId, day: date })
              }
            />
          </>
        )}
      </>
    );
  }

  /** 문서 종류 다섯 칸. 상세 화면에서는 그리지 않는다. */
  function typeGrid() {
    return (
      <div className={styles.typeGrid}>
        {TYPES.map((t) => (
          <button
            type="button"
            key={t.key}
            className={styles.typeCard}
            data-type={t.key}
            // 설명까지 이름에 섞이면 「보육일지 작성」 단추와 구분이 안 된다.
            aria-label={t.name}
            aria-pressed={type === t.key}
            onClick={() => {
              setType(t.key);
              setPlanPreview(null);
              onCloseDetail();
            }}
          >
            <Icon name={t.icon} />
            <strong>{t.name}</strong>
            <small>{t.desc}</small>
          </button>
        ))}
      </div>
    );
  }

  return (
    <div className={styles.archive}>
      <ClassRail classes={classes} classId={classId} onPick={onPickClass} />
      <div className={styles.content}>
        {header}
        {openDoc && editingId === openDoc.id ? (
          <>
            <button
              type="button"
              className={styles.backLink}
              onClick={() => {
                onBackToPreview();
                setMobileList(true);
              }}
            >
              ← 문서 목록으로 돌아가기
            </button>
            {detail}
          </>
        ) : (
          <>
            {typeGrid()}
            <div
              className={styles.split}
              data-preview={Boolean(previewKey)}
              data-selected={Boolean(previewKey) && !mobileList}
            >
              <div className={styles.browser}>
                {type === null && (
                  <Blank
                    art={<OverviewArt className={styles.blankArt} />}
                    title="문서를 선택해 주세요"
                  >
                    위의 문서 종류를 선택하면 해당 문서 목록을 확인할 수 있어요.
                  </Blank>
                )}
                {type === "annual" && annualView()}
                {type === "monthly" && monthlyView()}
                {type === "weekly" && weeklyView()}
                {type === "care" && careView()}
                {type === "observation" && observationView()}
              </div>
              {previewKey && (
                <aside
                  className={styles.previewPanel}
                  aria-label="문서 미리보기"
                  tabIndex={-1}
                  ref={previewRef}
                >
                  <button type="button" className={styles.backLink} onClick={closePreview}>
                    목록으로
                  </button>
                  {openDoc && preview}
                  {shownPlan && (
                    <PlanArchivePreview
                      key={`${shownPlan.kind}:${shownPlan.id}`}
                      target={shownPlan}
                    />
                  )}
                </aside>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

/** 연간 · 월간 · 주간 공통 카드 그리드. */
function PlanGrid({
  title,
  count,
  hint,
  blocked,
  createHref,
  createLabel,
  children,
  sort,
}: {
  title: string;
  count: number;
  hint: string;
  blocked: string;
  createHref: string;
  createLabel: string;
  children: ReactNode;
  sort: ReactNode;
}) {
  return (
    <section className={styles.panel}>
      <div className={styles.panelHead}>
        <div className={styles.panelHeadLeft}>
          <h3>{title}</h3>
          <span className={ws.badge}>{count}개</span>
        </div>
        <div className={styles.panelHeadLeft}>
          <span className={ws.muted}>{hint}</span>
          {sort}
        </div>
      </div>
      <div className={styles.docGrid}>
        {blocked ? (
          <button type="button" className={styles.addCard} disabled>
            <span className={styles.plus}>
              <Icon name="plus" />
            </span>
            {createLabel}
            <span className={styles.addNote}>{blocked}</span>
          </button>
        ) : (
          <Link className={styles.addCard} href={createHref}>
            <span className={styles.plus}>
              <Icon name="plus" />
            </span>
            {createLabel}
          </Link>
        )}
        {children}
      </div>
    </section>
  );
}

/** 날짜 한 줄 + 그 날짜의 문서. 관찰일지 · 보육일지가 같이 쓴다. */
function DayStrip({
  days,
  day,
  onPickDay,
  docsFor,
  onOpen,
  cover,
  art,
  emptyHint,
  createLabel,
  onCreate,
}: {
  days: string[];
  day: string;
  onPickDay: (date: string) => void;
  docsFor: (date: string) => ArchiveDoc[];
  onOpen: (id: string) => void;
  /** 표지 색 — 보육일지와 관찰일지가 다른 그림을 쓴다. */
  cover: "care" | "observation";
  art: ReactNode;
  emptyHint: string;
  createLabel: string;
  onCreate: () => void;
}) {
  const picked = docsFor(day);
  return (
    <>
      <div
        className={styles.dayStrip}
        role="group"
        aria-label={`${cover === "care" ? "보육일지" : "관찰일지"} 주간 달력`}
      >
        {days.map((d, i) => {
          const found = docsFor(d);
          // 한 날짜에 여러 장이면 가장 센 상태를 표시하고, 아래 카드에서 각각 확인한다.
          // 한 날짜에 여러 장이면 아직 검토 중인 것이 있는지만 본다.
          const state = !found.length
            ? "none"
            : found.some((x) => archiveStatus(x) === "draft")
              ? "draft"
              : "confirmed";
          return (
            <button
              type="button"
              key={d}
              className={styles.day}
              aria-pressed={d === day}
              onClick={() => onPickDay(d)}
            >
              <span className={styles.date}>{shortDate(d)}</span>
              <span className={styles.dow}>{WEEKDAY[i]}</span>
              <span className={styles.mark} data-state={state}>
                {state === "none" ? null : <Icon name="check" />}
              </span>
              <span className={styles.state}>{ARCHIVE_STATUS_LABEL[state]}</span>
              <CareDayDecor variant={i} className={styles.dayDecor} />
            </button>
          );
        })}
      </div>
      <div className={styles.docGrid} style={{ marginTop: 12 }}>
        {picked.map((d) => (
          <JournalCard key={d.id} doc={d} cover={cover} art={art} onOpen={onOpen} />
        ))}
        {/* 없는 문서의 가짜 카드를 만들지 않는다 — 대신 그 날짜로 새로 쓰는 길을 연다. */}
        {!picked.length && (
          <button
            type="button"
            className={`${styles.addCard} ${styles.journalCreateCard}`}
            onClick={onCreate}
          >
            <CareNotebookArt className={styles.journalCreateArt} />
            {createLabel}
            <span className={styles.addNote}>{emptyHint}</span>
          </button>
        )}
      </div>
    </>
  );
}

/** 보육일지 · 관찰일지 문서 카드. 계획안 카드와 같은 틀을 쓴다. */
function JournalCard({
  doc,
  cover,
  art,
  onOpen,
}: {
  doc: ArchiveDoc;
  cover: "care" | "observation";
  art: ReactNode;
  onOpen: (id: string) => void;
}) {
  const state = archiveStatus(doc);
  return (
    <button
      type="button"
      className={styles.docCard}
      data-state={state}
      onClick={() => onOpen(doc.id)}
    >
      <div className={styles.cover} data-type={cover}>
        <b>{doc.start}</b>
        <small>{DOCUMENT_KINDS[doc.kind]}</small>
        {art}
      </div>
      <div className={styles.docTitle}>{doc.title}</div>
      <div className={styles.docFoot}>
        {/* 상태를 화면이 계산하지 않는다 — 서버가 준 status · stale 로만 정한다. */}
        <span>{doc.updatedAt ? localDate(doc.updatedAt) : ""}</span>
        <StatusBadge state={state} />
      </div>
      <div className={styles.cardAction}>
        {state === "draft" ? "이어서 작성하기 →" : "문서 열기 →"}
      </div>
    </button>
  );
}

function Legend() {
  return (
    <div className={styles.legend}>
      {(["confirmed", "draft", "none"] as ArchiveStatus[]).map((s) => (
        <span key={s}>
          <i data-state={s} />
          {ARCHIVE_STATUS_LABEL[s]}
        </span>
      ))}
    </div>
  );
}

/** 문서 보관함 안쪽 반 선택. **전역 사이드바(AppSidebar)를 대신하지 않는다.** */
function ClassRail({
  classes,
  classId,
  onPick,
}: {
  classes: ClassroomEntry[];
  classId: string;
  onPick: (id: string) => void;
}) {
  return (
    <aside className={styles.classRail} aria-label="반 선택">
      <div className={styles.railHead}>
        <Icon name="users" />
        우리 반
      </div>
      {classes.length ? (
        <div className={styles.classList}>
          {classes.map((c) => (
            <button
              type="button"
              key={c.id}
              className={styles.classCard}
              aria-pressed={c.id === classId}
              onClick={() => onPick(c.id)}
            >
              <span className={styles.grow}>{c.className || "이름 없는 반"}</span>
              <Icon name="chevron" />
            </button>
          ))}
        </div>
      ) : (
        <p className={styles.railEmpty}>등록된 반이 없어요. 설정에서 반을 먼저 만들어주세요.</p>
      )}
      <SidebarDecor className={styles.decor} />
    </aside>
  );
}
