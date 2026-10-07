"use client";

/**
 * 우리 반 — 작업실 첫 화면.
 *
 * 교사가 하루에 제일 많이 하는 일이 「방금 본 걸 한 줄 적기」라서 그 칸이 맨 위에 온다.
 * 아래는 적은 것이 어떻게 쌓였는지 — 아이별 · 영역별 · 오늘 목록.
 *
 * 관찰 기록은 서버에 저장된다(`addRecord`). 일과 기록(반 전체 이야기)은 아직
 * 테이블이 없어서 이 화면에 칸을 두지 않았다 — 적을 수 있는데 사라지는 게 더 나쁘다.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { PageContainer } from "@/components/app/AppLayout";
import { Icon } from "@/components/app/icons";
import { useClasses } from "@/components/workspace/WorkspaceUI";
import { listRecords, addRecord } from "@/lib/api/records";
import type { ServerObservation } from "@/lib/api/observations";
import { DOMAINS, today } from "@/lib/workspace/model";
import { loadClassSettings, primaryClassFor } from "@/lib/onboarding/settings";
import { AGE_LABEL, type AgeGroup } from "@/lib/plan-generator/types";
import { formatKoreanDate } from "@/lib/greeting";
import { useClientState } from "@/lib/hooks/use-client-state";

const PRIMARY =
  "inline-flex min-h-11 items-center justify-center gap-2 rounded-md border border-primary-line " +
  "bg-primary px-4 text-xs font-semibold text-white shadow-pg-card transition-colors " +
  "hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-40";
const CARD = "border border-line bg-paper p-5 shadow-pg-card";

/** 어린이집 학사 연도는 3월에 시작한다. 1·2월은 아직 지난해 학년도다. */
const schoolYear = (date: Date) =>
  date.getMonth() + 1 >= 3 ? date.getFullYear() : date.getFullYear() - 1;

export default function HomePage() {
  const [message, setMessage] = useState("");
  const onError = useCallback((m: string) => setMessage(m), []);
  const classes = useClasses(onError);
  const [records, setRecords] = useState<ServerObservation[] | null>(null);
  const [todayDate] = useClientState(() => today(), "");

  const reload = useCallback(() => {
    listRecords()
      .then(setRecords)
      .catch(() => {
        setRecords([]);
        setMessage("기록을 불러오지 못했어요. 새로고침해주세요.");
      });
  }, []);
  useEffect(reload, [reload]);

  const [room] = useClientState(
    () => {
      const klass = primaryClassFor(loadClassSettings());
      return {
        className: klass?.className ?? "",
        age: klass?.ageGroup ? AGE_LABEL[klass.ageGroup as AgeGroup] : "",
        year: schoolYear(new Date()),
      };
    },
    { className: "", age: "", year: schoolYear(new Date()) },
  );

  const todayRecords = useMemo(
    () => (records ?? []).filter((r) => r.date === todayDate),
    [records, todayDate],
  );
  const subtitle = [room.className, room.age, `${room.year}학년도`].filter(Boolean).join(" · ");

  return (
    <PageContainer>
      <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-[34px] font-bold leading-tight text-ink lg:text-[44px]">
            우리 반
          </h1>
          <p className="mt-1 text-xs text-ink-soft">{subtitle}</p>
        </div>
        <span className="flex items-center gap-2 text-xs text-ink-soft">
          <Icon name="plan" className="h-4 w-4" />
          {todayDate && formatKoreanDate(new Date(todayDate))}
        </span>
      </div>

      {message && (
        <p role="alert" className="mb-5 rounded-md border border-line bg-paper px-4 py-3 text-xs">
          {message}
        </p>
      )}

      <Compose
        classes={classes}
        date={todayDate}
        className={room.className}
        onSaved={reload}
        onError={setMessage}
        todayCount={todayRecords.length}
      />

      <div className="mt-8 grid items-start gap-6 md:grid-cols-2">
        <ChildSpotlight classes={classes} records={records ?? []} />
        <DomainBoard records={todayRecords} />
      </div>

      <TodayList records={todayRecords} loading={records === null} />
    </PageContainer>
  );
}

type Classroom = ReturnType<typeof useClasses>[number];

