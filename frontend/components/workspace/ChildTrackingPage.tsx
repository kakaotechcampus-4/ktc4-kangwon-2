"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { getMe } from "@/lib/api/auth";
import { getChildren } from "@/lib/api/children";
import { getClasses } from "@/lib/api/classes";
import { getObservations } from "@/lib/api/observations";
import type { ApiChild, ApiClass, ApiObservation } from "@/lib/api/types";
import { DOMAINS } from "@/lib/workspace/model";
import { WorkspacePage, Empty, Message, ws } from "./WorkspaceUI";

/** 반 하나의 아동 명단과 관찰 기록. 기록은 한 번에 받아 화면에서 아이별로 나눈다. */
interface ClassData {
  classId: number;
  children: ApiChild[];
  records: ApiObservation[];
}

const FAILED = "기록을 불러오지 못했어요. 잠시 뒤 다시 열어주세요.";

/**
 * 발달 추적 — 아이 한 명의 관찰 기록을 모아 본다.
 *
 * **조회만 한다.** 발달 수준을 판정하지 않는다 — 판정은 ADR-007 이 스펙아웃한 발달평가다.
 * 영역별 개수는 「어느 영역을 덜 봤나」를 교사가 알게 하는 용도다.
 *
 * 서버에서 바로 읽고 브라우저에 저장하지 않는다 — 아동 실명이 담긴다 (ADR-013).
 */
export default function ChildTrackingPage() {
  const [classes, setClasses] = useState<ApiClass[] | null>(null);
  const [classData, setClassData] = useState<ClassData | null>(null);
  const [pickedClass, setPickedClass] = useState<number | null>(null);
  const [pickedChild, setPickedChild] = useState<number | null>(null);
  const [error, setError] = useState("");

  const classId = pickedClass ?? classes?.[0]?.id ?? null;

  useEffect(() => {
    getMe()
      .then((me) => (me.center_id ? getClasses(me.center_id) : { items: [] }))
      .then(({ items }) => setClasses(items))
      .catch(() => setError(FAILED));
  }, []);

  useEffect(() => {
    if (classId === null) return;
    let stale = false;
    Promise.all([getChildren(classId), getObservations({ class_id: classId })])
      .then(([children, records]) => {
        if (!stale) setClassData({ classId, children: children.items, records: records.items });
      })
      .catch(() => !stale && setError(FAILED));
    return () => {
      stale = true;
    };
  }, [classId]);

  function pickClass(id: number) {
    setPickedClass(id);
    setPickedChild(null);
  }

  return (
    <WorkspacePage title="아이별 모아보기" description="한 아이의 관찰 기록을 모아서 봐요.">
      <Message error>{error}</Message>
      {/* 실패했는데 「불러오는 중」을 같이 띄우면 교사는 계속 기다린다. */}
      {!error && (
        <Body
          classes={classes}
          classId={classId}
          classData={classData?.classId === classId ? classData : null}
          pickedChild={pickedChild}
          onPickClass={pickClass}
          onPickChild={setPickedChild}
        />
      )}
    </WorkspacePage>
  );
}

