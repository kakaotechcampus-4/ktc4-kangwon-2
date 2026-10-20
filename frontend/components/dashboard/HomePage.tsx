"use client";

/**
 * 우리 반 — 작업실 첫 화면.
 *
 * 교사가 하루에 제일 많이 하는 일이 「방금 본 걸 한 줄 적기」라서 그 칸이 맨 위에 온다.
 * 아래는 적은 것이 어떻게 쌓였는지 — 아이별 · 영역별 · 오늘 목록.
 *
 * 관찰 기록은 서버에 저장된다(`addRecord`). 반 전체 일과는 오늘 일과 적기에서 입력한다.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { PageContainer } from "@/components/app/AppLayout";
import { Icon, type IconName } from "@/components/app/icons";
import { useClasses } from "@/components/workspace/WorkspaceUI";
import { listRecords, addRecord } from "@/lib/api/records";
import type { ServerObservation } from "@/lib/api/observations";
import { DOMAINS, today } from "@/lib/workspace/model";
import { loadClassSettings, primaryClassFor } from "@/lib/onboarding/settings";
import { routinesPath, routinesScope } from "@/lib/workspace/routines-route";
import { classServerId } from "@/lib/api/onboarding";
import { AGE_LABEL, type AgeGroup } from "@/lib/plan-generator/types";
import { formatKoreanDate } from "@/lib/greeting";
import { useClientState } from "@/lib/hooks/use-client-state";
import { useDictation } from "@/lib/hooks/use-dictation";

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

  /**
   * 홈이 **지금 보여 주는 반**. 빠른 기록이 저장하는 반과 **같은 값**이어야 한다.
   *
   * 예전에는 `listRecords()` 를 인자 없이 불렀다. 반을 한 번도 고른 적 없는 한 반짜리 계정은
   * 주 반이 비어 있어 조회가 `[]` 로 끝났고, 저장은 성공했는데 홈이 0건으로 보였다.
   * 그렇다고 반 없이 기관 전체를 조회하면 FR-405 를 어긴다 — **보고 있는 반을 짚어서 묻는다.**
   */
  const [entry] = useClientState(
    () => ({
      classId: typeof window === "undefined" ? null : routinesScope(window.location.search).classId,
      primaryId: primaryClassFor(loadClassSettings())?.id ?? "",
    }),
    { classId: null as number | null, primaryId: "" },
  );
  const [pickedClass, setPickedClass] = useState<string | null>(null);
  // URL의 반이 아직 도착하지 않았으면 다른 반으로 대체하지 않는다.
  const activeClass =
    pickedClass !== null
      ? classes.find((c) => c.id === pickedClass)
      : entry.classId !== null
        ? classes.find((c) => classServerId(c.id) === entry.classId)
        : (classes.find((c) => c.id === entry.primaryId) ?? classes[0]);
  const activeClassId = activeClass?.id ?? "";
  const pickClass = (id: string) => {
    setPickedClass(id);
    const serverId = classServerId(id);
    if (serverId === null) return;
    const params = new URLSearchParams(window.location.search);
    params.set("class_id", String(serverId));
    // 홈으로 뒤로 왔을 때도 같은 반. 반 선택만으로 history를 늘리지 않는다.
    window.history.replaceState(null, "", `?${params}`);
  };

  /** 반을 바꾸는 사이 돌아온 옛 응답이 지금 반의 목록을 덮지 않게 한다. */
  const visit = useRef(0);
  const [recordsRevision, setRecordsRevision] = useState(0);
  // 저장 시작 당시의 반을 닫아 두지 않는다. 완료 시점에 보고 있는 반을 다시 읽는다.
  const recordSaved = useCallback(() => setRecordsRevision((revision) => revision + 1), []);
  const reload = useCallback(() => {
    const at = (visit.current += 1);
    // 반이 아직 안 붙었으면 묻지 않는다. 서버 반이 늦게 도착하면 deps 가 바뀌어 다시 돈다.
    const asked = activeClassId ? listRecords(activeClassId) : Promise.resolve([]);
    asked
      .then((rows) => {
        if (at === visit.current) setRecords(rows);
      })
      .catch(() => {
        if (at !== visit.current) return;
        setRecords([]);
        setMessage("기록을 불러오지 못했어요. 새로고침해주세요.");
      });
  }, [activeClassId]);
  useEffect(() => {
    reload();
  }, [reload, recordsRevision]);

  const [year] = useClientState(() => schoolYear(new Date()), schoolYear(new Date()));
  const className = activeClass?.className ?? "";
  const age = activeClass?.ageGroup ? AGE_LABEL[activeClass.ageGroup as AgeGroup] : "";
  const routines = activeClassId && todayDate ? routinesPath(activeClassId, todayDate) : null;
  // 반이 바뀐 직후, 새 응답 전에도 이전 반 기록을 그리지 않는다.
  const classRecords = (records ?? []).filter((r) => r.classId === activeClassId);
  const todayRecords = useMemo(
    () => (records ?? []).filter((r) => r.classId === activeClassId && r.date === todayDate),
    [records, activeClassId, todayDate],
  );
  const subtitle = [className, age, `${year}학년도`].filter(Boolean).join(" · ");

  return (
    <PageContainer>
      <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-[34px] font-bold leading-tight text-ink lg:text-[44px]">
            우리 반
          </h1>
          <p aria-label="현재 반" className="mt-1 text-xs text-ink-soft">
            {subtitle}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <span className="flex items-center gap-2 text-xs text-ink-soft">
            <Icon name="plan" className="h-4 w-4" />
            {todayDate && formatKoreanDate(new Date(todayDate))}
          </span>
          {routines && (
            <Link
              href={routines}
              className="inline-flex min-h-11 items-center gap-2 rounded-md border border-primary-tint-line bg-primary-tint px-3 text-xs font-semibold text-primary-ink"
            >
              오늘 일과 적기
              <Icon name="arrow" className="h-4 w-4" />
            </Link>
          )}
        </div>
      </div>

      {message && (
        <p role="alert" className="mb-5 rounded-md border border-line bg-paper px-4 py-3 text-xs">
          {message}
        </p>
      )}

      <Compose
        classes={classes}
        date={todayDate}
        className={className}
        activeClassId={activeClassId}
        onPickClass={pickClass}
        onSaved={recordSaved}
        onError={setMessage}
        todayCount={todayRecords.length}
      />

      <div className="mt-8 grid items-start gap-6 md:grid-cols-2">
        <ChildSpotlight classes={activeClass ? [activeClass] : []} records={classRecords} />
        <DomainBoard records={todayRecords} />
      </div>

      <TodayList records={todayRecords} loading={records === null} />
    </PageContainer>
  );
}

