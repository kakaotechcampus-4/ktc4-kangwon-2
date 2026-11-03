"use client";

/**
 * 우리 반 — 작업실 첫 화면.
 *
 * 교사가 하루에 제일 많이 하는 일이 「방금 본 걸 한 줄 적기」라서 그 칸이 맨 위에 온다.
 * 그 아래는 **오늘 적은 내용**이 영수증처럼 쌓이고, 그 끝에서 보육일지로 넘어간다.
 * 옆 줄에는 지금 챙겨야 할 것 셋 — 아직 못 만난 아이 · 비어 있는 날 · 지난주 돌아보기.
 *
 * 종이의 가장자리로 덩어리를 가른다(`globals.css` 의 `.slipEdge` · `.tornPaper`).
 * 네모 테두리를 더 두르면 카드가 늘지만, 교사가 보는 것은 쌓인 종이다.
 *
 * 관찰 기록은 서버에 저장된다(`addRecord`). 반 전체 일과는 오늘 일과 적기에서 입력한다.
 */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { PageContainer } from "@/components/app/AppLayout";
import { Icon } from "@/components/app/icons";
import ChildPicker from "@/components/app/ChildPicker";
import { SsampleNote } from "@/components/app/SsampleNote";
import { useClasses } from "@/components/workspace/WorkspaceUI";
import { listRecords, addRecord } from "@/lib/api/records";
import type { ServerObservation } from "@/lib/api/observations";
import { listRoutines, routineTime, type Routine } from "@/lib/api/routines";
import { today } from "@/lib/workspace/model";
import { useObservationDomains } from "@/lib/hooks/use-observation-domains";
import { loadClassSettings, primaryClassFor } from "@/lib/onboarding/settings";
import { routinesPath, routinesScope } from "@/lib/workspace/routines-route";
import { classServerId } from "@/lib/api/onboarding";
import { isStale, staleLabel, tallyFor } from "@/lib/workspace/child-mark";
import {
  emptyDay,
  firstWrittenDay,
  lastWeekLook,
  shiftDays,
  shortDate,
  type LastWeek,
} from "@/lib/workspace/home-blocks";
import { koreanDateParts } from "@/lib/greeting";
import { useClientState } from "@/lib/hooks/use-client-state";
import { useDictation } from "@/lib/hooks/use-dictation";

const PRIMARY =
  "inline-flex min-h-11 items-center justify-center gap-2 rounded-md border border-primary-line " +
  "bg-primary px-4 text-xs font-semibold text-white shadow-pg-card transition-colors " +
  "hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-40";
/** 영수증 줄 사이의 점선. 선 하나로 「따로 적은 것」이 갈린다. */
const DASH = "border-0 border-t border-dashed border-line";
/** 쪽지 머리의 작은 라벨. 손글씨 제목과 달리 넓게 벌려 쓴다. */
const LABEL = "text-[13px] font-medium tracking-[0.12em]";
/** 일과를 얼마나 거슬러 보나. 두 주면 「비어 있는 날」이 들어온다. */
const LOOK_BACK = 14;
/** 칠판에 붙이는 아이 쪽지. 색과 기울기를 번갈아 쓴다 — 같은 모양이 줄줄이 붙으면 한 장으로 보인다. */
const KID_NOTE = [
  "border-note-soft-line bg-note-soft -rotate-2",
  "border-plum-line bg-plum rotate-2",
  "border-clay-line bg-clay -rotate-1",
  "border-sage-line bg-sage-tint rotate-1",
];
/** 칠판에 붙이는 쪽지 수. 넘치는 아이는 수만 분필로 적는다. */
const PINNED = 4;