function Body({
  classes,
  classId,
  classData,
  pickedChild,
  onPickClass,
  onPickChild,
}: {
  classes: ApiClass[] | null;
  classId: number | null;
  classData: ClassData | null;
  pickedChild: number | null;
  onPickClass: (id: number) => void;
  onPickChild: (id: number) => void;
}) {
  if (!classes) return <p className={ws.muted}>불러오는 중이에요…</p>;
  if (!classes.length) {
    return (
      <Empty title="먼저 우리 반과 아동을 등록해주세요">
        <Link href="/onboarding">반·아동 등록하기 →</Link>
      </Empty>
    );
  }
  return (
    <div className={ws.grid}>
      <section className={ws.card}>
        {classes.length > 1 && (
          <label className={ws.field}>
            반
            <select value={classId ?? ""} onChange={(e) => onPickClass(Number(e.target.value))}>
              {classes.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <ChildList classData={classData} pickedChild={pickedChild} onPick={onPickChild} />
      </section>
      <ChildDetail classData={classData} pickedChild={pickedChild} />
    </div>
  );
}

function ChildList({
  classData,
  pickedChild,
  onPick,
}: {
  classData: ClassData | null;
  pickedChild: number | null;
  onPick: (id: number) => void;
}) {
  if (!classData) return <p className={ws.muted}>불러오는 중이에요…</p>;
  if (!classData.children.length) {
    return (
      <Empty title="이 반에 등록된 아동이 없어요">
        <Link href="/onboarding/children">아동 등록하기 →</Link>
      </Empty>
    );
  }
  const selected = pickedChild ?? classData.children[0].id;
  return (
    <ul className={ws.list} aria-label="아동 목록">
      {classData.children.map((child) => (
        <li key={child.id}>
          <button
            type="button"
            className={child.id === selected ? ws.primary : ws.secondary}
            aria-pressed={child.id === selected}
            onClick={() => onPick(child.id)}
          >
            {child.name} · {classData.records.filter((r) => r.child_id === child.id).length}건
          </button>
        </li>
      ))}
    </ul>
  );
}

function ChildDetail({
  classData,
  pickedChild,
}: {
  classData: ClassData | null;
  pickedChild: number | null;
}) {
  const child = classData?.children.find((c) => c.id === pickedChild) ?? classData?.children[0];
  // 서버가 date 내림차순으로 준다 (§10). 순서를 다시 매기지 않는다.
  const records = useMemo(
    () => classData?.records.filter((r) => r.child_id === child?.id) ?? [],
    [classData, child],
  );
  if (!child) return null;
  return (
    <section className={ws.stack}>
      <div className={ws.card}>
        <div className={ws.between}>
          <h2>{child.name}</h2>
          {/* 코드는 늘 받침 있는 더미 이름이라(CLAUDE.md 개인정보) 조사를 「으로」로 고정한다. */}
          <span className={ws.badge}>AI 에는 「{child.code}」으로 나가요</span>
        </div>
        <p className={ws.muted}>관찰 기록 {records.length}건</p>
      </div>
      <DomainCounts records={records} />
      <Timeline records={records} />
    </section>
  );
}

/** 5영역별 기록 수. 0 인 영역은 「아직 기록 없음」 — 덜 본 영역을 교사가 알게 한다. */
function DomainCounts({ records }: { records: ApiObservation[] }) {
  return (
    <div className={ws.cards} aria-label="영역별 기록 수">
      {DOMAINS.map((domain) => {
        const count = records.filter((r) => r.domain === domain).length;
        return (
          <div className={ws.card} key={domain}>
            <p className={ws.muted}>{domain}</p>
            <strong className={ws.count}>{count}</strong>
            {!count && <p className={ws.muted}>아직 기록 없음</p>}
          </div>
        );
      })}
    </div>
  );
}

/** 월별로 묶은 기록. 서버 순서(최신순)를 그대로 따른다. */
function Timeline({ records }: { records: ApiObservation[] }) {
  if (!records.length) {
    return (
      <Empty title="아직 남긴 기록이 없어요">
        <Link href="/records">관찰 기록 남기기 →</Link>
      </Empty>
    );
  }
  // Map.groupBy 는 구형 iPad Safari(17.4 미만)에 없다. 넣은 순서 = 최신 달부터다.
  const months = new Map<string, ApiObservation[]>();
  for (const r of records)
    months.set(r.date.slice(0, 7), [...(months.get(r.date.slice(0, 7)) ?? []), r]);
  return (
    <div className={`${ws.card} ${ws.stack}`}>
      {[...months].map(([month, items]) => (
        <section key={month} aria-label={`${month} 기록`}>
          <h3>
            {Number(month.slice(5))}월 <span className={ws.muted}>{items.length}건</span>
          </h3>
          <div className={ws.list}>
            {items.map((r) => (
              <article className={ws.item} key={r.id}>
                <div className={ws.between}>
                  <p className={ws.muted}>
                    {r.date} {r.context && `· ${r.context}`}
                  </p>
                  <span className={ws.badge}>{r.domain}</span>
                </div>
                <p>{r.fact}</p>
              </article>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
