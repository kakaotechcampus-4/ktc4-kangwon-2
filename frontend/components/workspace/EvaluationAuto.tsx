"use client";

import { useState } from "react";
import Link from "next/link";
import type { AutoIndicator } from "@/lib/api/evaluation";
import { ws } from "./WorkspaceUI";
import styles from "./Evaluation.module.css";

const VERDICT = {
  SUPPORTED: "기준 건수 충족",
  INSUFFICIENT: "보완 필요",
  NONE: "아직 없음",
};

/** 공식 평가항목 이름은 작게 두고, 교사가 스스로 물어볼 말로 크게 적는다. */
const QUESTION: Record<string, string> = {
  "4-1": "관찰을 바탕으로 계획하고, 매일 기록했나요?",
  "4-2": "아이마다 1년에 2번 이상 발달 평가를 했나요?",
};

/** 서버가 아직 목록을 주지 않는 링크. 누르면 준비 중이라고만 알린다. */
const LIST_LINK: Record<string, string> = {
  "4-1": "빈 날짜 보기",
  "4-2": "부족한 아동 보기",
};

/** `date`(YYYY-MM-DD)는 시간대가 없어 잘라 써도 된다. */
function longDate(value: string) {
  const [y, m, d] = value.split("-").map(Number);
  return `${y}년 ${m}월 ${d}일`;
}

function percent(met: number, total: number) {
  return total ? Math.round((met / total) * 100) : 0;
}

function Bar({ value }: { value: number }) {
  return (
    <span className={styles.bar} aria-hidden="true">
      <span style={{ width: `${value}%` }} />
    </span>
  );
}

function Requirement({
  done,
  need,
  have,
  bar,
  href,
  action,
  primary = false,
}: {
  done: boolean;
  need: string;
  have: string;
  bar?: number;
  href: string;
  action: string;
  primary?: boolean;
}) {
  return (
    <div className={styles.requirement}>
      <span className={`${styles.mark} ${done ? styles.markDone : ""}`} aria-hidden="true">
        {done ? "✓" : "!"}
      </span>
      <div className={styles.requirementText}>
        <strong>{need}</strong>
        <span>{have}</span>
        {bar !== undefined && <Bar value={bar} />}
      </div>
      <Link href={href} className={primary ? ws.primary : ws.secondary}>
        {action}
      </Link>
    </div>
  );
}

/**
 * 4-1 — 서버는 「두 조건을 다 채운 반」 수 하나만 준다(judge_4_1).
 * 계획안 · 일지를 따로 채운 반 수는 모르므로 줄마다 건수만 보이고 「채움」이라 하지 않는다.
 */
function ClassRequirements({ item }: { item: AutoIndicator }) {
  const classes = item.classes ?? { met: 0, total: 0 };
  const plans = item.plan_ids.length;
  const logs = item.document_ids.length;
  return (
    <div className={styles.requirements}>
      <p className={styles.ratio}>
        두 조건을 다 채운 반 · {classes.total}개 반 중 {classes.met}개 반
        <Bar value={percent(classes.met, classes.total)} />
      </p>
      <Requirement
        done={plans > 0}
        need="반마다 확정된 월간계획안 1건 이상"
        have={`확정 월간계획안 ${plans}건`}
        href="/plans/monthly"
        action="월간계획안 만들기"
      />
      <Requirement
        done={logs > 0}
        need="검토 기간 평일마다 확정된 보육일지"
        have={`확정 보육일지 ${logs}건`}
        href="/routines"
        action="보육일지 쓰러 가기"
        primary
      />
    </div>
  );
}

function ChildRequirement({ item }: { item: AutoIndicator }) {
  const children = item.children ?? { met: 0, total: 0 };
  return (
    <div className={styles.requirements}>
      <Requirement
        done={children.total > 0 && children.met === children.total}
        need="아동마다 확정된 영유아 평가 2건"
        have={`${children.total}명 중 ${children.met}명 채움 · 관찰일지 수로 대신 세지 않아요`}
        bar={percent(children.met, children.total)}
        href="/documents"
        action="영유아 평가 작성하기"
        primary
      />
    </div>
  );
}