/** 지금, 한 줄 기록 — 아이 하나와 영역 하나를 고르고 본 그대로 적는다. */
function Compose({
  classes,
  date,
  className,
  todayCount,
  onSaved,
  onError,
}: {
  classes: Classroom[];
  date: string;
  className: string;
  todayCount: number;
  onSaved: () => void;
  onError: (m: string) => void;
}) {
  const withChildren = classes.filter((c) => c.children.length > 0);
  const [classId, setClassId] = useState("");
  const [childId, setChildId] = useState("");
  const [domain, setDomain] = useState(DOMAINS[0]);
  const [fact, setFact] = useState("");
  const [busy, setBusy] = useState(false);

  // 반·아동은 늦게 도착한다. 그때 useState 를 맞추는 대신 그릴 때 첫 항목으로 떨어뜨린다 —
  // effect 안에서 setState 하면 렌더가 한 번 더 돈다.
  const classroom = withChildren.find((c) => c.id === classId) ?? withChildren[0];
  const activeClassId = classroom?.id ?? "";
  const activeChildId =
    classroom?.children.find((c) => c.id === childId)?.id ?? classroom?.children[0]?.id ?? "";

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!fact.trim() || !activeClassId || !activeChildId || busy) return;
    setBusy(true);
    try {
      await addRecord({
        classId: activeClassId,
        childId: activeChildId,
        date,
        domain,
        context: "",
        fact: fact.trim(),
      });
      setFact("");
      onSaved();
    } catch (e) {
      onError(e instanceof Error ? e.message : "기록을 저장하지 못했어요.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-[24px] font-bold text-ink lg:text-[29px]">
          지금, 한 줄 기록
        </h2>
        <span className="text-[11px] text-ink-soft">
          {date.slice(5).replace("-", "월 ")}일{className && ` · ${className}`}
        </span>
      </div>

      {withChildren.length === 0 ? (
        <div className={`${CARD} text-center text-xs text-ink-soft`}>
          아이를 먼저 등록해 주세요.{" "}
          <Link href="/onboarding/children" className="font-semibold text-primary underline">
            아동 명단으로 가기
          </Link>
        </div>
      ) : (
        <form onSubmit={submit} className={CARD}>
          <div className="flex flex-wrap gap-2.5">
            <select
              aria-label="반"
              value={activeClassId}
              onChange={(e) => {
                setClassId(e.target.value);
                setChildId("");
              }}
              className="min-h-11 rounded-md border border-line bg-cream px-3 text-xs"
            >
              {withChildren.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.className}
                </option>
              ))}
            </select>
            <select
              aria-label="아이"
              value={activeChildId}
              onChange={(e) => setChildId(e.target.value)}
              className="min-h-11 rounded-md border border-line bg-cream px-3 text-xs"
            >
              {classroom?.children.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <select
              aria-label="관찰 영역"
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              className="min-h-11 rounded-md border border-line bg-cream px-3 text-xs"
            >
              {DOMAINS.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </div>

          <textarea
            aria-label="빠른 기록 내용"
            value={fact}
            onChange={(e) => setFact(e.target.value)}
            rows={3}
            placeholder="아이 A가 도토리를 크기별로 줄 세웠다."
            className="mt-3 w-full resize-y rounded-md border border-line bg-cream px-3 py-3 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary-tint"
          />

          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            {/* 해석·지원은 여기서 받지 않는다. 본 그대로만 남기고, 해석은 일지를 쓸 때 더한다. */}
            <span className="text-[11px] text-ink-soft">
              본 그대로 적어 주세요. 원문은 그대로 보관해요.
            </span>
            <button type="submit" disabled={!fact.trim() || busy} className={PRIMARY}>
              {busy ? "남기는 중" : "기록 남기기"}
            </button>
          </div>
        </form>
      )}

      <div className="mt-4 flex items-center justify-between gap-3 border-t border-line pt-4">
        <span className="text-xs text-ink-soft">
          오늘 남긴 기록 <strong className="text-ink">{todayCount}</strong>건
        </span>
        <Link
          href="/records"
          className="inline-flex min-h-11 items-center gap-2 rounded-md border border-primary-tint-line bg-primary-tint px-3 text-xs font-semibold text-primary-ink"
        >
          관찰 기록으로 가기
          <Icon name="arrow" className="h-4 w-4" />
        </Link>
      </div>
    </section>
  );
}