type Classroom = ReturnType<typeof useClasses>[number];

/**
 * 지금, 한 줄 기록 — 본 그대로 먼저 적고, 누구 이야기인지는 그 다음에 고른다.
 *
 * 순서가 중요하다. 아이·영역을 먼저 고르게 하면 적기도 전에 분류부터 해야 해서,
 * 교실에서 손이 바쁠 때 그냥 안 적게 된다.
 */
function Compose({
  classes,
  date,
  className,
  todayCount,
  activeClassId,
  onPickClass,
  onSaved,
  onError,
}: {
  classes: Classroom[];
  date: string;
  className: string;
  todayCount: number;
  /** 홈이 정한 지금 반. 홈의 조회와 같은 값이라 통계와 저장 대상이 어긋나지 않는다. */
  activeClassId: string;
  onPickClass: (id: string) => void;
  onSaved: () => void;
  onError: (m: string) => void;
}) {
  const withChildren = classes.filter((c) => c.children.length > 0);
  const [childId, setChildId] = useState("");
  const [domain, setDomain] = useState(DOMAINS[0]);
  const [fact, setFact] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  // 받아쓴 말은 적던 글 뒤에 붙인다. 덮어쓰면 쓰던 걸 잃는다.
  const dictation = useDictation((said) => setFact((prev) => (prev ? `${prev} ${said}` : said)));

  // 반·아동은 늦게 도착한다. 그때 useState 를 맞추는 대신 그릴 때 첫 항목으로 떨어뜨린다 —
  // effect 안에서 setState 하면 렌더가 한 번 더 돈다. 반을 고르는 규칙은 홈에 하나만 둔다.
  const classroom = classes.find((c) => c.id === activeClassId);
  const child = classroom?.children.find((c) => c.id === childId) ?? classroom?.children[0];

  async function save() {
    if (!fact.trim() || !activeClassId || !child || busy) return;
    setBusy(true);
    try {
      await addRecord({
        classId: activeClassId,
        childId: child.id,
        date,
        domain,
        context: "",
        fact: fact.trim(),
      });
      setFact("");
      setConfirming(false);
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

      {!classroom?.children.length ? (
        <div className={`${CARD} text-center text-xs text-ink-soft`}>
          아이를 먼저 등록해 주세요.{" "}
          <Link href="/onboarding/children" className="font-semibold text-primary underline">
            아동 명단으로 가기
          </Link>
        </div>
      ) : (
        <>
          <div className="overflow-hidden rounded-sm border border-line bg-paper shadow-pg-hard">
            <div className="flex items-center justify-between gap-2 border-b border-paper-warm-line bg-paper-warm px-4 py-3">
              <span className="flex items-center gap-2 text-[11px] text-ink-soft">
                <Icon name="edit" className="h-3.5 w-3.5" />
                {classroom?.className} · 본 말과 행동
              </span>
              <span className="text-[10px] text-ink-soft">아이 한 명씩 남겨요</span>
            </div>
            <textarea
              aria-label="빠른 기록 내용"
              value={fact}
              disabled={confirming}
              onChange={(e) => setFact(e.target.value)}
              placeholder={
                "바깥놀이에서 아이 A가 도토리를 크기별로 줄 세웠다.\n" +
                "친구가 와서 같이 세었고, 교사는 옆에서 지켜보았다."
              }
              className="block min-h-[150px] w-full resize-y border-0 bg-transparent p-5 font-display text-[22px] font-bold leading-[1.6] text-ink outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-inset placeholder:font-normal placeholder:text-ink-soft"
            />
            <div className="flex items-center justify-between gap-3 border-t border-paper-warm-line px-4 py-3">
              {/* 적는 순서를 보여준다(FR-404). 교사가 빠뜨리기 쉬운 것이 「반응」과 「교사 지원」인데,
                  그 둘이 없으면 AI 가 해석과 지원을 쓸 근거가 없다. 안내일 뿐 막지는 않는다.
                  한 줄짜리 빠른 기록 자리라 RecordsPage 보다 짧게 적는다. */}
              <span className="hidden text-[10px] text-ink-soft sm:block">
                본 그대로 적어 주세요 · <b>상황 → 행동 → 반응 → 교사 지원</b> 순서면 더 좋아요
              </span>
              <div className="ml-auto flex items-center gap-3">
                {dictation.supported && (
                  <button
                    type="button"
                    aria-label={dictation.listening ? "받아쓰기 중지" : "음성 받아쓰기"}
                    aria-pressed={dictation.listening}
                    disabled={confirming}
                    onClick={dictation.toggle}
                    className={`flex h-10 w-10 items-center justify-center rounded-full border transition-colors ${
                      dictation.listening
                        ? "animate-pulse border-peach-strong bg-peach-tint text-peach-ink"
                        : "border-primary-tint-line bg-primary-tint text-primary"
                    }`}
                  >
                    <Icon name="mic" className="h-5 w-5" />
                  </button>
                )}
                {!confirming && (
                  <button
                    type="button"
                    disabled={!fact.trim() || dictation.listening}
                    onClick={() => setConfirming(true)}
                    className={PRIMARY}
                  >
                    <Icon name="check" className="h-4 w-4" />
                    기록 남기기
                  </button>
                )}
              </div>
            </div>
          </div>

          {confirming && (
            <section className="mt-5 rounded-lg border border-primary-tint-line bg-primary-tint p-4">
              <h3 className="mb-4 font-display text-2xl font-bold text-primary-ink">
                이렇게 남길까요?
              </h3>
              <div className="grid gap-3 sm:grid-cols-3">
                <label className="text-[10px] text-primary-ink">
                  반
                  <select
                    value={activeClassId}
                    onChange={(e) => {
                      onPickClass(e.target.value);
                      setChildId("");
                    }}
                    className="mt-1 block min-h-11 w-full rounded-md border border-line bg-paper px-3 text-xs text-ink"
                  >
                    {withChildren.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.className}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="text-[10px] text-primary-ink">
                  아이
                  <select
                    value={child?.id ?? ""}
                    onChange={(e) => setChildId(e.target.value)}
                    className="mt-1 block min-h-11 w-full rounded-md border border-line bg-paper px-3 text-xs text-ink"
                  >
                    {classroom?.children.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="text-[10px] text-primary-ink">
                  영역
                  <select
                    value={domain}
                    onChange={(e) => setDomain(e.target.value)}
                    className="mt-1 block min-h-11 w-full rounded-md border border-line bg-paper px-3 text-xs text-ink"
                  >
                    {DOMAINS.map((d) => (
                      <option key={d} value={d}>
                        {d}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="mt-4 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setConfirming(false)}
                  className="min-h-11 px-3 text-xs text-primary-ink underline underline-offset-4"
                >
                  더 쓸래요
                </button>
                <button type="button" disabled={busy} onClick={save} className={PRIMARY}>
                  {busy ? "남기는 중" : "이대로 남기기"}
                </button>
              </div>
            </section>
          )}
        </>
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
    <section className="relative border border-note-soft-line bg-note-soft p-5 shadow-pg-hard">
      <Tape />
      <span className="text-[11px] font-semibold text-sun-ink">한 아이, 조금 더 가까이</span>

      {!child ? (
        <p className="mt-4 text-xs text-sun-ink">아직 등록된 아이가 없어요.</p>
      ) : (
        <>
          <div className="mt-3 flex items-center gap-3">
            <span className="flex h-12 w-12 items-center justify-center rounded-[18px_14px_20px_12px] border border-note-soft-line bg-paper font-display text-[26px] font-bold text-sun-ink">
              {child.name.slice(0, 1)}
            </span>
            <div>
              <h3 className="font-display text-[26px] font-bold text-ink">{child.name}</h3>
              <span className="text-[10px] text-sun-ink">최근 관찰</span>
            </div>
          </div>

          <div className="mt-5 border-t border-note-soft-line pt-4">
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
const DOMAIN_ICON: Record<string, IconName> = {
  "신체운동·건강": "body",
  의사소통: "talk",
  사회관계: "social",
  예술경험: "art",
  자연탐구: "nature",
};

function DomainBoard({ records }: { records: ServerObservation[] }) {
  return (
    <section className={CARD}>
      <h3 className="font-display text-[22px] font-bold text-ink">우리 반 한눈에</h3>
      <p className="mt-1 text-[11px] text-ink-soft">오늘의 놀이와 관찰 영역</p>
      <ul className="mt-5 grid grid-cols-5 gap-2 text-center">
        {DOMAINS.map((domain) => {
          const filled = records.some((r) => r.domain === domain);
          return (
            <li key={domain} className="flex flex-col items-center gap-1.5">
              <span
                className={`flex h-12 w-12 items-center justify-center rounded-[18px] ${
                  filled ? "bg-primary-tint text-primary-ink" : "bg-cream text-ink-soft"
                }`}
              >
                <Icon name={DOMAIN_ICON[domain]} className="h-6 w-6" />
              </span>
              <span className="text-[10px] leading-tight text-ink-soft">{domain}</span>
              <span className={`text-[9px] ${filled ? "text-primary" : "text-ink-soft"}`}>
                {filled ? "기록 있음" : "—"}
              </span>
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

/** 쪽지 윗변에 붙인 종이테이프. 장식이라 읽어주지 않는다. */
function Tape() {
  return (
    <span
      aria-hidden="true"
      className="pointer-events-none absolute -top-3 left-1/2 h-6 w-20 -translate-x-1/2 -rotate-3 border-x border-white/60 bg-tape shadow-[0_1px_2px_rgba(106,96,80,.09)]"
    />
  );
}
