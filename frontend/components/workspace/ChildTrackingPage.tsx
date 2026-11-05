"use client";
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { getMe } from "@/lib/api/auth";
import { getChildTracking } from "@/lib/api/children";
import { getClasses, isMyClass } from "@/lib/api/classes";
import { getObservations } from "@/lib/api/observations";
import { useClientState } from "@/lib/hooks/use-client-state";
import { useObservationDomains } from "@/lib/hooks/use-observation-domains";
import { CHILD_PREFIX, CLASS_PREFIX, classServerId } from "@/lib/api/onboarding";
import { chosenClassFor, loadClassSettings } from "@/lib/onboarding/settings";
import { daysBetween, markFor, STALE_DAYS } from "@/lib/workspace/child-mark";
import { DOMAIN_LOOK } from "@/lib/workspace/domain-look";
import { today } from "@/lib/workspace/model";
import type { ApiChildTracking, ApiClass, ApiObservation } from "@/lib/api/types";
import { Icon } from "@/components/app/icons";
import { ChildNote } from "@/components/app/ChildPicker";
import { ObservationArt } from "./DocumentArchiveArt";
import { Message } from "./WorkspaceUI";
import styles from "./ChildTracking.module.css";

/** 반 하나의 아이별 집계. 기록 본문은 고른 아이 것만 따로 받는다. */
interface ClassData {
  classId: number;
  children: ApiChildTracking[];
}

const FAILED = "기록을 불러오지 못했어요. 잠시 뒤 다시 열어주세요.";

/** 관찰 기록 화면이 이미 받는 반·아동 필터만 전달한다. 실명이나 본문은 주소에 넣지 않는다. */
function recordsHref(classId: number | null, childId?: number) {
  if (classId === null) return "/records";
  const query = new URLSearchParams({ class: CLASS_PREFIX + classId });
  if (childId !== undefined) query.set("child", CHILD_PREFIX + childId);
  return "/records?" + query.toString();
}

/** 마지막 기록이 며칠 전인지. 한 번도 없으면 null. */
const gapOf = (child: ApiChildTracking, now: string) =>
  child.last_date ? daysBetween(child.last_date, now) : null;
/** 「오늘」 · 「어제」 · 「14일 전」 · 「없음」 */
function whenLabel(days: number | null) {
  if (days === null) return "없음";
  return days === 0 ? "오늘" : days === 1 ? "어제" : `${days}일 전`;
}

/** 오래 비어 있는 순 — 한 번도 없는 아이가 맨 앞, 그다음 마지막 기록이 오래된 아이. */
function byNeed(a: ApiChildTracking, b: ApiChildTracking) {
  if (a.last_date !== b.last_date) {
    if (a.last_date === null) return -1;
    if (b.last_date === null) return 1;
    return a.last_date.localeCompare(b.last_date);
  }
  return a.name.localeCompare(b.name, "ko");
}

/**
 * 칠판 띠 한 줄. **가장 오래 비어 있는 아이에 맞춰 말을 고른다** — 모두 사흘 안에
 * 적었는데 「한 주 넘게 못 본 아이」라고 하면 틀린 말이다.
 *
 * - 한 번도 없는 아이가 있으면 → 「아직 한 번도 못 적은 아이 — ○○」
 * - 한 주(7일)를 넘긴 아이가 있으면 → 「한 주 넘게 못 본 아이 — ○○」
 * - 다 한 주 안이면 → 「다음엔 ○○ 차례예요」(가장 오래된 아이)
 * - 오늘 모두 적었으면 → 「오늘 모두 한 번씩 적었어요」
 */
export function boardLine(children: ApiChildTracking[], now: string) {
  if (!children.length) return null;
  const sorted = [...children].sort(byNeed);
  const top = sorted[0];
  const gap = gapOf(top, now);
  const names = (list: ApiChildTracking[]) =>
    list.length > 3
      ? `${list
          .slice(0, 3)
          .map((c) => c.name)
          .join(" · ")} 외 ${list.length - 3}명`
      : list.map((c) => c.name).join(" · ");
  if (gap === null) {
    const never = sorted.filter((c) => c.last_date === null);
    return {
      lead: "아직 한 번도 못 적은 아이 — ",
      names: names(never),
      tail: "",
      sub: "",
      target: top,
    };
  }
  if (gap > STALE_DAYS) {
    const late = sorted.filter((c) => (gapOf(c, now) ?? 0) > STALE_DAYS);
    const sub = `${late.length > 1 ? "가장 오래된 기록" : "마지막 기록"} ${whenLabel(gap)}`;
    return { lead: "한 주 넘게 못 본 아이 — ", names: names(late), tail: "", sub, target: top };
  }
  if (gap > 0)
    return {
      lead: "다음엔 ",
      names: top.name,
      tail: " 차례예요",
      sub: `마지막 기록 ${whenLabel(gap)}`,
      target: top,
    };
  return { lead: "오늘 모두 한 번씩 적었어요", names: "", tail: "", sub: "", target: null };
}

