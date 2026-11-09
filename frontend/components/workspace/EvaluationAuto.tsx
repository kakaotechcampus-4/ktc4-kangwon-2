"use client";

import { useState } from "react";
import Link from "next/link";
import type { AutoIndicator } from "@/lib/api/evaluation";
import { ws } from "./WorkspaceUI";
import EvidenceImport from "./EvidenceImport";
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

/** `date`(YYYY-MM-DD)는 시간대가 없어 잘라 써도 된다. 끝 날짜는 해가 같으면 해를 뺀다. */
function periodText(from: string, to: string) {
  const [fy, fm, fd] = from.split("-").map(Number);
  const [ty, tm, td] = to.split("-").map(Number);
  return `검토 기간 ${fy}년 ${fm}월 ${fd}일 ~ ${ty === fy ? "" : `${ty}년 `}${tm}월 ${td}일`;
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
        월간계획안 · 보육일지를 다 채운 반 · {classes.total}개 반 중 {classes.met}개 반
        <Bar value={percent(classes.met, classes.total)} />
      </p>
      <Requirement
        done={plans > 0}
        need="반마다 확정한 월간계획안 1건 이상"
        have={`확정 월간계획안 ${plans}건`}
        href="/plans/monthly"
        action="월간계획안 만들기"
      />
      {/* 서버는 일일 보육일지만 센다(ADR-057 결과). 「집계에 들어간 문서」 펼침을 지우며 「일일」을 여기로 옮겼다(11-09). */}
      <Requirement
        done={logs > 0}
        need="검토 기간 평일마다 확정한 일일 보육일지"
        have={`확정 보육일지 ${logs}건`}
        href="/routines"
        action="보육일지 쓰기"
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
        need="아이마다 확정한 영유아 평가 2건 이상"
        have={`${children.total}명 중 ${children.met}명 채움 · 관찰일지는 평가로 치지 않아요`}
        bar={percent(children.met, children.total)}
        href="/documents?kind=assessment"
        action="영유아 평가 쓰기"
        primary
      />
    </div>
  );
}

/**
 * api-spec §12 가 요구하는 뜻(공휴일 · 방학 · 학년도 경계 / 입소 6개월 · 연 1회 · 2회로 셈 · 재등록)은 다 남기고
 * 이어 붙인 문장만 나눴다(11-09 문구 토론). 개별화교육계획은 이제 자기 카드가 있어 4-1 안내에서 뺐다.
 */
function notesFor(item: AutoIndicator) {
  const period = periodText(item.period.from, item.period.to);
  if (item.indicator === "4-1")
    return [
      `${period}. 오늘 쓴 일지는 내일 숫자에 들어가요.`,
      "공휴일 · 방학도 빈 날로 세어요. 3월에는 지난 학년도 반이 빠져 실제보다 부족하게 보일 수 있어요.",
      "4-1의 「5세 초등학교 전이 활동」은 세지 않아요. 해당하면 따로 챙겨 주세요.",
    ];
  return [
    `${period}. 입소 6개월이 안 된 아이는 평가 대상이 아니고, 6~12개월은 1번이면 돼요.`,
    "쌤플은 입소일을 몰라 모두 2번으로 세서 실제보다 부족하게 보일 수 있어요.",
    "새 학년도에 아이를 다시 등록했다면 지난 학년도 평가는 안 세어질 수 있어요.",
  ];
}

/** 4-1 은 일일 보육일지, 4-2 는 영유아 평가만 센다(§12). 올릴 수 있는 종류도 그것뿐이다. */
const IMPORT = {
  "4-1": { kind: "dailyLog", label: "예전 보육일지 올리기" },
  "4-2": { kind: "assessment", label: "예전 평가 올리기" },
} as const;

function AutoCard({ item, onImported }: { item: AutoIndicator; onImported: () => void }) {
  const [importing, setImporting] = useState(false);
  const importId = `eval-import-${item.indicator}`;
  const upload = IMPORT[item.indicator as keyof typeof IMPORT];
  return (
    <section className={styles.card} aria-label={`${item.indicator} ${item.title}`}>
      <p className={styles.kicker}>
        <span className={`${styles.chip} ${styles[item.verdict]}`}>{VERDICT[item.verdict]}</span>
        {item.indicator} {item.title}
      </p>
      <div className={styles.titleRow}>
        <h3>{QUESTION[item.indicator] ?? item.title}</h3>
        <div className={styles.links}>
          {upload && (
            <button
              type="button"
              className={styles.linkButton}
              aria-expanded={importing}
              aria-controls={importId}
              onClick={() => setImporting(!importing)}
            >
              {upload.label} ▾
            </button>
          )}
        </div>
      </div>
      {/* 펼친 내용은 누른 버튼 바로 밑에 둔다. 아래에 열리면 무엇이 열렸는지 찾아야 한다. */}
      {upload && (
        <div id={importId} hidden={!importing}>
          <EvidenceImport kind={upload.kind} onImported={onImported} />
        </div>
      )}
      {/* 「집계에 들어간 문서」 펼침은 지웠다 — 아래 두 줄 숫자의 합일 뿐이었다(11-09 문구 토론). */}
      {item.indicator === "4-1" ? (
        <ClassRequirements item={item} />
      ) : (
        <ChildRequirement item={item} />
      )}
      <ul className={styles.notes}>
        {notesFor(item).map((note) => (
          <li key={note}>{note}</li>
        ))}
      </ul>
    </section>
  );
}

/** 문서 탭 — 확정 문서를 세기만 한다. 충족을 확인해 주지 않는다(ADR-019 · ADR-022). */
export default function EvaluationAuto({
  items,
  onImported,
}: {
  items: AutoIndicator[];
  /** 예전 서류를 올리면 숫자를 다시 받는다. */
  onImported: () => void;
}) {
  return (
    <div className={ws.stack}>
      {/* 「세기만」 — 센 것이지 충족을 확인한 것이 아니라는 api-spec §12 의 뜻을 한 절로 둔다. 제목은 서랍 머리줄이 맡는다. */}
      <p className={ws.hint}>쌤플에서 확정했거나 올린 문서를 세기만 해요.</p>
      {items.map((item) => (
        <AutoCard key={item.indicator} item={item} onImported={onImported} />
      ))}
    </div>
  );
}
