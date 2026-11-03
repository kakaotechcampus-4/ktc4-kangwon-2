"use client";
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { getMe } from "@/lib/api/auth";
import { getChildTracking } from "@/lib/api/children";
import { getClasses } from "@/lib/api/classes";
import { getObservations } from "@/lib/api/observations";
import { useClientState } from "@/lib/hooks/use-client-state";
import { useObservationDomains } from "@/lib/hooks/use-observation-domains";
import { CHILD_PREFIX, CLASS_PREFIX, classServerId } from "@/lib/api/onboarding";
import { chosenClassFor, loadClassSettings } from "@/lib/onboarding/settings";
import { AXES, DEFAULT_AXIS, type ObservationAxis } from "@/lib/workspace/observation-axis";
import type { ApiChildTracking, ApiClass, ApiObservation } from "@/lib/api/types";
import { Icon } from "@/components/app/icons";
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

/**
 * 발달 추적 — 아이 한 명의 관찰 기록을 모아 본다.
 *
 * **조회만 한다.** 발달 수준을 판정하지 않는다 — 판정은 ADR-007 이 스펙아웃한 발달평가다.
 * 영역별 개수는 「어느 영역을 덜 봤나」를 교사가 알게 하는 용도다. 서버가 센다 (§2-1).
 *
 * 서버에서 바로 읽고 브라우저에 저장하지 않는다 — 아동 실명이 담긴다 (ADR-013).
 */
