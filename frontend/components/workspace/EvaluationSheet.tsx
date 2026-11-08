"use client";

import { useRef, useState, type ChangeEvent } from "react";
import Link from "next/link";
import type { AutoIndicator } from "@/lib/api/evaluation";
import {
  DIRECTOR_ITEMS,
  TEACHER_DOCS,
  gapText,
  scanNames,
  sourceLines,
  stampSources,
  type DocResult,
  type Scan,
  type StampSource,
  type TeacherDoc,
} from "@/lib/workspace/evaluation-files";
import { today } from "@/lib/workspace/model";
import { Posty } from "@/components/app/Posty";
import { Icon } from "@/components/app/icons";
import { ws } from "./WorkspaceUI";
import EvidenceImport from "./EvidenceImport";
import styles from "./Evaluation.module.css";

const WEEKDAY = ["일", "월", "화", "수", "목", "금", "토"];

/** `2026-10-15` → `10월 15일(목)`, `2026-09` → `9월` */
function shortDate(value: string) {
  const [y, m, d] = value.split("-").map(Number);
  if (!d) return `${m}월`;
  return `${m}월 ${d}일(${WEEKDAY[new Date(y, m - 1, d).getDay()]})`;
}

/** 접힌 칸 앞의 꺾쇠. 열렸는지 닫혔는지 글자만으로는 몰랐다. */
export function FoldMark() {
  return (
    <svg className={styles.foldMark} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path
        d="M9 5.5 16.5 12 9 18.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** 서류 한 줄에서 쌤플이 아는 쪽. 쌤플이 만들지 않는 서류는 `null` 이다. */
interface Made {
  /** 「확정 24건」처럼 한 줄로 읽히는 숫자 */
  text: string;
  done: boolean;
  /** 기준은 못 채웠지만 확정한 문서가 있다 — 근거 줄을 점선(모자람)으로 보인다 */
  some: boolean;
  /** 채울 서류 카드에 「무엇이 모자라요」로 적는 말. 기준을 채웠으면 없다 */
  need?: string;
  /** 지금 손댈 수 있는 길. 없으면 단추를 두지 않는다. */
  go?: { href: string; label: string };
  /** 예전 서류를 올려 같이 세게 할 수 있는 서류만 */
  importKind?: "dailyLog" | "assessment";
}

/**
 * 쌤플 문서와 평가 서류를 잇는다.
 *
 * 서버는 평가항목(4-1 · 4-2) 단위로 센다. 교사가 평가 당일 꺼내는 단위는 서류다.
 * 그래서 여기서 한 번 옮겨 적는다 — **숫자를 다시 만들지 않고 서버가 준 것만 옮긴다.**
 * 보육일지 · 계획안을 반마다 따로 센 수는 서버 저장(PR ②) 뒤에 온다. 그 전에는 건수만 보인다.
 */
function madeInSsample(docId: string, autos: AutoIndicator[]): Made | null {
  const by = (indicator: string) => autos.find((item) => item.indicator === indicator);
  if (docId === "journal") {
    const item = by("4-1");
    if (!item) return null;
    const count = item.document_ids.length;
    return {
      text: `확정 ${count}건`,
      done: count > 0,
      some: count > 0,
      need: count ? undefined : "검토 기간에 확정한 보육일지가 없어요",
      go: { href: "/routines", label: "보육일지 쓰기" },
      importKind: "dailyLog",
    };
  }
  if (docId === "plan") {
    const item = by("4-1");
    if (!item) return null;
    const count = item.plan_ids.length;
    return {
      text: `확정 ${count}건`,
      done: count > 0,
      some: count > 0,
      need: count ? undefined : "검토 기간에 확정한 월간계획안이 없어요",
      go: { href: "/plans/monthly", label: "월간계획안 만들기" },
    };
  }
  if (docId === "assessment") {
    const item = by("4-2");
    if (!item) return null;
    const children = item.children ?? { met: 0, total: 0 };
    const done = children.total > 0 && children.met === children.total;
    return {
      text: `${children.total}명 중 ${children.met}명`,
      done,
      some: item.document_ids.length > 0,
      need: done
        ? undefined
        : children.total
          ? `${children.total - children.met}명이 아직 ${item.required ?? 2}번을 못 채웠어요`
          : "반에 등록한 아이가 없어요",
      go: { href: "/documents?kind=assessment", label: "영유아 평가 쓰기" },
      importKind: "assessment",
    };
  }
  return null;
}

/** 그 서류가 걸린 평가항목. 서류 설명 첫머리에 이미 적혀 있어 거기서 떼어 쓴다. */
function indicatorOf(doc: TeacherDoc) {
  return doc.basis.split(" · ")[0];
}

/** 평가항목 번호를 뺀 나머지 설명(기간 · 횟수) */
function basisOf(doc: TeacherDoc) {
  return doc.basis.split(" · ").slice(1).join(" · ");
}

/** 이름 규칙과 검사 결과. 찾은 이름은 화면에만 보이고 저장하지 않는다(ADR-013). */
function FoundDetail({ doc, result }: { doc: TeacherDoc; result: DocResult | undefined }) {
  const shown = result?.missing.slice(0, 12) ?? [];
  return (
    <div className={styles.fileDetail}>
      <p>
        이름에 날짜 + {doc.keywords.join(" / ")}
        <br />
        예: {doc.example}
      </p>
      {result && result.missing.length > 0 && (
        <p>
          빈 {doc.rule.kind === "weekdays" ? "평일" : "달"} {result.missing.length}개 —{" "}
          {shown.map(shortDate).join(", ")}
          {result.missing.length > shown.length && ` 외 ${result.missing.length - shown.length}개`}
        </p>
      )}
      {result && result.undated.length > 0 && (
        <p>날짜가 없어 세지 않은 파일 {result.undated.length}개 — 이름에 날짜를 넣어 주세요.</p>
      )}
      {result && result.outside > 0 && <p>검토 기간 밖이라 세지 않은 파일 {result.outside}개</p>}
      {doc.caveat && <p>ⓘ {doc.caveat}</p>}
      {result && result.matched.length > 0 && (
        <ul className={styles.fileList}>
          {result.matched.map((name) => (
            <li key={name}>{name}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** 서류 한 줄 — 쌤플 쪽 숫자, 폴더 검사 결과, 교사 체크를 한데 묶는다. 도장판과 아래 표가 같이 쓴다. */
export type SheetRow = {
  doc: TeacherDoc;
  made: Made | null;
  result: DocResult | undefined;
  /** 선생님이 직접 누른 체크(`doc:<id>`). 쌤플이 만드는 서류에서는 근거로 쓰지 않는다 — `stampSources` */
  checked: boolean;
  /** 도장 근거. 비어 있으면 빈 칸이다 */
  sources: StampSource[];
  done: boolean;
};

export function sheetRows(autos: AutoIndicator[], scan: Scan | null, checks: string[]): SheetRow[] {
  return TEACHER_DOCS.map((doc) => {
    const made = madeInSsample(doc.id, autos);
    const result = scan?.results.find((r) => r.id === doc.id);
    const checked = checks.includes(`doc:${doc.id}`);
    const sources = stampSources(made, result, checked);
    return { doc, made, result, checked, sources, done: sources.length > 0 };
  });
}

/** 도장 안 근거 글자. 사용자 결정(2026-11-08) — 「챙겼어요」 대신 왜 찍혔는지를 쓴다. */
const SOURCE_WORD: Record<StampSource, string> = {
  ssample: "쌤플확정",
  folder: "내컴퓨터",
  teacher: "직접확인",
};

/**
 * 도장 칸 하나.
 *
 * **쌤플이 만들지 않는 서류는 동그라미가 곧 「직접확인」이다** — 누르면 「직접확인」이 찍히고 다시 누르면 지워진다.
 * 폴더에서 찾은 근거(「내컴퓨터」)는 누른다고 지워지지 않는다. 쌤플이 만드는 서류는 눌러도 바뀌지 않는다.
 * 도장 안에는 근거를 모두 적는다(한 칸에 둘까지 — 쌤플확정 + 내컴퓨터, 내컴퓨터 + 직접확인).
 *
 * `fresh` 는 방금 빈 칸에서 찍힌 칸이다. 그 칸에만 이중 원이 꾹 찍히고 포스티 · 근거 글자가 나타난다. 처음 열 때는 움직이지 않는다.
 */
function StampSlot({
  row,
  fresh,
  onPress,
}: {
  row: SheetRow;
  fresh: boolean;
  onPress: () => void;
}) {
  const { doc, made, done, checked, sources } = row;
  const state = done ? "done" : doc.optional ? "opt" : "empty";
  const pressable = !made;
  const words = sources.map((source) => SOURCE_WORD[source]);
  const value = made
    ? made.text
    : checked
      ? "다시 누르면 지워요"
      : done
        ? "눌러서 직접확인 더하기"
        : doc.optional
          ? "해당 반만 · 세지 않아요"
          : "눌러서 찍어요";
  const valueTone = made ? (made.done ? styles.madeDone : styles.madeShort) : styles.pressHint;

  return (
    <li className={styles.slot}>
      <span className={styles.ring} data-state={state} data-fresh={fresh || undefined}>
        {done ? (
          <span
            className={styles.stampMark}
            data-fresh={fresh || undefined}
            data-lines={words.length}
            aria-hidden="true"
          >
            {/* 찍힐 때는 이 포스티가 근거 글자와 같이 그 자리에서 나타난다. */}
            <span className={styles.stampArt}>
              <span className={styles.imprint}>
                <Posty pose="cheer" face="done" tone="note" size={46} label={null} />
              </span>
            </span>
            <span className={styles.stampWords} data-count={words.length}>
              {words.map((word) => (
                <b key={word}>{word}</b>
              ))}
            </span>
          </span>
        ) : state === "empty" ? (
          <span className={styles.wait} aria-hidden="true">
            <Posty pose="stand" face="empty" tone="shell" size={58} label={null} />
            <b>비었어요</b>
          </span>
        ) : (
          <span className={styles.optWord} aria-hidden="true">
            해당 반만
          </span>
        )}
        {pressable && (
          <button
            type="button"
            className={styles.press}
            aria-pressed={checked}
            aria-label={`${doc.title} 직접확인`}
            onClick={onPress}
          />
        )}
      </span>
      <p className={styles.slotName}>
        {/* 평가항목 번호(4-1 등)는 도장판에서 뺐다(11-08). 아래 표에는 남아 있다. */}
        {doc.title}
        {/* 도장 그림은 화면 읽기에서 뺐다. 근거를 글로 읽어 준다. */}
        <span className="sr-only">
          {" "}
          · {done ? `도장 — ${words.join(", ")}` : doc.optional ? "해당 반만" : "비어 있음"}
        </span>
      </p>
      <p className={`${styles.slotValue} ${valueTone}`}>{value}</p>
    </li>
  );
}

/**
 * 평가 서류 도장판 — 시안 ⑥ · 포스티 도장(평가 점검 디자인 시안, 2026-11-08).
 * 머리에 「몇 칸 비었나」, 아래에 서류마다 도장 칸 하나.
 */
export function StampBoard({
  rows,
  basis,
  onToggle,
  onRecount,
}: {
  rows: SheetRow[];
  /** 「2026학년도 · 11월 7일까지 확정한 문서 기준」 */
  basis: string;
  onToggle: (id: string, on: boolean) => void;
  onRecount: () => void;
}) {
  const [fresh, setFresh] = useState<string | null>(null);
  const counted = rows.filter((row) => !row.doc.optional);
  const left = counted.filter((row) => !row.done).length;

  function press(row: SheetRow) {
    const on = !row.checked;
    const id = row.doc.id;
    // 찍히는 동작은 빈 칸이 찍힐 때만이다. 이미 「내컴퓨터」로 찍힌 칸에 직접확인을 더할 때는 글자만 는다.
    // 다른 칸을 지울 때는 아직 찍히고 있는 칸을 끊지 않는다.
    setFresh((current) => (on && !row.done ? id : current === id ? null : current));
    onToggle(`doc:${id}`, on);
  }

  return (
    <section
      className={styles.stampCard}
      data-done={left ? undefined : true}
      data-tour="eval-today"
      aria-label="평가 서류 도장판"
    >
      <span aria-hidden="true" className={ws.tape} />
      <span aria-hidden="true" className={`${ws.tape} ${styles.tapeRight}`} />
      <div className={styles.stampHead}>
        <div>
          <h2 className={styles.stampTitle}>평가 서류 도장판</h2>
          <p className={styles.stampSub}>
            {basis}
            <button
              type="button"
              className={styles.recount}
              onClick={onRecount}
              aria-label="다시 세기"
              title="다시 세기"
            >
              <Icon name="refresh" />
            </button>
          </p>
        </div>
        <div className={styles.stampSay}>
          <Posty
            pose={left ? "point" : "cheer"}
            face={left ? "oh" : "done"}
            tone={left ? "sun" : "sage"}
            size={62}
            label={null}
          />
          <div>
            <p className={styles.stampLead}>
              {left ? (
                <>
                  아직 <b>{left}칸</b>이 비어 있어요
                </>
              ) : (
                "낼 서류를 다 챙겼어요"
              )}
            </p>
          </div>
        </div>
      </div>
      <ol
        className={styles.slots}
        aria-label={`서류 ${rows.length}칸 · 세는 ${counted.length}칸 중 ${counted.length - left}칸 챙김`}
      >
        {rows.map((row) => (
          <StampSlot
            key={row.doc.id}
            row={row}
            fresh={fresh === row.doc.id && row.done}
            onPress={() => press(row)}
          />
        ))}
      </ol>
    </section>
  );
}

/** 줄 맨 앞 작은 동그라미 — 찍힌 서류는 도장판과 같은 보라 이중 원에 포스티, 빈 서류는 점선. */
function Mini({ state }: { state: "done" | "empty" | "opt" }) {
  return (
    <span className={styles.mini} data-state={state} aria-hidden="true">
      {state === "done" && <Posty pose="cheer" face="done" tone="note" size={21} label={null} />}
    </span>
  );
}

/** 도장 근거 줄. `inline` 이면 한 줄로 — 찍힌 서류 목록에 쓴다. */
function Sources({ row, inline = false }: { row: SheetRow; inline?: boolean }) {
  const all = sourceLines(row.doc, row.made, row.result, row.checked);
  // 찍힌 줄만 「없음」을 뺀다. 열어 둔 뒤 도장이 빠진 줄(폴더를 다시 고름)은 무엇이 없는지 다 보인다.
  const lines = inline && row.done ? all.filter((line) => line.state !== "none") : all;
  return (
    <div className={styles.srcs} data-inline={inline || undefined}>
      {lines.map((line) => (
        <p key={line.source} className={styles.src} data-state={line.state}>
          <b>{SOURCE_WORD[line.source]}</b>
          <span>
            <span className="sr-only">
              {line.state === "on" ? " 찍음" : line.state === "short" ? " 모자람" : " 없음"} ·{" "}
            </span>
            {line.text}
          </span>
        </p>
      ))}
    </div>
  );
}

const IMPORT_LABEL = { dailyLog: "예전 보육일지 올리기", assessment: "예전 평가 올리기" } as const;

/** 찾은 파일 · 이름 규칙 단추 이름 */
function foundLabel(result: DocResult | undefined) {
  return result?.matched.length ? `찾은 파일 ${result.matched.length}건` : "이름 규칙";
}

/**
 * 채울 서류 카드 — 도장판의 빈 칸 하나. 무엇이 모자라는지와 지금 할 일을 크게 둔다(시안 ⑤).
 * 펼친 내용(찾은 파일 · 예전 서류 올리기)은 카드 안에 둔다. 이 화면에 있는 동안 도장이 찍히면 카드는 그 자리에서
 * 도장만 바뀐다 — `EvaluationSheet` 참고.
 */
function TodoCard({ row, onImported }: { row: SheetRow; onImported: () => void }) {
  const { doc, made, result } = row;
  const [open, setOpen] = useState<"found" | "import" | null>(null);
  const id = `eval-doc-${doc.id}`;
  const toggle = (panel: "found" | "import") => setOpen(open === panel ? null : panel);
  const need = [
    made ? made.need : "쌤플이 만들지 않는 서류예요 · 위 도장판 동그라미를 눌러 찍어요",
    result?.status === "partial" ? `컴퓨터 파일은 ${gapText(doc, result)}` : undefined,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <article className={styles.todoCard} aria-label={doc.title}>
      <h3 className={styles.todoTitle}>
        <Mini state={row.done ? "done" : "empty"} />
        <span>
          {doc.title}
          <span className={styles.docIndicator}>{indicatorOf(doc)}</span>
        </span>
      </h3>
      <p className={styles.docBasis}>{basisOf(doc)}</p>
      {!row.done && need && <p className={styles.need}>{need}</p>}
      <Sources row={row} />
      <div className={styles.todoActs}>
        {made?.go && (
          <Link href={made.go.href} className={ws.primary}>
            {made.go.label}
          </Link>
        )}
        {made?.importKind && (
          <button
            type="button"
            className={ws.secondary}
            aria-expanded={open === "import"}
            aria-controls={`${id}-import`}
            onClick={() => toggle("import")}
          >
            {IMPORT_LABEL[made.importKind]}
          </button>
        )}
        <button
          type="button"
          className={styles.linkButton}
          aria-expanded={open === "found"}
          aria-controls={`${id}-found`}
          onClick={() => toggle("found")}
        >
          {foundLabel(result)} ▾
        </button>
      </div>
      <div id={`${id}-found`} className={styles.panel} hidden={open !== "found"}>
        <FoundDetail doc={doc} result={result} />
      </div>
      {made?.importKind && (
        <div id={`${id}-import`} className={styles.panel} hidden={open !== "import"}>
          <EvidenceImport kind={made.importKind} onImported={onImported} />
        </div>
      )}
    </article>
  );
}

/** 찍힌 서류 한 줄 — 있는 근거만 짧게. 「자세히」를 누르면 그 밑에 찾은 파일 · 예전 서류 올리기를 편다. */
function DoneRow({ row, onImported }: { row: SheetRow; onImported: () => void }) {
  const { doc, made, result, done } = row;
  const [open, setOpen] = useState(false);
  const [importing, setImporting] = useState(false);
  const id = `eval-doc-${doc.id}`;
  const opt = doc.optional && !done;
  return (
    <li className={styles.doneRow} data-opt={opt || undefined}>
      <Mini state={done ? "done" : doc.optional ? "opt" : "empty"} />
      <div>
        <p className={styles.doneName}>
          {doc.title}
          <span className={styles.docIndicator}>{indicatorOf(doc)}</span>
        </p>
        <p className={styles.docBasis}>{basisOf(doc)}</p>
      </div>
      {opt ? (
        <p className={styles.optNote}>
          해당하면 따로 챙겨 주세요
          {result && ` · 내 컴퓨터에서 ${result.status === "found" ? "찾음" : "못 찾음"}`}
        </p>
      ) : (
        <Sources row={row} inline />
      )}
      <span className={styles.acts}>
        {made?.go && (
          <Link href={made.go.href} className={styles.linkButton}>
            {made.go.label}
          </Link>
        )}
        <button
          type="button"
          className={styles.linkButton}
          aria-expanded={open}
          aria-controls={`${id}-more`}
          onClick={() => setOpen(!open)}
        >
          자세히 ▾
        </button>
      </span>
      <div id={`${id}-more`} className={styles.donePanel} hidden={!open}>
        <FoundDetail doc={doc} result={result} />
        {made?.importKind && (
          <>
            <button
              type="button"
              className={styles.linkButton}
              aria-expanded={importing}
              aria-controls={`${id}-import`}
              onClick={() => setImporting(!importing)}
            >
              {IMPORT_LABEL[made.importKind]} ▾
            </button>
            <div id={`${id}-import`} hidden={!importing}>
              <EvidenceImport kind={made.importKind} onImported={onImported} />
            </div>
          </>
        )}
      </div>
    </li>
  );
}

/**
 * 도장판 아래 — 시안 ⑤ 「빈 칸 먼저」(2026-11-08).
 * 채울 서류(도장판의 빈 칸)는 카드로 크게, 찍힌 서류와 해당 반만 내는 서류는 한 줄씩.
 * 근거는 도장 안 낱말(쌤플확정 · 내컴퓨터 · 직접확인)로 줄마다 따로 적는다 — 쌤플 숫자와 폴더 결과는 세는 법이 달라
 * 칸 하나에 합쳐 쓰지 않는다(ADR-019 · ADR-045).
 *
 * 어느 쪽에 둘지는 **처음 열 때 한 번만** 정한다. 도장을 찍거나 폴더를 다시 고르거나 예전 서류를 올릴 때마다
 * 카드가 자리를 옮기면 읽던 곳을 잃고, 펼쳐 둔 올리기 폼 · 「등록했어요」 안내가 새로 그려져 사라진다.
 * 그동안 바뀐 것은 그 자리의 도장 · 근거 줄로 보이고, 다시 열면 새로 나눈다.
 */
export default function EvaluationSheet({
  rows,
  onImported,
}: {
  rows: SheetRow[];
  /** 예전 서류를 올리면 숫자를 다시 받는다. */
  onImported: () => void;
}) {
  const [todoIds] = useState(() =>
    rows.filter((row) => !row.done && !row.doc.optional).map((row) => row.doc.id),
  );
  const todo = rows.filter((row) => todoIds.includes(row.doc.id));
  const rest = rows.filter((row) => !todoIds.includes(row.doc.id));
  // 해당 반만 내는 서류는 맨 아래
  const listed = [
    ...rest.filter((row) => !row.doc.optional),
    ...rest.filter((row) => row.doc.optional),
  ];
  // 제목 숫자는 그 묶음 안에서 센다 — 이번에 연 동안 찍힌 카드는 위 묶음에 남아 있으니 거기서 빠진다.
  const left = todo.filter((row) => !row.done).length;
  const stamped = listed.filter((row) => row.done).length;

  return (
    // 높이는 오른쪽 칸에 맞춰 늘어난다 — 찍힌 서류 목록이 남는 높이를 채운다(.doneList).
    <section className={styles.sheet} aria-label="서류마다 자세히" data-tour="eval-sheet">
      {todo.length > 0 && (
        <>
          <h2 className={styles.secTitle}>
            {left ? (
              <>
                채울 서류 <em>{left}가지</em>
                <span>도장판의 빈 칸이에요</span>
              </>
            ) : (
              "채울 서류를 다 찍었어요"
            )}
          </h2>
          <div className={styles.todo}>
            {todo.map((row) => (
              <TodoCard key={row.doc.id} row={row} onImported={onImported} />
            ))}
          </div>
        </>
      )}
      <h2 className={styles.secTitle}>
        도장 찍힌 서류 {stamped}가지
        <span>해당 반만 내는 서류도 여기</span>
      </h2>
      <ul className={styles.doneList}>
        {listed.map((row) => (
          <DoneRow key={row.doc.id} row={row} onImported={onImported} />
        ))}
      </ul>
    </section>
  );
}

/** 폴더를 고른 뒤 — 언제 골랐고, 몇 개를 봐서 몇 가지를 찾았는지(시안 ③). */
function ScanStat({ scan, at }: { scan: Scan; at: Date }) {
  const found = scan.results.filter((r) => r.status === "found").length;
  const partial = scan.results.filter((r) => r.status === "partial").length;
  const time = at.toLocaleTimeString("ko-KR", { hour: "numeric", minute: "2-digit" });
  return (
    <p role="status" className={styles.scanStat}>
      <b>
        {at.getMonth() + 1}월 {at.getDate()}일 {time}에 고른 폴더
      </b>
      <span>
        파일 이름 {scan.total}개 · 찾음 {found}가지
        {partial > 0 && ` · 일부 빠짐 ${partial}가지`}
      </span>
    </p>
  );
}

/** 내 컴퓨터 폴더 — 고르면 파일 이름만 읽어 서류가 있는지 찾는다. 노란 쪽지(시안 ③). */
export function FolderCard({ scan, onScan }: { scan: Scan | null; onScan: (scan: Scan) => void }) {
  const input = useRef<HTMLInputElement | null>(null);
  const [at, setAt] = useState<Date | null>(null);

  function pick(e: ChangeEvent<HTMLInputElement>) {
    const names = Array.from(e.target.files ?? [], (file) => file.name);
    onScan(scanNames(names, today()));
    setAt(new Date());
    // 같은 폴더를 다시 골라도 change 가 일어나게 비운다. File 객체는 들고 있지 않는다.
    e.target.value = "";
  }

  return (
    <section className={styles.folderNote} aria-label="내 컴퓨터 폴더" data-tour="eval-folder">
      <span aria-hidden="true" className={`${ws.tape} ${styles.noteTape}`} />
      <h2 className={styles.folderTitle}>내 컴퓨터 폴더</h2>
      {/* 설명은 한 문장만 둔다(11-08). 「업로드할까요?」 창 안내(멘토 11-05)도 뺐다. */}
      <p className={styles.folderLead}>
        폴더를 고르면 파일 <strong>이름만</strong> 읽어요.
      </p>
      <button
        type="button"
        className={scan ? ws.secondary : ws.primary}
        onClick={() => input.current?.click()}
      >
        {scan ? "폴더 다시 고르기" : "폴더 고르기"}
      </button>
      {scan && at && <ScanStat scan={scan} at={at} />}
      {/* webkitdirectory 는 React 타입에 없어 직접 단다. 아이폰 사파리는 폴더 선택을 못 한다. */}
      <input
        type="file"
        multiple
        hidden
        ref={(el) => {
          input.current = el;
          el?.setAttribute("webkitdirectory", "");
        }}
        onChange={pick}
      />
    </section>
  );
}

/** 원장님이 챙기는 서류. 선생님 폴더에는 보통 없어 찾지 않고 체크만 받는다. 처음부터 펴 둔다(시안 ⑤). */
export function DirectorFold({
  checks,
  onToggle,
}: {
  checks: string[];
  onToggle: (id: string, on: boolean) => void;
}) {
  const done = DIRECTOR_ITEMS.filter((item) => checks.includes(`director:${item.id}`)).length;
  return (
    <details className={styles.fold} aria-label="원장님이 챙기는 서류" open>
      <summary>
        <FoldMark />
        원장님이 챙기는 서류 · {done} / {DIRECTOR_ITEMS.length}
      </summary>
      <div className={styles.directorBody}>
        <p className={ws.hint}>선생님 폴더에는 보통 없어 찾지 않아요. 챙겼으면 체크해 주세요.</p>
        {DIRECTOR_ITEMS.map((item) => {
          const id = `director:${item.id}`;
          return (
            <label key={item.id} className={styles.directorItem}>
              <input
                type="checkbox"
                checked={checks.includes(id)}
                onChange={(e) => onToggle(id, e.target.checked)}
              />
              <span>
                {item.title}
                <small>{item.basis}</small>
              </span>
            </label>
          );
        })}
      </div>
    </details>
  );
}