/**
 * 아이별 기록 — 쪽지 하나가 아이 한 명. 오래 비어 있는 아이가 먼저 온다(순서는 하나뿐이다),
 * 쪽지를 누르면 옆에 그 아이의 영역 칸과 날짜별 기록이 펼쳐진다.
 *
 * **조회만 한다.** 발달 수준을 판정하지 않는다 — 판정은 ADR-007 이 스펙아웃한 발달평가다.
 * 영역별 개수는 「어느 영역을 덜 봤나」를 교사가 알게 하는 용도다. 서버가 센다 (§2-1).
 * 영역 축(누리과정 5영역 · 일상생활 · 놀이활동)은 원 설정을 따른다 — 화면에서 바꾸게
 * 두었더니, 그 축으로 적은 기록이 없는 칸만 보여서 헷갈렸다.
 *
 * 서버에서 바로 읽고 브라우저에 저장하지 않는다 — 아동 실명이 담긴다 (ADR-013).
 */
export default function ChildTrackingPage() {
  const [classes, setClasses] = useState<ApiClass[] | null>(null);
  const [classData, setClassData] = useState<ClassData | null>(null);
  const [pickedChild, setPickedChild] = useState<number | null>(null);
  const [error, setError] = useState("");
  const domains = useObservationDomains();

  /*
    반은 사이드바가 고른다. 화면 안에 셀렉트를 두지 않으므로 주 반의 서버 번호를 그대로
    쓰고, 아직 연결이 없으면 서버가 준 첫 반으로 떨어진다.
  */
  const [primaryServerId] = useClientState<number | null>(() => {
    const local = chosenClassFor(loadClassSettings())?.id;
    const bound = local ? classServerId(local) : null;
    return typeof bound === "number" ? bound : null;
  }, null);
  const classId =
    (primaryServerId && classes?.some((c) => c.id === primaryServerId) ? primaryServerId : null) ??
    classes?.[0]?.id ??
    null;

  useEffect(() => {
    getMe()
      .then((me) => (me.center_id ? getClasses(me.center_id) : { items: [] }))
      .then(({ items }) => setClasses(items.filter(isMyClass)))
      .catch(() => setError(FAILED));
  }, []);

  useEffect(() => {
    if (classId === null) return;
    let stale = false;
    getChildTracking(classId)
      .then(({ items }) => !stale && setClassData({ classId, children: items }))
      .catch(() => !stale && setError(FAILED));
    return () => {
      stale = true;
    };
  }, [classId]);

  const current = classData?.classId === classId ? classData : null;
  const now = today();
  const sorted = current ? [...current.children].sort(byNeed) : [];
  const child = sorted.find((c) => c.child_id === pickedChild) ?? sorted[0] ?? null;

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1>아이별 기록</h1>
          <p>쪽지 하나가 아이 한 명이에요. 누르면 그 아이 기록이 펼쳐져요.</p>
        </div>
        {/* 관찰 기록 아래 화면이다. 관찰일지 만들기 화면과 같은 자리 · 같은 말로 돌아간다. */}
        <Link href="/records" className={styles.back}>
          ← 관찰 기록
        </Link>
      </header>
      <Message error>{error}</Message>
      {/* 조회가 실패하면 로딩 안내를 함께 보여주지 않는다. */}
      {!error && !classes && <TrackingState loading title="기록을 불러오고 있어요" />}
      {!error && classes && !classes.length && (
        <TrackingState title="먼저 아이를 등록해 주세요">
          <Link href="/onboarding" className={styles.action}>
            반·아동 등록하기 →
          </Link>
        </TrackingState>
      )}
      {!error && !!classes?.length && (
        <>
          {current && <Board kids={current.children} now={now} classId={classId} />}
          <div className={styles.workspace}>
            <Wall
              loaded={!!current}
              sorted={sorted}
              selected={child?.child_id ?? null}
              now={now}
              domains={domains}
              onPick={setPickedChild}
            />
            {/* 아이를 바꾸면 이전 아이의 본문을 즉시 걷고 새로 조회한다. */}
            {child && (
              <ChildDetail
                key={`${classId}:${child.child_id}`}
                classId={classId}
                child={child}
                domains={domains}
              />
            )}
          </div>
        </>
      )}
      {error && (
        <div className={styles.notice}>
          <ObservationArt className={styles.emptyArt} />
          <h2>기록을 잠시 불러올 수 없어요</h2>
          <p>잠시 뒤 이 화면을 다시 열거나 관찰 기록 화면으로 돌아가주세요.</p>
          <Link href="/records" className={styles.action}>
            관찰 기록으로 돌아가기
          </Link>
        </div>
      )}
    </main>
  );
}