export default function ChildTrackingPage() {
  const [classes, setClasses] = useState<ApiClass[] | null>(null);
  const [classData, setClassData] = useState<ClassData | null>(null);
  const [pickedChild, setPickedChild] = useState<number | null>(null);
  const [error, setError] = useState("");
  const configuredDomains = useObservationDomains();
  // 기존 훅은 설정을 읽기 전이나 실패했을 때 DEFAULT_AXIS의 상수 배열을 반환한다.
  const defaultAxis: ObservationAxis =
    configuredDomains === AXES.DAILY_PLAY_2 ? "DAILY_PLAY_2" : DEFAULT_AXIS;
  const [axisSelection, setAxisSelection] = useState<{
    classId: number;
    axis: ObservationAxis;
  } | null>(null);

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
  const axis = axisSelection?.classId === classId ? axisSelection.axis : defaultAxis;

  useEffect(() => {
    getMe()
      .then((me) => (me.center_id ? getClasses(me.center_id) : { items: [] }))
      .then(({ items }) => setClasses(items))
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
  const child =
    current?.children.find((c) => c.child_id === pickedChild) ?? current?.children[0] ?? null;

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1>아이별 기록</h1>
          <p>아이를 고르면 그 아이 기록만 봅니다.</p>
        </div>
      </header>
      <Message error>{error}</Message>
      {/* 조회가 실패하면 로딩 안내를 함께 보여주지 않는다. */}
      {!error && (
        <Body
          classes={classes}
          classId={classId}
          classData={current}
          child={child}
          axis={axis}
          onPickAxis={(next) => {
            if (classId !== null) setAxisSelection({ classId, axis: next });
          }}
          onPickChild={setPickedChild}
        />
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

function Body({
  classes,
  classId,
  classData,
  child,
  axis,
  onPickAxis,
  onPickChild,
}: {
  classes: ApiClass[] | null;
  classId: number | null;
  classData: ClassData | null;
  child: ApiChildTracking | null;
  axis: ObservationAxis;
  onPickAxis: (axis: ObservationAxis) => void;
  onPickChild: (id: number) => void;
}) {
  if (!classes) return <TrackingState loading title="기록을 불러오고 있어요" />;
  if (!classes.length) {
    return (
      <TrackingState title="먼저 아이를 등록해 주세요">
        <Link href="/onboarding" className={styles.action}>
          반·아동 등록하기 →
        </Link>
      </TrackingState>
    );
  }
  const className = classes.find((item) => item.id === classId)?.name ?? "";
  return (
    <div className={styles.workspace}>
      <aside className={styles.selector} aria-label="아이 고르기">
        {/* 반은 사이드바 맨 위에서 고른다. 여기에 또 두면 두 곳에서 같은 것을 고르게 된다. */}
        <div className={styles.selectorHead}>
          <h2>아이 고르기</h2>
          <p>고른 아이의 기록만 봅니다.</p>
        </div>
        <ChildList
          key={classId ?? "loading"}
          classData={classData}
          selected={child?.child_id ?? null}
          onPick={onPickChild}
        />
      </aside>
      {/* 아이를 바꾸면 이전 아이의 본문을 즉시 걷고 새로 조회한다. */}
      {child && (
        <ChildDetail
          key={`${classId}:${child.child_id}`}
          child={child}
          className={className}
          writeHref={recordsHref(classId, child.child_id)}
          axis={axis}
          onPickAxis={onPickAxis}
        />
      )}
      {!child && (
        <TrackingState
          loading={!classData}
          title={classData ? "아직 적은 기록이 없어요" : "아이 정보를 불러오고 있어요"}
        >
          {classData && <p>반에 아동을 등록하면 아이별로 관찰을 모아 볼 수 있어요.</p>}
        </TrackingState>
      )}
    </div>
  );
}

function ChildList({
  classData,
  selected,
  onPick,
}: {
  classData: ClassData | null;
  selected: number | null;
  onPick: (id: number) => void;
}) {
  if (!classData)
    return (
      <p role="status" className={styles.helper}>
        아이 목록을 불러오고 있어요…
      </p>
    );
  if (!classData.children.length) {
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
    <>
      <p className={styles.rosterLabel}>
        아이 <span>{classData.children.length}명</span>
      </p>
      <ul className={styles.childList} aria-label="아이 목록">
        {classData.children.map((item) => (
          <li key={item.child_id}>
            <button
              type="button"
              className={styles.childCard}
              aria-label={`${item.name} · ${item.total}건`}
              aria-pressed={item.child_id === selected}
              onClick={() => onPick(item.child_id)}
            >
              <span className={styles.childInfo}>
                <strong>{item.name}</strong>
                <small>기록 {item.total}건</small>
              </span>
              <Icon name="chevron" />
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}

function ChildDetail({
  child,
  className,
  writeHref,
  axis,
  onPickAxis,
}: {
  child: ApiChildTracking;
  className: string;
  writeHref: string;
  axis: ObservationAxis;
  onPickAxis: (axis: ObservationAxis) => void;
}) {
  const [records, setRecords] = useState<ApiObservation[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let stale = false;
    // 서버가 date 내림차순으로 준다 (§10). 순서를 다시 매기지 않는다.
    getObservations({ child_id: child.child_id })
      .then(({ items }) => !stale && setRecords(items))
      .catch(() => !stale && setFailed(true));
    return () => {
      stale = true;
    };
  }, [child.child_id]);

  return (
    <section className={styles.detail} aria-label={`${child.name} 관찰 기록`}>
      <div className={styles.summary}>
        <div className={styles.summaryText}>
          <span className={styles.eyebrow}>{className}</span>
          <h2>{child.name}</h2>
          <p className={styles.recordTotal}>기록 {child.total}건</p>
        </div>
        <Link href={writeHref} className={styles.action}>
          전체 기록에서 보기 →
        </Link>
      </div>
      <DomainCounts
        counts={child.by_domain}
        total={child.total}
        axis={axis}
        onPickAxis={onPickAxis}
      />
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
 * 고른 기준의 카드는 빈 집계에서도 늘 유지한다 — 5영역은 5장, 놀이·일상생활은 2장.
 * 전체 0건이 확인된 경우만 누락된 영역을 0건으로 채우고, 기록이 있는데 그 기준의 키가
 * 없으면 숫자를 추정하지 않고 카드 안에서 「정보 없음」으로 안내한다.
 */
function DomainCounts({
  counts,
  total,
  axis,
  onPickAxis,
}: {
  counts: Record<string, number>;
  total: number;
  axis: ObservationAxis;
  onPickAxis: (axis: ObservationAxis) => void;
}) {
  const playLife = axis === "DAILY_PLAY_2";
  // 저장 계약의 두 영역을 그대로 쓰되, 시안처럼 놀이활동을 먼저 배치한다.
  const domains = playLife ? [...AXES[axis]].reverse() : AXES[axis];
  return (
    <section className={styles.domainSection} aria-label="영역별 기록 수">
      <div className={styles.sectionHead}>
        <div className={styles.sectionTitleRow}>
          <h3>영역별 기록 수</h3>
          <div className={styles.axisSwitch} role="group" aria-label="관찰 영역 보기 기준">
            <button
              type="button"
              aria-pressed={axis === "NURI_5"}
              onClick={() => onPickAxis("NURI_5")}
            >
              누리과정 5영역
            </button>
            <button
              type="button"
              aria-pressed={playLife}
              onClick={() => onPickAxis("DAILY_PLAY_2")}
            >
              놀이·일상생활
            </button>
          </div>
        </div>
        <p>관찰한 횟수입니다. 발달 수준을 뜻하지 않습니다.</p>
      </div>
      <ul className={styles.domainRow} data-axis={axis}>
        {domains.map((domain) => {
          // tracking 조회가 성공해 전체 0건임을 알 때만 누락 키를 0으로 보충한다.
          // 기록이 있는 아동의 누락 키는 숫자를 추정하지 않고 「—」 로 둔다.
          const count: number | undefined = counts[domain] ?? (total === 0 ? 0 : undefined);
          return (
            <li key={domain} data-empty={count ? undefined : true}>
              <span>{domain}</span>
              <b>{count ?? "—"}</b>
            </li>
          );
        })}
      </ul>
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
      <div aria-hidden="true" className="slipEdge top" />
      <div className={styles.slip}>
        {[...months].map(([month, items]) => (
          <section key={month} aria-label={`${month} 기록`}>
            <h4 className={styles.monthLine}>
              {month.slice(0, 4)}년 {Number(month.slice(5))}월 <span>{items.length}건</span>
            </h4>
            {items.map((record) => (
              <article className={styles.slipLine} key={record.id}>
                <time dateTime={record.date}>{shortDate(record.date)}</time>
                <div>
                  <span className={styles.domainTag}>{record.domain}</span>
                  <p>{record.fact}</p>
                </div>
              </article>
            ))}
          </section>
        ))}
      </div>
      <div aria-hidden="true" className="slipEdge bottom" />
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