/** 한 아이, 조금 더 가까이 — 한 명씩 넘겨 보며 최근 관찰을 확인한다. */
function ChildSpotlight({
  classes,
  records,
}: {
  classes: Classroom[];
  records: ServerObservation[];
}) {
  const children = classes.flatMap((c) => c.children);
  const [index, setIndex] = useState(0);
  const child = children[index % Math.max(children.length, 1)];
  const latest = records.find((r) => r.childId === child?.id);

  return (
    <section className="relative border border-note-line bg-note p-5 shadow-pg-card">
      <span
        aria-hidden="true"
        className="pointer-events-none absolute -top-3 left-1/2 h-6 w-20 -translate-x-1/2 -rotate-3 border-x border-white/50 bg-paper/70"
      />
      <span className="text-[11px] font-semibold text-sun-ink">한 아이, 조금 더 가까이</span>

      {!child ? (
        <p className="mt-4 text-xs text-sun-ink">아직 등록된 아이가 없어요.</p>
      ) : (
        <>
          <div className="mt-3 flex items-center gap-3">
            <span className="flex h-12 w-12 items-center justify-center rounded-[18px_14px_20px_12px] border border-note-line bg-paper font-display text-[26px] font-bold text-sun-ink">
              {child.name.slice(0, 1)}
            </span>
            <div>
              <h3 className="font-display text-[26px] font-bold text-ink">{child.name}</h3>
              <span className="text-[10px] text-sun-ink">최근 관찰</span>
            </div>
          </div>

          <div className="mt-5 border-t border-note-line pt-4">
            <span className="flex items-center gap-2 text-[11px] font-semibold text-sun-ink">
              {latest?.domain || "최근 관찰"}
              <span className="ml-auto font-normal">
                {latest ? latest.date.slice(5).replace("-", ".") : ""}
              </span>
            </span>
            <p className="mt-2 text-[13px] leading-[1.9] text-ink">
              {latest?.fact || "아직 남긴 관찰 기록이 없어요."}
            </p>
          </div>

          <div className="mt-4 flex items-center justify-between gap-2">
            <Link
              href="/records"
              className="flex min-h-11 items-center gap-1 text-[11px] font-semibold text-sun-ink"
            >
              이 아이 기록 보기
              <Icon name="arrow" className="h-3 w-3" />
            </Link>
            <div className="flex items-center gap-1">
              <button
                type="button"
                aria-label="이전 아이"
                onClick={() => setIndex((p) => (p - 1 + children.length) % children.length)}
                className="flex h-11 w-11 items-center justify-center rounded-full hover:bg-white/60"
              >
                <Icon name="arrow" className="h-4 w-4 rotate-180" />
              </button>
              <span className="text-[10px] text-sun-ink">
                {(index % children.length) + 1}/{children.length}
              </span>
              <button
                type="button"
                aria-label="다음 아이"
                onClick={() => setIndex((p) => (p + 1) % children.length)}
                className="flex h-11 w-11 items-center justify-center rounded-full hover:bg-white/60"
              >
                <Icon name="arrow" className="h-4 w-4" />
              </button>
            </div>
          </div>
        </>
      )}
    </section>
  );
}

/** 우리 반 한눈에 — 오늘 어느 영역이 비었는지. 평가에서 영역 하나가 비면 바로 걸린다. */
function DomainBoard({ records }: { records: ServerObservation[] }) {
  return (
    <section className={CARD}>
      <h3 className="font-display text-[22px] font-bold text-ink">우리 반 한눈에</h3>
      <p className="mt-1 text-[11px] text-ink-soft">오늘 남긴 관찰 영역</p>
      <ul className="mt-4 grid grid-cols-5 gap-2 text-center">
        {DOMAINS.map((domain) => {
          const count = records.filter((r) => r.domain === domain).length;
          return (
            <li key={domain} className="flex flex-col items-center gap-1.5">
              <span
                className={`flex h-12 w-12 items-center justify-center rounded-[18px] font-display text-lg ${
                  count ? "bg-primary-tint text-primary-ink" : "bg-cream text-ink-soft"
                }`}
              >
                {count || "—"}
              </span>
              <span className="text-[10px] leading-tight text-ink-soft">{domain}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function TodayList({ records, loading }: { records: ServerObservation[]; loading: boolean }) {
  if (loading) return null;
  return (
    <section className="mt-8">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h3 className="font-display text-[22px] font-bold text-ink">
          오늘 기록 <span className="text-primary">{records.length}</span>건
        </h3>
        <Link href="/records" className="text-xs font-semibold text-primary">
          전체 기록 →
        </Link>
      </div>
      {records.length === 0 ? (
        <p className={`${CARD} text-center text-xs text-ink-soft`}>
          오늘은 아직 기록이 없어요. 위에 한 줄 남겨 보세요.
        </p>
      ) : (
        <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {records.map((record) => (
            <li key={record.id} className={CARD}>
              <div className="flex items-start justify-between gap-2">
                <span className="font-semibold text-ink">{record.childName}</span>
                <span className="shrink-0 rounded-full bg-primary-tint px-2 py-0.5 text-[10px] text-primary-ink">
                  {record.domain}
                </span>
              </div>
              <p className="mt-2 text-[13px] leading-relaxed text-ink">{record.fact}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