/** 칠판 띠 — 지금 챙길 아이 한 줄과 바로 적으러 가는 단추. */
function Board({
  kids,
  now,
  classId,
}: {
  kids: ApiChildTracking[];
  now: string;
  classId: number | null;
}) {
  const line = boardLine(kids, now);
  if (!line) return null;
  return (
    <section className={`chalkboard ${styles.board}`} aria-label="챙길 아이">
      <div>
        <p className={styles.boardSay}>
          {line.lead}
          {line.names && <em>{line.names}</em>}
          {line.tail}
        </p>
        {line.sub && <p className={styles.boardSub}>{line.sub}</p>}
      </div>
      {line.target && (
        <Link href={recordsHref(classId, line.target.child_id)} className={styles.boardGo}>
          기록 작성 →
        </Link>
      )}
    </section>
  );
}

function Wall({
  loaded,
  sorted,
  selected,
  now,
  domains,
  onPick,
}: {
  loaded: boolean;
  sorted: ApiChildTracking[];
  selected: number | null;
  now: string;
  domains: readonly string[];
  onPick: (id: number) => void;
}) {
  if (!loaded)
    return (
      <p role="status" className={styles.helper}>
        아이 목록을 불러오고 있어요…
      </p>
    );
  if (!sorted.length) {
    return (
      <div className={styles.rosterEmpty}>
        <p>이 반에 등록된 아동이 없어요</p>
        <Link href="/onboarding/children" className={styles.textLink}>
          아동 등록하기 →
        </Link>
      </div>
    );
  }
  return (
    <ul className={styles.wall} aria-label="아이 목록">
      {sorted.map((item) => {
        const gap = gapOf(item, now);
        const late = gap === null || gap > STALE_DAYS;
        return (
          <li key={item.child_id}>
            <button
              type="button"
              className={styles.note}
              data-tone={markFor(CHILD_PREFIX + item.child_id).tone}
              aria-label={`${item.name} · ${item.total}건`}
              aria-pressed={item.child_id === selected}
              onClick={() => onPick(item.child_id)}
            >
              {late && (
                <span className={styles.flag}>{gap === null ? "기록 없음" : `D+${gap}`}</span>
              )}
              <strong>{item.name}</strong>
              <small data-late={late || undefined}>
                기록 {item.total}건<span className={styles.sep}> · </span>
                <span className={styles.last}>마지막 {whenLabel(gap)}</span>
              </small>
              <span className={styles.noteDomains} aria-hidden="true">
                {domains.map((domain) => {
                  const look = DOMAIN_LOOK[domain];
                  if (!look) return null;
                  return (
                    <i
                      key={domain}
                      data-tone={look.tone}
                      data-off={!item.by_domain[domain] || undefined}
                    >
                      <Icon name={look.icon} width={13} height={13} />
                    </i>
                  );
                })}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function ChildDetail({
  classId,
  child,
  domains,
}: {
  classId: number | null;
  child: ApiChildTracking;
  domains: readonly string[];
}) {
  const [records, setRecords] = useState<ApiObservation[] | null>(null);
  const [failed, setFailed] = useState(false);
  const writeHref = recordsHref(classId, child.child_id);

  useEffect(() => {
    let stale = false;
    // 서버가 date 내림차순으로 준다 (§10). 순서를 다시 매기지 않는다.
    // 반을 같이 보낸다 — 반을 안 짚은 목록은 내 반만 준다. 승인받고 보는 반이면 빈 목록이 온다 (ADR-059).
    getObservations({ class_id: classId ?? undefined, child_id: child.child_id })
      .then(({ items }) => !stale && setRecords(items))
      .catch(() => !stale && setFailed(true));
    return () => {
      stale = true;
    };
  }, [classId, child.child_id]);

  // tracking 조회가 성공해 전체 0건임을 알 때만 누락 키를 0으로 보충한다.
  // 기록이 있는 아동의 누락 키는 숫자를 추정하지 않고 「—」 로 둔다.
  const countOf = (domain: string): number | undefined =>
    child.by_domain[domain] ?? (child.total === 0 ? 0 : undefined);

  return (
    <section className={styles.detail} aria-label={`${child.name} 관찰 기록`}>
      <div className={styles.detailHead}>
        <ChildNote name={child.name} mark={markFor(CHILD_PREFIX + child.child_id)} size={40} />
        <h2>{child.name}</h2>
      </div>

      <section className={styles.domainSection} aria-label="영역별 기록 수">
        <ul className={styles.domainRow} data-axis={domains.length}>
          {domains.map((domain) => {
            const count = countOf(domain);
            const look = DOMAIN_LOOK[domain];
            return (
              <li key={domain} data-tone={look?.tone} data-empty={count ? undefined : true}>
                {look && (
                  <i aria-hidden="true">
                    <Icon name={look.icon} width={17} height={17} />
                  </i>
                )}
                <span>{domain}</span>
                <b>{count ?? "—"}</b>
              </li>
            );
          })}
        </ul>
      </section>

      <Link
        href={`/records/journal?child=${encodeURIComponent(CHILD_PREFIX + child.child_id)}`}
        className={styles.journalGo}
      >
        관찰일지 작성 →
      </Link>

      {/* 본문 조회 오류가 다른 아동의 선택을 막지 않게 상세 안에서 안내한다. */}
      {failed && (
        <Message error>기록을 불러오지 못했어요. 다른 아이를 골랐다가 다시 열어주세요.</Message>
      )}
      {!failed && records === null && <TrackingState loading title="기록을 불러오고 있어요" />}
      {!failed && records !== null && <Timeline records={records} writeHref={writeHref} />}
    </section>
  );
}

/**
 * 날짜별 기록. 관찰 기록 화면과 같은 영수증 종이 한 장이다 —
 * 줄마다 테두리를 두르면 목록이 아니라 카드 더미가 된다.
 * 월 제목은 묶음을 알려주고, 서버가 준 최신순은 다시 매기지 않는다.
 */
function Timeline({ records, writeHref }: { records: ApiObservation[]; writeHref: string }) {
  if (!records.length) {
    return (
      <TrackingState title="아직 적은 기록이 없어요">
        <p>아이의 말과 행동을 한 줄씩 적어 둡니다.</p>
        <Link href={writeHref} className={styles.action}>
          <Icon name="edit" />
          기록 적으러 가기 →
        </Link>
      </TrackingState>
    );
  }
  // 구형 iPad Safari에서도 동작하도록 기존 Map 순서와 날짜 묶음을 유지한다.
  const months = new Map<string, ApiObservation[]>();
  for (const record of records)
    months.set(record.date.slice(0, 7), [...(months.get(record.date.slice(0, 7)) ?? []), record]);
  return (
    <section className={styles.timeline}>
      <div className={styles.timelineHead}>
        <h3>날짜별 기록</h3>
        <span className={styles.timelineCount}>기록 {records.length}건</span>
      </div>
      <div className={styles.slip}>
        {[...months].map(([month, items]) => (
          <section key={month} aria-label={`${month} 기록`}>
            <h4 className={styles.monthLine}>
              {month.slice(0, 4)}년 {Number(month.slice(5))}월 <span>{items.length}건</span>
            </h4>
            {items.map((record) => {
              const look = DOMAIN_LOOK[record.domain];
              return (
                <article className={styles.slipLine} key={record.id}>
                  <time dateTime={record.date}>{shortDate(record.date)}</time>
                  <div>
                    <span className={styles.domainTag} data-tone={look?.tone}>
                      {look && <Icon name={look.icon} width={12} height={12} />}
                      {record.domain}
                    </span>
                    <p>{record.fact}</p>
                  </div>
                </article>
              );
            })}
          </section>
        ))}
      </div>
    </section>
  );
}

function TrackingState({
  title,
  loading = false,
  children,
}: {
  title: string;
  loading?: boolean;
  children?: ReactNode;
}) {
  return (
    <div
      className={styles.emptyState}
      role={loading ? "status" : undefined}
      aria-busy={loading || undefined}
    >
      <ObservationArt className={styles.emptyArt} />
      <h3>{title}</h3>
      {children}
    </div>
  );
}

/** 「2026-11-03」 을 「11.03」 으로. 달 제목이 해를 이미 말한다. */
function shortDate(date: string) {
  const [, m, d] = date.split("-");
  return m && d ? `${m}.${d}` : date;
}