export default function HomePage() {
  const [message, setMessage] = useState("");
  // **반 명단**을 못 불러오면 아래 빈 화면 안내를 그리지 않는다. 「아이를 먼저 등록해 주세요」를
  // 보고 멀쩡한 명단을 다시 만들러 간다. 기록 조회가 흔들린 것은 여기 들지 않는다 — 적는 칸은
  // 다른 길로 저장하므로 그대로 쓸 수 있어야 한다. 저장 실패도 아니다 — 적던 글은 남아야 한다.
  const [loadFailed, setLoadFailed] = useState(false);
  const onError = useCallback((m: string) => {
    setMessage(m);
    setLoadFailed(true);
  }, []);
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
  // 반은 사이드바가 정한다. 주소에 반이 적혀 오면(다른 화면에서 건너온 길) 그것이 먼저다.
  // URL의 반이 아직 도착하지 않았으면 다른 반으로 대체하지 않는다.
  const activeClass =
    entry.classId !== null
      ? classes.find((c) => classServerId(c.id) === entry.classId)
      : (classes.find((c) => c.id === entry.primaryId) ?? classes[0]);
  const activeClassId = activeClass?.id ?? "";

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

  /**
   * 반 일과. 오늘 줄과 「비어 있는 날」이 쓴다. 기록과 따로 읽는다 — 한쪽이 실패해도
   * 다른 쪽은 보인다.
   *
   * **못 읽은 것과 없는 것을 가른다.** 실패했을 때 빈 배열로 두면 일과가 멀쩡히 있는
   * 반에게 「아직 일과를 안 적었어요」라고 재촉한다. 모르는 동안은 `null` 로 두고
   * 그 자리를 그리지 않는다.
   */
  const [loadedRoutines, setLoadedRoutines] = useState<{ at: string; rows: Routine[] } | null>(
    null,
  );
  useEffect(() => {
    const serverId = activeClassId ? classServerId(activeClassId) : null;
    if (serverId === null || !todayDate) return;
    let alive = true;
    listRoutines({ class_id: serverId, from: shiftDays(todayDate, -LOOK_BACK), to: todayDate })
      .then((rows) => {
        if (alive) setLoadedRoutines({ at: activeClassId, rows });
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [activeClassId, todayDate]);
  // 반이 바뀐 직후의 옛 반 일과를 쓰지 않는다. 어느 반의 것인지 같이 들고 있다가 맞을 때만 본다.
  const routineRows = loadedRoutines?.at === activeClassId ? loadedRoutines.rows : null;

  const head = koreanDateParts(todayDate ? new Date(todayDate) : new Date());
  const serverClassId = activeClassId ? classServerId(activeClassId) : null;
  const routinesHref = activeClassId && todayDate ? routinesPath(activeClassId, todayDate) : null;
  // 반이 바뀐 직후, 새 응답 전에도 이전 반 기록을 그리지 않는다.
  const classRecords = (records ?? []).filter((r) => r.classId === activeClassId);
  const todayRecords = useMemo(
    () => (records ?? []).filter((r) => r.classId === activeClassId && r.date === todayDate),
    [records, activeClassId, todayDate],
  );
  const todayRoutines = (routineRows ?? []).filter((r) => r.date === todayDate);
  /** 일지는 **활동실행**을 근거로 쓴다 — 줄만 있고 실행이 비면 일지도 빈다 (S-J1 과 같은 규칙). */
  const logReady = todayRoutines.some((r) => r.execution.trim());
  const dailyLogHref =
    serverClassId !== null && todayDate
      ? `/documents?kind=dailyLog&class_id=${serverClassId}&date=${todayDate}`
      : null;
  const gapDay =
    routineRows && todayDate
      ? emptyDay(
          routineRows.map((r) => r.date),
          firstWrittenDay(
            routineRows.map((r) => r.date),
            classRecords.map((r) => r.date),
          ),
          todayDate,
          LOOK_BACK,
        )
      : null;
  const lastWeek = todayDate ? lastWeekLook(classRecords, todayDate) : null;

  return (
    <PageContainer>
      {/* 종이가 화면 끝까지 늘어나면 한 줄이 1300px 을 넘어 글이 안 읽힌다.
          넓은 모니터에서도 책상 위 종이 폭으로 묶어 둔다 (PM 점검). */}
      <div className="mx-auto w-full max-w-[1170px]">
        {/* 머리글은 날짜만 둔다. 반 이름 · 나이는 사이드바 반 카드와 상단 띠에 이미 있다 —
          교사가 매일 보는 맨 윗자리를 라벨로 채우지 않는다. */}
        <h1 className="mb-7 font-display text-[40px] font-bold leading-none text-primary-deep lg:text-[54px]">
          {head.day}
          <span className="relative ml-2.5 inline-block font-display text-[24px] font-bold text-ink-soft lg:text-[30px]">
            {head.dow}
            {/* 달력에서 오늘에 치는 동그라미. 한 바퀴를 덜 닫아 손으로 그은 자국으로 보인다.
                요일만 감싸므로 날짜가 「11월 30일」처럼 길어져도 자리가 안 흔들린다. */}
            <svg
              aria-hidden="true"
              viewBox="0 0 150 70"
              preserveAspectRatio="none"
              className="pointer-events-none absolute -bottom-2.5 -left-3.5 -right-3.5 -top-3 text-alert-strong"
            >
              <path
                d="M74 6 C112 4 146 18 143 36 C140 56 100 66 68 64 C32 62 6 50 8 32 C10 14 42 6 78 7"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.6"
                strokeLinecap="round"
              />
            </svg>
          </span>
        </h1>

        {message && (
          <p role="alert" className="mb-5 rounded-md border border-line bg-paper px-4 py-3 text-xs">
            {message}
          </p>
        )}

        {!loadFailed && (
          <div className="flex flex-col gap-8 xl:flex-row xl:gap-9">
            <div className="flex min-w-0 max-w-[820px] flex-col gap-8 xl:flex-1">
              <Compose
                classes={classes}
                date={todayDate}
                activeClassId={activeClassId}
                records={classRecords}
                onSaved={recordSaved}
                onError={setMessage}
              />

              <TodaySlip
                records={todayRecords}
                loading={records === null}
                routines={routineRows && todayDate ? todayRoutines : null}
                routinesHref={routinesHref}
                dailyLogHref={logReady ? dailyLogHref : null}
                day={head.day}
              />

              {lastWeek && <LastWeekNote look={lastWeek} />}
            </div>

            {/* 오른쪽 줄은 교실 칠판이다. 칸 제목은 쪽지 안이 아니라 판에 분필로 쓰고,
                쪽지는 그 밑에 붙는다 — 종이마다 머리글이 달리면 쪽지가 서류로 보인다. */}
            <div className="chalkboard flex min-w-0 flex-col justify-center gap-[38px] px-4 pb-7 pt-6 xl:w-[310px] xl:shrink-0">
              {todayDate && (
                <UnseenChildren
                  roster={activeClass?.children ?? []}
                  records={classRecords}
                  today={todayDate}
                />
              )}
              {gapDay && <EmptyDayNote date={gapDay} href={routinesPath(activeClassId, gapDay)} />}
              <ChildSpotlight classes={activeClass ? [activeClass] : []} records={classRecords} />
            </div>
          </div>
        )}
      </div>
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
  activeClassId,
  records,
  onSaved,
  onError,
}: {
  classes: Classroom[];
  date: string;
  /** 홈이 정한 지금 반. 홈의 조회와 같은 값이라 통계와 저장 대상이 어긋나지 않는다. */
  activeClassId: string;
  /** 지금 반의 기록. 고르개가 아이별 마지막 기록·이번 주 횟수를 여기서 센다. */
  records: readonly ServerObservation[];
  onSaved: () => void;
  onError: (m: string) => void;
}) {
  // 아이는 여럿 고를 수 있다. 한 명만 고를 때도 배열 하나로 다룬다 — 두 갈래 상태를
  // 두면 「여럿 고르기」를 켰다 끈 사이에 값이 어긋난다.
  const [childIds, setChildIds] = useState<string[]>([]);
  const [many, setMany] = useState(false);
  // 원마다 축이 다르다 (observation-axis.ts). 5영역 원이면 다섯, 2축 원이면 둘이다.
  //
  // **고른 영역 하나만 둔다.** 칸에는 첫 영역을 띄우고 상태는 빈 채로 두면, 교사가 고르지
  // 않고 저장했을 때 화면이 보여준 것과 다른 값(빈 값)이 서버로 간다 — 422 다.
  const domains = useObservationDomains();
  const [picked, setDomain] = useState("");
  const domain = picked || domains[0];
  const [fact, setFact] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  // 받아쓴 말은 적던 글 뒤에 붙인다. 덮어쓰면 쓰던 걸 잃는다.
  const dictation = useDictation((said) => setFact((prev) => (prev ? `${prev} ${said}` : said)));

  // 반은 늦게 도착한다. 그때 useState 를 맞추는 대신 그릴 때 고른다 —
  // effect 안에서 setState 하면 렌더가 한 번 더 돈다. 반을 고르는 규칙은 홈에 하나만 둔다.
  //
  // **아이는 첫 항목으로 떨어뜨리지 않는다.** 영역과 다르다 — 영역을 잘못 고르면 교사가
  // 그 기록을 고치면 되지만, 아이를 잘못 고르면 **다른 아이의 기록**이 된다.
  // 바쁜 교사가 확인하지 않고 「이대로 남기기」를 누르면 조용히 그렇게 저장됐다.
  const classroom = classes.find((c) => c.id === activeClassId);
  const chosen = (classroom?.children ?? []).filter((c) => childIds.includes(c.id));
  const saveLabel =
    chosen.length === 1
      ? `${chosen[0].name} 기록으로 남기기`
      : chosen.length > 1
        ? `${chosen.length}명으로 남기기`
        : "이대로 남기기";

  async function save() {
    const written = fact.trim();
    if (!written || !activeClassId || !chosen.length || busy) return;
    setBusy(true);
    try {
      /*
        아이를 여럿 골랐으면 기록도 사람 수만큼 남는다. 한 장면이어도 평가 증빙은
        아이별로 모여야 한다 (「자유놀이 때 하늘·민재가 같이 블록놀이」가 하늘의 기록
        한 건과 민재의 기록 한 건이다).

        `allSettled` 다. 하나가 실패했을 때 나머지를 되돌릴 방법이 없으므로, 남은 것은
        남긴 채로 두고 **실패한 아이만 다시 고른 상태로** 돌려준다. 적은 글도 지우지
        않는다 — 여기서 글을 지우면 교사가 쓴 문장이 사라진다.
      */
      const results = await Promise.allSettled(
        chosen.map((c) =>
          addRecord({
            classId: activeClassId,
            childId: c.id,
            date,
            domain,
            context: "",
            fact: written,
          }),
        ),
      );
      const stuck = chosen.filter((_, i) => results[i].status === "rejected");
      if (stuck.length === results.length) {
        const first = results[0] as PromiseRejectedResult;
        throw first.reason;
      }
      if (stuck.length) {
        setChildIds(stuck.map((c) => c.id));
        onError(
          `${results.length - stuck.length}명은 남겼어요. ` +
            `${stuck.map((c) => c.name).join(" · ")} 는 못 남겼어요 — 다시 눌러주세요.`,
        );
        onSaved();
        return;
      }
      setFact("");
      setChildIds([]);
      setConfirming(false);
      onSaved();
    } catch (e) {
      onError(e instanceof Error ? e.message : "기록을 저장하지 못했어요.");
    } finally {
      setBusy(false);
    }
  }

  return (
    /* 적는 칸만 **흰 종이**다. 쌓인 것(영수증 · 쪽지)은 아이보리와 색종이라, 제일 밝은
       종이가 늘 「지금 적는 자리」가 된다. 테이프는 종이 바깥에 붙여야 종이에 얹힌 것으로
       보인다. */
    <section className="relative pt-3">
      <Tape className="left-10 -rotate-2" />
      <div className="relative bg-paper px-5 pb-4 pt-5 shadow-pg lg:px-6">
        <h2 className="font-display text-[26px] font-bold text-ink">지금, 한 줄</h2>

        {!classroom?.children.length ? (
          <div className="mt-4 flex flex-col items-center gap-2.5 text-center text-xs text-ink-soft">
            <SsampleNote mood="empty" size={44} />
            아이를 먼저 등록해 주세요.{" "}
            <Link href="/onboarding/children" className="font-semibold text-primary underline">
              아동 명단으로 가기
            </Link>
          </div>
        ) : (
          <>
            {/* 여기는 손글씨(`font-display`)를 쓰지 않는다. 구글 폰트의 Gaegu 는 한글을
                89개 조각으로 쪼개 보내는데, 교사가 글자를 칠 때마다 아직 안 받은 조각이
                생겨 그 글자만 잠깐 다른 글꼴로 보였다가 바뀐다 — 한 줄 안에서 글자가 튄다.
                손글씨는 제목·숫자에만 쓴다(`globals.css`). */}
            <textarea
              aria-label="빠른 기록 내용"
              value={fact}
              disabled={confirming}
              onChange={(e) => setFact(e.target.value)}
              placeholder={
                "바깥놀이에서 아이 A가 도토리를 크기별로 줄 세웠다.\n" +
                "친구가 와서 같이 세었고, 교사는 옆에서 지켜보았다."
              }
              className="ruledPaper mt-3 block min-h-[136px] w-full resize-y border-0 bg-transparent p-0 text-[20px] font-medium leading-[1.7] text-ink outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-4 focus-visible:ring-offset-paper placeholder:font-normal placeholder:text-ink-hint"
            />
            {dictation.error && (
              <p
                role="status"
                className="mt-2 bg-peach-tint px-3 py-2.5 text-[13px] text-peach-ink"
              >
                {dictation.error}
              </p>
            )}
            <div className="mt-4 flex items-center justify-between gap-3 border-t border-line pt-3">
              {/* 적는 순서를 보여준다(FR-404). 교사가 빠뜨리기 쉬운 것이 「반응」과 「교사 지원」인데,
                  그 둘이 없으면 AI 가 해석과 지원을 쓸 근거가 없다. 안내일 뿐 막지는 않는다.
                  한 줄짜리 빠른 기록 자리라 RecordsPage 보다 짧게 적는다. */}
              <span className="hidden text-[13px] text-ink-soft sm:block">
                <b>상황 · 행동 · 반응 · 교사 지원</b> 순서면 좋아요
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
                    누구 기록인지 고르기
                  </button>
                )}
              </div>
            </div>
          </>
        )}
      </div>

      {confirming && (
        <section className="mt-5 rounded-lg border border-primary-tint-line bg-primary-tint p-4">
          <h3 className="mb-4 flex items-center gap-2.5 font-display text-2xl font-bold text-primary-ink">
            <SsampleNote size={34} label={null} />
            이렇게 남길까요?
          </h3>
          {/* 아이는 격자로 깔아 반 전체를 보여준다. 고르개가 「누가 오래 비었는지」까지
                  같이 말해 주므로, 적을 아이를 고르는 자리가 치우침을 보는 자리도 된다. */}
          <div className="rounded-md border border-line bg-paper p-3.5">
            <ChildPicker
              childList={classroom?.children ?? []}
              records={records}
              today={date}
              selected={childIds}
              onSelect={setChildIds}
              multiple={many}
              onMultipleChange={(on) => {
                setMany(on);
                // 한 명 고르기로 돌아갈 때 둘 이상 골라 둔 것을 들고 가지 않는다.
                setChildIds((ids) => (on ? ids : ids.slice(0, 1)));
              }}
            />
          </div>
          <label className="mt-3 block max-w-[260px] text-[13px] text-primary-ink">
            영역
            <select
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              className="selectField mt-1 block min-h-11 w-full rounded-md border border-line bg-paper px-3 text-xs text-ink"
            >
              {domains.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>
          <div className="mt-4 flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="min-h-11 px-3 text-xs text-primary-ink underline underline-offset-4"
            >
              더 쓸래요
            </button>
            <button
              type="button"
              disabled={busy || !chosen.length}
              onClick={save}
              className={PRIMARY}
            >
              {busy ? "남기는 중" : saveLabel}
            </button>
          </div>
        </section>
      )}
    </section>
  );
}

/** 앞장 쪽지 색. 아이가 바뀔 때마다 색도 바뀐다 — 넘어갔다는 것이 글자보다 먼저 보인다. */
const SPOT_NOTE = [
  "border-note-soft-line bg-note-soft",
  "border-plum-line bg-plum",
  "border-clay-line bg-clay",
  "border-sage-line bg-sage-tint",
];
/** 자동으로 넘어가는 간격. 짧은 관찰 한 건을 읽기에 7초면 넉넉하다. */
const TURN_MS = 7000;

/**
 * 한 아이, 조금 더 가까이 — 쪽지를 여러 장 겹쳐 두고 한 장씩 넘긴다.
 *
 * 책장이 넘어가듯 **스스로 넘어간다**(7초). 읽는 중에 넘어가면 방해가 되므로
 * 마우스를 올리거나 안의 것에 초점이 가 있으면 멈춘다. 화살표로 직접 넘기면
 * 그때부터는 자동으로 넘기지 않는다 — 교사가 고른 아이를 화면이 뺏어가면 안 된다.
 *
 * 움직임을 줄여 달라고 한 기기(`prefers-reduced-motion`)에서는 처음부터 자동이 없다.
 */
function ChildSpotlight({
  classes,
  records,
}: {
  classes: Classroom[];
  records: ServerObservation[];
}) {
  const children = classes.flatMap((c) => c.children);
  const [index, setIndex] = useState(0);
  // 교사가 직접 넘긴 뒤에는 자동으로 움직이지 않는다.
  const [held, setHeld] = useState(false);
  const [paused, setPaused] = useState(false);
  const count = children.length;

  useEffect(() => {
    if (count < 2 || held || paused) return;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const timer = window.setInterval(() => setIndex((p) => (p + 1) % count), TURN_MS);
    return () => window.clearInterval(timer);
  }, [count, held, paused]);

  const child = children[index % Math.max(count, 1)];
  const latest = records.find((r) => r.childId === child?.id);
  // 관찰 기록 화면은 기본으로 「주 반」을 연다. 지금 보고 있는 반·아이를 같이 넘겨야 그 아이가 걸린다.
  const childHref = child
    ? `/records?class=${encodeURIComponent(
        classes.find((c) => c.children.some((k) => k.id === child.id))?.id ?? "",
      )}&child=${encodeURIComponent(child.id)}`
    : "/records";
  const turn = (step: number) => {
    setHeld(true);
    setIndex((p) => (p + step + count) % count);
  };

  return (
    <BoardSection title="한 아이, 조금 더 가까이">
      {!child ? (
        <ChalkLine>아직 등록된 아이가 없어요</ChalkLine>
      ) : (
        <>
          <div
            className="group relative mx-3"
            onMouseEnter={() => setPaused(true)}
            onMouseLeave={() => setPaused(false)}
            onFocusCapture={() => setPaused(true)}
            onBlurCapture={() => setPaused(false)}
          >
            {/* 뒤에 깔린 두 장. 넘길 것이 남았다는 게 글자 없이 보인다. */}
            {count > 1 && (
              <>
                <span
                  aria-hidden="true"
                  className="absolute inset-0 translate-x-[6px] translate-y-[8px] rotate-[2.6deg] border border-plum-line bg-plum"
                />
                <span
                  aria-hidden="true"
                  className="absolute inset-0 -translate-x-[5px] translate-y-[5px] -rotate-[2deg] border border-clay-line bg-clay"
                />
              </>
            )}
            <div
              key={child.id}
              className={`pageTurn relative border p-4 shadow-pg-hard ${SPOT_NOTE[index % SPOT_NOTE.length]}`}
            >
              <h3 className="font-display text-[25px] font-bold leading-none text-ink">
                {child.name}
              </h3>
              {/* 기록이 없으면 영역 줄을 비운다. 「최근 관찰」을 빈 자리 메우개로 쓰면
                  제목과 같은 말이 한 쪽지에 두 번 나온다. */}
              {/* 이름 · 언제 무슨 영역 · 적힌 글 · 가는 길. 넷이 줄 없이 붙어 있으면
                  글자 크기만으로 갈라야 해서 한 덩어리로 읽힌다. */}
              {latest ? (
                <div className="mt-3 flex items-baseline justify-between gap-2 border-t border-ink/35 pt-2.5 text-[12.5px] font-semibold text-sun-ink">
                  <span className="min-w-0 truncate">{latest.domain}</span>
                  <span className="shrink-0 font-normal">{shortDate(latest.date)}</span>
                </div>
              ) : (
                <div className="mt-3 border-t border-ink/35 pt-2.5 text-[12.5px] text-sun-ink">
                  최근 관찰
                </div>
              )}
              <p className="mt-2 text-[13.5px] leading-[1.8] text-ink">
                {latest?.fact || "아직 남긴 관찰 기록이 없어요."}
              </p>
              <Link
                href={childHref}
                className="mt-3 flex min-h-10 items-center gap-1 border-t border-ink/35 pt-2.5 text-[12.5px] font-semibold text-sun-ink"
              >
                이 아이 기록 보기
                <Icon name="arrow" className="h-3 w-3" />
              </Link>
            </div>
            {count > 1 && (
              <>
                <button
                  type="button"
                  aria-label="이전 아이"
                  onClick={() => turn(-1)}
                  className="absolute -left-4 top-1/2 flex h-12 w-8 -translate-y-1/2 items-center justify-center text-board-ink-soft opacity-0 transition-opacity hover:text-board-ink focus-visible:opacity-100 group-hover:opacity-100"
                >
                  <Icon name="arrow" className="h-3.5 w-3.5 rotate-180" />
                </button>
                <button
                  type="button"
                  aria-label="다음 아이"
                  onClick={() => turn(1)}
                  className="absolute -right-4 top-1/2 flex h-12 w-8 -translate-y-1/2 items-center justify-center text-board-ink-soft opacity-0 transition-opacity hover:text-board-ink focus-visible:opacity-100 group-hover:opacity-100"
                >
                  <Icon name="arrow" className="h-3.5 w-3.5" />
                </button>
              </>
            )}
          </div>
          {count > 1 && (
            <p className="text-center font-display text-[16px] text-board-ink-soft">
              {count}명 중 {(index % count) + 1}번째
            </p>
          )}
        </>
      )}
    </BoardSection>
  );
}

/**
 * 오늘 적은 내용 — 영수증.
 *
 * 일과 한 줄과 관찰 기록을 적힌 시각과 함께 한 줄씩 쌓고, **그 끝에** 일지로 넘어가는
 * 줄을 둔다. 마감을 맨 위에 띄우면 아직 아무것도 안 적은 교사에게 첫 화면이 재촉으로
 * 시작한다 — 재료가 다 모인 자리에서 넘어가는 것이 순서다.
 */
function TodaySlip({
  records,
  loading,
  routines,
  routinesHref,
  dailyLogHref,
  day,
}: {
  records: ServerObservation[];
  loading: boolean;
  /** 오늘 일과. 아직 못 읽었으면 `null` 이고 그 줄을 그리지 않는다. */
  routines: Routine[] | null;
  routinesHref: string | null;
  /** 일지를 만들 수 있을 때만 주소가 온다 — 활동실행이 적혀 있어야 한다. */
  dailyLogHref: string | null;
  /** 「11월 3일」. 머리글과 같은 글자를 쓴다. */
  day: string;
}) {
  if (loading) return null;
  const names = (routines ?? []).map((r) => r.name.trim()).filter(Boolean);
  return (
    <section>
      <div aria-hidden="true" className="slipEdge top" />
      <div className="bg-ivory px-5 lg:px-6">
        <div className="flex items-baseline justify-between gap-3 py-3">
          <h2 className={`${LABEL} min-w-0 text-ink-soft`}>
            오늘 적은 내용 <b className="text-primary">{records.length}</b>건
          </h2>
          <Link href="/records" className="shrink-0 text-xs font-semibold text-primary">
            전체 기록 →
          </Link>
        </div>

        {routines && (
          <>
            <hr className={DASH} />
            <div className="flex flex-wrap items-baseline gap-3 py-3">
              <span className="w-[52px] shrink-0 text-[13px] text-ink-soft">
                {routineTime(routines[0]?.start ?? null)}
              </span>
              <span className="min-w-0 flex-1 text-sm text-ink">
                {names.length ? `일과 — ${names.join(" · ")}` : "일과를 아직 안 적었어요"}
              </span>
              {routinesHref && (
                <Link href={routinesHref} className="shrink-0 text-xs font-semibold text-primary">
                  오늘 일과 적기
                </Link>
              )}
            </div>
          </>
        )}

        {records.length === 0 ? (
          <>
            <hr className={DASH} />
            <p className="py-4 text-center text-xs text-ink-soft">
              오늘은 아직 기록이 없어요. 위에 한 줄 남겨 보세요.
            </p>
          </>
        ) : (
          records.map((record) => (
            <div key={record.id}>
              <hr className={DASH} />
              <div className="flex gap-3 py-3">
                <span className="w-[52px] shrink-0 pt-0.5 text-[13px] text-ink-soft">
                  {clockOf(record.createdAt)}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm text-ink">{record.fact}</span>
                  <span className="mt-1.5 inline-flex rounded bg-primary-tint px-2 py-0.5 text-[13px] text-primary-ink">
                    {record.childName} · {record.domain}
                  </span>
                </span>
              </div>
            </div>
          ))
        )}

        {/* 일지는 일과를 근거로 쓴다. 일과가 비면 길을 막는 대신 그 자리에서 일과로 보낸다. */}
        <hr className={`${DASH} border-t-2`} />
        <div className="flex flex-wrap items-center gap-3 py-4">
          <span className="min-w-0 flex-1 border-l-[3px] border-peach-strong bg-peach-tint py-2 pl-3.5">
            <span className={`${LABEL} block text-peach-ink`}>오늘 적은 것으로</span>
            <span className="mt-0.5 block text-sm font-bold text-ink">{day} 보육일지</span>
          </span>
          {dailyLogHref ? (
            <Link href={dailyLogHref} className={PRIMARY}>
              만들기
              <Icon name="arrow" className="h-4 w-4" />
            </Link>
          ) : (
            <span className="text-[13px] text-ink-soft">
              일과를 적으면 만들 수 있어요
              {routinesHref && (
                <>
                  {" · "}
                  <Link href={routinesHref} className="font-semibold text-primary underline">
                    일과 적기
                  </Link>
                </>
              )}
            </span>
          )}
        </div>
      </div>
      <div aria-hidden="true" className="slipEdge bottom" />
    </section>
  );
}

/** 칠판 한 칸 — 분필로 쓴 제목, 그 아래 붙인 쪽지, 맨 끝에 더 보러 가는 길. */
function BoardSection({
  title,
  href,
  linkLabel,
  children,
}: {
  title: string;
  href?: string;
  linkLabel?: string;
  children: ReactNode;
}) {
  return (
    <section className="flex min-w-0 flex-col gap-3">
      <h2 className="font-display text-[20px] font-bold leading-tight text-board-ink">{title}</h2>
      {children}
      {href && linkLabel && (
        <Link
          href={href}
          className="self-start font-display text-[17px] font-bold text-board-ink-soft underline underline-offset-4"
        >
          {linkLabel}
        </Link>
      )}
    </section>
  );
}

/** 칠판에 쓰는 분필 글. 쪽지가 없는 자리를 빈 칸으로 두지 않는다. */
function ChalkLine({ children }: { children: ReactNode }) {
  return (
    <p className="font-display text-[18px] leading-[1.6] text-board-ink-soft">{children}</p>
  );
}

/**
 * 기록 안된 아이들 — 한 주 넘게 기록이 없는 아이. 제목은 PM 이 정한 말이다.
 *
 * 평가제에서 교사가 제일 걱정하는 것이 기록의 치우침이다. 셈은 아이 고르개와 **같은
 * 것**을 쓴다(`child-mark.ts`) — 두 자리가 다른 숫자를 말하면 둘 다 못 믿는다.
 *
 * **쪽지는 넉 장까지만 붙인다.** 반이 스물이면 비어 있는 아이가 열을 넘을 수 있는데,
 * 그걸 다 붙이면 첫 화면이 빚 목록이 된다. 310px 폭에 두 장씩 두 줄이 꼭 맞고,
 * 다섯 장이 되면 세 줄이 되면서 아래 칸이 첫 화면 밖으로 밀린다.
 */
function UnseenChildren({
  roster,
  records,
  today,
}: {
  roster: Classroom["children"];
  records: readonly { childId: string; date: string }[];
  today: string;
}) {
  if (!roster.length) return null;
  // 오래 비어 있는 아이부터. 한 번도 없는 아이가 제일 급하다.
  const waited = (days: number | null) => (days === null ? Number.MAX_SAFE_INTEGER : days);
  const unseen = roster
    .map((child) => ({ child, tally: tallyFor(records, child.id, today) }))
    .filter(({ tally }) => isStale(tally))
    .sort((a, b) => waited(b.tally.days) - waited(a.tally.days));
  const pinned = unseen.slice(0, PINNED);
  const rest = unseen.length - pinned.length;
  // 쓰기 시작한 날엔 반 전체가 0번이다. 그날 스무 장을 붙이면 첫날부터 빚이 보인다.
  const neverStarted =
    unseen.length === roster.length && unseen.every(({ tally }) => tally.days === null);

  return (
    <BoardSection title="기록 안된 아이들" href="/records/children" linkLabel="아이들 전부 보기 →">
      {unseen.length === 0 ? (
        <ChalkLine>
          이번 주{" "}
          <span className="relative inline-block">
            <span className="text-[40px] font-bold leading-none text-board-ink">모두</span>
            {/* 「다 적었다」는 표시다. 워드마크에서 뺀 그 마크를 여기서는 칭찬으로 쓴다. */}
            <Icon
              name="star"
              aria-hidden="true"
              className="absolute -right-[18px] -top-1 h-[17px] w-[17px] text-board-ink"
            />
          </span>
          <br />한 번씩 적혔어요
        </ChalkLine>
      ) : neverStarted ? (
        <ChalkLine>
          아직 아무도 안 적혔어요.
          <br />
          오늘 <b className="text-board-ink">한 명</b>부터 시작해요
        </ChalkLine>
      ) : (
        <>
          <ul className="flex flex-wrap gap-x-3 gap-y-4 pt-2">
            {pinned.map(({ child, tally }, i) => (
              <li key={child.id}>
                <span
                  className={`relative block w-[94px] border px-3 pb-3 pt-2.5 shadow-[0_3px_7px_rgba(0,0,0,.3)] ${KID_NOTE[i % KID_NOTE.length]}`}
                >
                  {/* 아이 쪽지는 작아서 본문 테이프(w-20)가 쪽지보다 넓다. 여기만 좁게 붙인다. */}
                  <span
                    aria-hidden="true"
                    className="pointer-events-none absolute -top-2 left-1/2 h-4 w-11 -translate-x-1/2 -rotate-3 border-x border-white/60 bg-tape"
                  />
                  <span className="block font-display text-[22px] font-bold leading-none text-ink">
                    {child.name}
                  </span>
                  <span className="mt-1.5 block whitespace-nowrap text-[11.5px] text-ink-soft">
                    {staleLabel(tally)}
                  </span>
                </span>
              </li>
            ))}
          </ul>
          {rest > 0 && (
            <ChalkLine>
              그 밖에 <b className="text-board-ink">{rest}명</b> 더
            </ChalkLine>
          )}
        </>
      )}
    </BoardSection>
  );
}

/**
 * 비어 있는 날 — 일과가 없어 일지를 만들 수 없는 지난 평일. **하루만** 보여 준다.
 * 빠뜨린 날을 다 세어 들이밀면 첫 화면이 빚 목록이 된다.
 */
function EmptyDayNote({ date, href }: { date: string; href: string | null }) {
  return (
    <BoardSection title="비어 있는 날">
      {/* 칠판 위에서는 찢긴 밑(`tornPaper`)을 쓰지 않는다. 어두운 판 위에 흰 반원이
          줄지어 떠서 종이가 톱니처럼 보인다. 판에 붙인 쪽지는 네 변이 다 반듯하다. */}
      <div className="relative mt-1 border border-peach-line bg-peach p-5 shadow-pg-hard">
        <Tape className="right-8 rotate-3" />
        <div className="flex items-baseline gap-3">
          <span className="font-display text-[40px] font-bold leading-none text-peach-ink">
            {shortDate(date)}
          </span>
          <span className="min-w-0 flex-1 text-[13px] text-ink-soft">
            일과가 없어
            <br />
            일지를 못 만들어요
          </span>
        </div>
        {href && (
          <Link
            href={href}
            className="mt-3 inline-flex min-h-10 items-center rounded-md border border-line bg-ivory px-4 text-xs font-semibold text-ink shadow-pg-card transition-transform active:translate-x-[2px] active:translate-y-[3px] active:shadow-none"
          >
            작성하기
          </Link>
        )}
      </div>
    </BoardSection>
  );
}

/**
 * 지난주 돌아보기 — **센 것만** 적는다.
 *
 * 「모으고 견주는 놀이가 늘었습니다」 같은 해석은 기록을 읽어야 나오는 말이고, 그것은
 * 주간 보육일지가 하는 일이다. 첫 화면이 지어내면 교사가 그걸 믿고 문서로 옮긴다.
 */
function LastWeekNote({ look }: { look: LastWeek }) {
  return (
    <TornNote tone="bg-primary-tint" tape="left-16 -rotate-2">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className={`${LABEL} min-w-0 text-primary-ink`}>
          지난주 돌아보기 · {shortDate(look.from)}~{shortDate(look.to)}
        </h2>
        <Link
          href="/quick-records"
          className="shrink-0 text-xs font-semibold text-primary-ink underline"
        >
          주간 기록 보기 →
        </Link>
      </div>
      <p className="mt-3 max-w-[60ch] text-sm leading-[1.85] text-ink">
        기록 <b>{look.count}건</b>
        {look.domain && (
          <>
            {" · 제일 많이 적은 영역은 "}
            <b>{look.domain}</b> {look.domainCount}건이에요.
          </>
        )}
      </p>
    </TornNote>
  );
}

/**
 * 테이프로 붙여 둔, 아래를 찢어낸 쪽지.
 *
 * 테이프는 찢긴 종이 **바깥**에 둔다 — 안에 넣으면 같은 `mask` 에 같이 깎여 사라진다.
 */
function TornNote({ tone, tape, children }: { tone: string; tape: string; children: ReactNode }) {
  return (
    <section className="relative min-w-0 pt-3">
      <Tape className={tape} />
      <div className={`tornPaper px-5 pb-8 pt-4 ${tone}`}>{children}</div>
    </section>
  );
}

/** 「10:20」 — 적힌 시각. 서버가 시간대를 붙여 주므로 교사가 보는 시각으로 읽는다. */
function clockOf(createdAt: string): string {
  const at = new Date(createdAt);
  if (Number.isNaN(at.getTime())) return "";
  return `${String(at.getHours()).padStart(2, "0")}:${String(at.getMinutes()).padStart(2, "0")}`;
}

/** 쪽지 윗변에 붙인 종이테이프. 장식이라 읽어주지 않는다. */
function Tape({ className = "left-1/2 -translate-x-1/2 -rotate-3" }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={`pointer-events-none absolute -top-3 z-[1] h-6 w-20 border-x border-white/60 bg-tape shadow-[0_1px_2px_rgba(106,96,80,.09)] ${className}`}
    />
  );
}