function notesFor(item: AutoIndicator) {
  const period = `검토 기간 ${longDate(item.period.from)} ~ ${longDate(item.period.to)}`;
  if (item.indicator === "4-1")
    return [
      `${period} · 공휴일·방학은 빼지 않고, 학년도가 바뀌면 지난 학년도 반이 빠져서 실제보다 부족하게 보일 수 있어요. 오늘 쓴 일지는 내일부터 세요.`,
      "4-1의 「5세 초등학교 전이 활동」과 「장애영유아 개별화교육계획」은 세지 않아요. 해당하면 따로 챙겨 주세요.",
    ];
  return [
    `${period} · 입소 6개월 미만은 공식 평가 대상이 아니고, 6~12개월은 연 1회면 돼요. 입소일을 몰라 모두 2회로 세서 실제보다 부족하게 보일 수 있어요.`,
    "새 학년도에 아동을 다시 등록했다면 지난 학년도 평가가 빠질 수 있어요.",
  ];
}

function AutoCard({ item }: { item: AutoIndicator }) {
  const [counted, setCounted] = useState(false);
  const [soon, setSoon] = useState(false);
  const countedId = `eval-counted-${item.indicator}`;
  return (
    <section className={styles.card} aria-label={`${item.indicator} ${item.title}`}>
      <p className={styles.kicker}>
        <span className={`${styles.chip} ${styles[item.verdict]}`}>{VERDICT[item.verdict]}</span>
        {item.indicator} {item.title}
      </p>
      <div className={styles.titleRow}>
        <h3>{QUESTION[item.indicator] ?? item.title}</h3>
        <div className={styles.links}>
          {LIST_LINK[item.indicator] && (
            <button type="button" className={styles.linkButton} onClick={() => setSoon(true)}>
              {LIST_LINK[item.indicator]} ▾
            </button>
          )}
          {item.indicator === "4-1" && (
            <button
              type="button"
              className={styles.linkButton}
              aria-expanded={counted}
              aria-controls={countedId}
              onClick={() => setCounted(!counted)}
            >
              집계에 들어간 문서 {item.count}건 ▾
            </button>
          )}
        </div>
      </div>
      <p role="status" className={styles.soon}>
        {soon && "이 목록은 아직 준비 중이에요. 지금은 아래 숫자로 확인해 주세요."}
      </p>
      {item.indicator === "4-1" ? (
        <ClassRequirements item={item} />
      ) : (
        <ChildRequirement item={item} />
      )}
      <div id={countedId} className={styles.counted} hidden={!counted}>
        반마다 검토 기간의 확정 월간계획안과, 평일마다 확정한 일일 보육일지를 세요. 월간계획안{" "}
        {item.plan_ids.length}건 · 보육일지 {item.document_ids.length}건
      </div>
      <ul className={styles.notes}>
        {notesFor(item).map((note) => (
          <li key={note}>{note}</li>
        ))}
      </ul>
    </section>
  );
}

/** 문서 탭 — 확정 문서를 세기만 한다. 충족을 확인해 주지 않는다(ADR-019 · ADR-022). */
export default function EvaluationAuto({ items }: { items: AutoIndicator[] }) {
  return (
    <div className={ws.stack}>
      <div>
        <h2 className={styles.sectionTitle}>확정 문서로 확인하는 평가항목</h2>
        <p className={ws.hint}>
          쌤플에서 확정한 문서를 세어 봐요. 세어 준 것이지 충족을 확인해 준 것이 아니에요.
        </p>
      </div>
      {items.map((item) => (
        <AutoCard key={item.indicator} item={item} />
      ))}
    </div>
  );
}
