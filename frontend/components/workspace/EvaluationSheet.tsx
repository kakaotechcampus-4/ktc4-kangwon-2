"use client";

import {
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type ChangeEvent,
  type ReactNode,
} from "react";
import Link from "next/link";
import type { AutoIndicator, DirectorCheck, DocumentMark } from "@/lib/api/evaluation";
import {
  DIRECTOR_ITEMS,
  TEACHER_DOCS,
  scanNames,
  sourceLines,
  stampSources,
  summarize,
  type DocResult,
  type FolderSummary,
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

/** 서류 한 줄에서 쌤플이 아는 쪽. 쌤플이 만들지 않는 서류는 `null` 이다. */
interface Made {
  /** 「확정 24건」처럼 한 줄로 읽히는 숫자 */
  text: string;
  done: boolean;
  /** 기준은 못 채웠지만 확정한 문서가 있다 — 근거 줄을 점선(모자람)으로 보인다 */
  some: boolean;
  /**
   * 근거 줄 숫자로는 뜻이 안 읽힐 때만 카드에 적는 말(반 · 아이를 아직 등록하지 않음).
   * 「확정 0건 · 0/2반」을 말로 다시 풀어 쓴 문장은 같은 내용이 두 번 보여 뺐다(11-09).
   */
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
 * 보육일지 · 계획안은 **반마다** 센다 — 4-1 의 두 조건을 서버가 따로 센 반 수(`journal_classes` · `plan_classes`, ADR-074 결정 2).
 * 원의 반이 다 채워야 도장이 찍힌다.
 */
function madeInSsample(docId: string, autos: AutoIndicator[]): Made | null {
  const by = (indicator: string) => autos.find((item) => item.indicator === indicator);
  if (docId === "journal" || docId === "plan") {
    const item = by("4-1");
    if (!item) return null;
    const journal = docId === "journal";
    const count = journal ? item.document_ids.length : item.plan_ids.length;
    const classes = (journal ? item.journal_classes : item.plan_classes) ?? { met: 0, total: 0 };
    const done = classes.total > 0 && classes.met === classes.total;
    return {
      text: `확정 ${count}건 · ${classes.met}/${classes.total}반`,
      done,
      some: count > 0,
      need: classes.total ? undefined : "올해 등록한 반이 없어요",
      go: journal
        ? { href: "/routines", label: "보육일지 쓰기" }
        : { href: "/plans/monthly", label: "월간계획안 만들기" },
      importKind: journal ? "dailyLog" : undefined,
    };
  }
  if (docId === "assessment") {
    const item = by("4-2");
    if (!item) return null;
    const children = item.children ?? { met: 0, total: 0 };
    const done = children.total > 0 && children.met === children.total;
    return {
      // 「채움」까지 써야 숫자만으로 읽힌다 — 4-2 카드도 같은 말을 쓴다.
      text: `${children.total}명 중 ${children.met}명 채움`,
      done,
      some: item.document_ids.length > 0,
      need: children.total ? undefined : "반에 등록한 아이가 없어요",
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

/** 「보육계획안 (월간 · 주간 · 일일)」 → 「보육계획안」 */
function nameOf(doc: TeacherDoc) {
  return doc.title.replace(/\s*\(.*\)\s*$/, "");
}

/** 「보육계획안 (월간 · 주간 · 일일)」 → 「월간 · 주간 · 일일」. 괄호가 없으면 빈 문자열 */
function kindsOf(doc: TeacherDoc) {
  return doc.title.match(/\(([^)]*)\)\s*$/)?.[1] ?? "";
}

/** 평가항목 번호를 뺀 나머지 설명(기간 · 횟수) */
function basisOf(doc: TeacherDoc) {
  return doc.basis.split(" · ").slice(1).join(" · ");
}

/** 이름 규칙과 검사 결과. 찾은 이름은 화면에만 보이고 저장하지 않는다(ADR-013). */
function FoundDetail({
  doc,
  result,
  folder,
}: {
  doc: TeacherDoc;
  result: DocResult | undefined;
  folder: FolderSummary | undefined;
}) {
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
      {/* 이름 · 빈 날짜는 서버에 없다(ADR-074 결정 5). 다시 열면 결과 요약만 남는다. */}
      {!result && folder && (
        <p>
          찾은 파일 이름과 빈 날짜는 폴더를 고른 그때만 보여요. 다시 보려면 폴더를 다시 골라 주세요.
        </p>
      )}
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
  /** 이번에 고른 폴더의 결과(파일 이름 포함). 화면 메모리에만 있다 */
  result: DocResult | undefined;
  /** 폴더 결과 요약 — 이번에 고른 폴더가 있으면 그것, 없으면 서버에 남은 마지막 검사(ADR-074) */
  folder: FolderSummary | undefined;
  /** 선생님이 직접 누른 체크. 쌤플이 만드는 서류에서는 근거로 쓰지 않는다 — `stampSources` */
  checked: boolean;
  /** 도장 근거. 비어 있으면 빈 칸이다 */
  sources: StampSource[];
  done: boolean;
};

export function sheetRows(
  autos: AutoIndicator[],
  scan: Scan | null,
  documents: DocumentMark[],
): SheetRow[] {
  return TEACHER_DOCS.map((doc) => {
    const made = madeInSsample(doc.id, autos);
    const result = scan?.results.find((r) => r.id === doc.id);
    const mark = documents.find((d) => d.doc === doc.id);
    const folder = result ? summarize(result) : (mark?.folder ?? undefined);
    const checked = mark?.checked ?? false;
    const sources = stampSources(made, folder, checked);
    return { doc, made, result, folder, checked, sources, done: sources.length > 0 };
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
      <p className={styles.slotName} title={doc.title}>
        {/* 평가항목 번호(4-1 등)는 도장판에서 뺐다(11-08). 아래 표에는 남아 있다. */}
        {/* 괄호 속 종류는 이름을 두 줄로 밀어 칸 높이가 어긋났다(11-09). 종류는 아래 서류 카드에 나온다. */}
        {nameOf(doc)}
        {kindsOf(doc) && <span className="sr-only"> ({kindsOf(doc)})</span>}
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
    onToggle(id, on);
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
  const all = sourceLines(row.doc, row.made, row.folder, row.checked);
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

/** 찾은 파일 · 이름 규칙 단추 이름. 이름 목록은 이번에 고른 폴더에만 있다. */
function foundLabel(result: DocResult | undefined) {
  return result?.matched.length ? `찾은 파일 ${result.matched.length}건` : "이름 규칙";
}

/**
 * 쪽지를 카드 밑에 놓는다. 쪽지는 맨 위 층(popover)에 올라 있어 가로 칸이 어디인지 모른다 — 단추 자리를 재서 정한다.
 * 폭 · 왼쪽 끝은 그 카드에 맞추고(양옆 8px 넓게), 아래가 모자라면 단추 위에 놓는다. 좌우는 화면 안으로 민다.
 * 박스 좌표는 화면 배율(--app-zoom)이 곱해져 나오고 CSS 값에는 안 곱해진다 — 배율로 나눠 맞춘다.
 */
function placeNote(note: HTMLElement, anchor: HTMLElement) {
  const zoom = Number.parseFloat(getComputedStyle(document.documentElement).zoom) || 1;
  const card = (anchor.closest("article") ?? anchor).getBoundingClientRect();
  const rect = anchor.getBoundingClientRect();
  const edge = 8;
  note.style.width = `${card.width / zoom + 2 * edge}px`;
  const left = Math.min(
    card.left / zoom - edge,
    window.innerWidth / zoom - note.offsetWidth - edge,
  );
  const under = rect.bottom / zoom + 6;
  const top =
    under + note.offsetHeight + edge <= window.innerHeight / zoom
      ? under
      : Math.max(edge, rect.top / zoom - 6 - note.offsetHeight);
  note.style.left = `${Math.max(edge, left)}px`;
  note.style.top = `${top}px`;
}

/**
 * 예전 서류 올리기 판 — 작은 모달. 네이티브 `<dialog>` 라서 포커스를 가두고 Esc 로 닫는다(RegionSheet 와 같다).
 * 닫힌 뒤 포커스는 부모가 눌렀던 단추로 돌린다. 올린 결과는 판 안에 그대로 남아 닫을 때까지 보인다.
 */
function ImportDialog({
  kind,
  onImported,
  onClose,
}: {
  kind: "dailyLog" | "assessment";
  onImported: () => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);

  return (
    <dialog
      ref={ref}
      className={styles.importDialog}
      aria-labelledby={titleId}
      onClose={onClose}
      onClick={(e) => e.target === ref.current && ref.current.close()}
    >
      <div className={styles.importHead}>
        <h2 id={titleId}>{IMPORT_LABEL[kind]}</h2>
        <button
          type="button"
          className={styles.noteClose}
          aria-label="닫기"
          onClick={() => ref.current?.close()}
        >
          ×
        </button>
      </div>
      <div className={styles.importBody}>
        <EvidenceImport kind={kind} onImported={onImported} />
      </div>
    </dialog>
  );
}

/**
 * 서류 한 장 — 가로 칸의 카드 하나. 같은 틀에 세 모양이다.
 * - `todo` 도장판의 빈 칸 — 점선. 무엇이 모자라는지와 지금 할 일(쓰기 · 예전 서류 올리기)을 둔다.
 * - `done` 찍힌 서류 — 실선 · 흰 바탕. 있는 근거만 짧게.
 * - `opt`  해당 반만 내는 서류 — 옅게.
 *
 * 펼치는 것은 카드 키를 바꾸지 않는다(사용자 결정 11-09 — 카드 안에서 펴면 같은 줄 카드가 다 같이 늘어났다).
 * 찾은 파일 · 이름 규칙 · 자세히는 단추 옆에 뜨는 쪽지로, 예전 서류 올리기는 작은 모달로 띄운다.
 * 둘 다 맨 위 층에 올라 가로 칸(`overflow`)에 잘리지 않는다.
 */
function DocCard({
  row,
  kind,
  onImported,
}: {
  row: SheetRow;
  kind: "todo" | "done" | "opt";
  onImported: () => void;
}) {
  const { doc, made, result, folder } = row;
  const [open, setOpen] = useState<"note" | "import" | null>(null);
  const id = `eval-doc-${doc.id}`;
  const note = useRef<HTMLDivElement>(null);
  const noteButton = useRef<HTMLButtonElement>(null);
  const importButton = useRef<HTMLButtonElement>(null);
  const todo = kind === "todo";

  // 쪽지는 열 때 맨 위 층에 올리고 단추 밑에 놓는다. 바깥을 누르거나 Esc · 스크롤 · 창 크기가 바뀌면 닫는다.
  useLayoutEffect(() => {
    const el = note.current;
    const anchor = noteButton.current;
    if (!el || !anchor) return;
    if (open !== "note") {
      if (el.matches(":popover-open")) el.hidePopover();
      return;
    }
    el.showPopover();
    placeNote(el, anchor);
    const away = (e: PointerEvent) => {
      if (!el.contains(e.target as Node) && !anchor.contains(e.target as Node)) setOpen(null);
    };
    const esc = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(null);
      anchor.focus();
    };
    // 가로 칸이 밀리면 단추만 움직이고 쪽지는 제자리에 남는다. 쪽지 안 스크롤은 닫지 않는다.
    const drift = (e: Event) => {
      if (!el.contains(e.target as Node)) setOpen(null);
    };
    const close = () => setOpen(null);
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", esc);
    window.addEventListener("scroll", drift, true);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("pointerdown", away);
      document.removeEventListener("keydown", esc);
      window.removeEventListener("scroll", drift, true);
      window.removeEventListener("resize", close);
    };
  }, [open]);

  // 컴퓨터 파일이 일부 빠진 날짜는 내컴퓨터 근거 줄에 같은 글자로 있어 여기 다시 적지 않는다(11-09).
  const need = made ? made.need : "쌤플이 만들지 않는 서류예요 · 위 도장판 동그라미를 눌러 찍어요";
  const closeNote = () => {
    setOpen(null);
    noteButton.current?.focus();
  };

  return (
    <article className={styles.docCard} data-kind={kind} aria-label={doc.title}>
      {/* 이름은 한 줄로 둔다 — 두 줄이 되면 앞의 동그라미가 옆 카드와 높이가 달라졌다(11-09).
          괄호 안 갈래(「월간 · 주간 · 일일」)는 본문 글씨로 작게 붙인다. 그래도 넘치면 말줄임, 전체 이름은 title 에. */}
      <h3 className={styles.docTitle}>
        <Mini state={row.done ? "done" : doc.optional ? "opt" : "empty"} />
        <span className={styles.todoName} title={doc.title}>
          {nameOf(doc)}
          {kindsOf(doc) && <small className={styles.todoKinds}>{kindsOf(doc)}</small>}
          <span className={styles.docIndicator}>{indicatorOf(doc)}</span>
        </span>
      </h3>
      <div className={styles.docMeta}>
        <p className={styles.docBasis}>{basisOf(doc)}</p>
        <button
          ref={noteButton}
          type="button"
          className={styles.linkButton}
          aria-expanded={open === "note"}
          aria-controls={`${id}-note`}
          onClick={() => setOpen(open === "note" ? null : "note")}
        >
          {todo ? foundLabel(result) : "자세히"} ▾
        </button>
        <div
          id={`${id}-note`}
          ref={note}
          popover="manual"
          role="group"
          aria-label={`${nameOf(doc)} 자세히`}
          className={styles.foundNote}
        >
          <button type="button" className={styles.noteClose} aria-label="닫기" onClick={closeNote}>
            ×
          </button>
          <FoundDetail doc={doc} result={result} folder={folder} />
          {!todo && made?.importKind && (
            <button
              type="button"
              className={ws.secondary}
              aria-haspopup="dialog"
              onClick={() => setOpen("import")}
            >
              {IMPORT_LABEL[made.importKind]}
            </button>
          )}
        </div>
      </div>
      {todo && !row.done && need && <p className={styles.need}>{need}</p>}
      {kind === "opt" ? (
        <p className={styles.optNote}>
          해당하면 따로 챙겨 주세요
          {folder && ` · 내 컴퓨터에서 ${folder.status === "found" ? "찾음" : "못 찾음"}`}
        </p>
      ) : (
        <Sources row={row} inline={!todo} />
      )}
      {made?.go && (
        <div className={styles.docActs}>
          {todo ? (
            <>
              <Link href={made.go.href} className={ws.primary}>
                {made.go.label}
              </Link>
              {made.importKind && (
                <button
                  ref={importButton}
                  type="button"
                  className={ws.secondary}
                  aria-haspopup="dialog"
                  onClick={() => setOpen("import")}
                >
                  {IMPORT_LABEL[made.importKind]}
                </button>
              )}
            </>
          ) : (
            <Link href={made.go.href} className={styles.linkButton}>
              {made.go.label}
            </Link>
          )}
        </div>
      )}
      {open === "import" && made?.importKind && (
        <ImportDialog
          kind={made.importKind}
          onImported={onImported}
          onClose={() => {
            setOpen(null);
            (todo ? importButton : noteButton).current?.focus();
          }}
        />
      )}
    </article>
  );
}

/**
 * 도장판 아래 — 서류 6장이 한 줄로 서는 가로 칸(2026-11-09). 시안 ⑤ 「빈 칸 먼저」를 가로로 옮겼다.
 * 빈 서류 카드 → 찍힌 서류 카드 → 해당 반만 내는 서류 카드 순이고, ‹ › 나 Tab 으로 옆으로 넘긴다.
 * 근거는 도장 안 낱말(쌤플확정 · 내컴퓨터 · 직접확인)로 줄마다 따로 적는다 — 쌤플 숫자와 폴더 결과는 세는 법이 달라
 * 칸 하나에 합쳐 쓰지 않는다(ADR-019 · ADR-045).
 *
 * 어느 쪽에 둘지는 **처음 열 때 한 번만** 정한다. 도장을 찍거나 폴더를 다시 고르거나 예전 서류를 올릴 때마다
 * 카드가 자리를 옮기면 읽던 곳을 잃고, 펼쳐 둔 올리기 폼 · 「등록했어요」 안내가 새로 그려져 사라진다.
 * 그동안 바뀐 것은 그 자리의 도장 · 근거 줄로 보이고, 다시 열면 새로 나눈다.
 * `children` 은 가로 칸 바로 아래 한 줄 — 「내용이 기준을 채웠는지는…」 안내를 받는다.
 */
export default function EvaluationSheet({
  rows,
  onImported,
  children,
}: {
  rows: SheetRow[];
  /** 예전 서류를 올리면 숫자를 다시 받는다. */
  onImported: () => void;
  children?: ReactNode;
}) {
  const [todoIds] = useState(() =>
    rows.filter((row) => !row.done && !row.doc.optional).map((row) => row.doc.id),
  );
  const rest = rows.filter((row) => !todoIds.includes(row.doc.id));
  const cards = [
    ...rows
      .filter((row) => todoIds.includes(row.doc.id))
      .map((row) => ({ row, kind: "todo" as const })),
    // 해당 반만 내는 서류는 맨 끝
    ...rest.filter((row) => !row.doc.optional).map((row) => ({ row, kind: "done" as const })),
    ...rest
      .filter((row) => row.doc.optional)
      .map((row) => ({ row, kind: row.done ? ("done" as const) : ("opt" as const) })),
  ];

  const rail = useRef<HTMLDivElement>(null);
  // 끝에 닿은 쪽 단추를 끄고, 끝에서는 오른쪽 흐림도 걷는다. 소수점 오차를 1px 로 받는다.
  const [edge, setEdge] = useState({ start: true, end: false });
  useEffect(() => {
    const el = rail.current;
    if (!el) return;
    const measure = () =>
      setEdge({
        start: el.scrollLeft < 1,
        end: el.scrollLeft + el.clientWidth >= el.scrollWidth - 1,
      });
    el.addEventListener("scroll", measure, { passive: true });
    // 처음 한 번과 창 폭이 바뀔 때 — 카드가 다 보이는 폭이면 두 단추 모두 꺼진다.
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => {
      el.removeEventListener("scroll", measure);
      observer.disconnect();
    };
  }, []);

  /** 카드 한 장 폭 + 간격 = 첫 두 카드 왼쪽 끝의 차이. 화면 배율(zoom)이 있어도 스크롤 값과 같은 단위다. */
  function slide(direction: 1 | -1) {
    const el = rail.current;
    const [first, second] = Array.from(el?.children ?? []) as HTMLElement[];
    if (!el || !second) return;
    el.scrollBy({
      left: direction * (second.offsetLeft - first.offsetLeft),
      behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
    });
  }

  return (
    <section className={styles.sheet} aria-label="서류마다 자세히" data-tour="eval-sheet">
      <div className={styles.sheetHead}>
        <h2 className={styles.secTitle}>서류 {rows.length}가지</h2>
        <div className={styles.sheetArrows}>
          <button
            type="button"
            aria-label="이전 서류 카드"
            disabled={edge.start}
            onClick={() => slide(-1)}
          >
            ‹
          </button>
          <button
            type="button"
            aria-label="다음 서류 카드"
            disabled={edge.end}
            onClick={() => slide(1)}
          >
            ›
          </button>
        </div>
      </div>
      <div className={styles.rail} ref={rail} data-end={edge.end || undefined}>
        {cards.map(({ row, kind }) => (
          <DocCard key={row.doc.id} row={row} kind={kind} onImported={onImported} />
        ))}
      </div>
      {children}
    </section>
  );
}

/**
 * 폴더를 고른 뒤 — 언제 골랐고, 몇 가지를 찾았는지(시안 ③).
 * 다시 열면 서버에 남은 마지막 검사를 보인다. 파일 수(이름을 센 것)는 그 방문에만 안다.
 */
function ScanStat({ at, total, folders }: { at: Date; total?: number; folders: FolderSummary[] }) {
  const found = folders.filter((f) => f.status === "found").length;
  const partial = folders.filter((f) => f.status === "partial").length;
  const time = at.toLocaleTimeString("ko-KR", { hour: "numeric", minute: "2-digit" });
  return (
    <p role="status" className={styles.scanStat}>
      <b>
        {at.getMonth() + 1}월 {at.getDate()}일 {time}에 고른 폴더
      </b>
      <span>
        {total !== undefined && `파일 이름 ${total}개 · `}찾음 {found}가지
        {partial > 0 && ` · 일부 빠짐 ${partial}가지`}
      </span>
    </p>
  );
}

/** 폴더 고르기 창이 돌려주는 항목 — 쓰는 칸만 적었다. File System Access 타입이 TS 의 dom 라이브러리에 다 들어 있지 않다. */
type FolderEntry = {
  kind: "file" | "directory";
  name: string;
  values?: () => AsyncIterable<FolderEntry>;
};
type FolderWindow = { showDirectoryPicker?: (options: { mode: "read" }) => Promise<FolderEntry> };

/**
 * 크롬 계열(크롬 · 엣지 · 웨일)에만 있는 폴더 고르기(File System Access). 이쪽은 브라우저가 「모든 파일을 업로드하시겠습니까?」 대신
 * 폴더를 봐도 되는지 묻는다 — 실제로 하는 일(이름만 읽기)에 더 가깝다(시안 ③, 11-09). 사파리 · 파이어폭스는 webkitdirectory.
 */
const canViewFolder = () => typeof (window as FolderWindow).showDirectoryPicker === "function";

/** 하위 폴더까지 파일 이름만 모은다 — webkitdirectory 가 주는 범위와 같다. 파일 내용은 열지 않는다. */
async function namesIn(dir: FolderEntry, names: string[] = []): Promise<string[]> {
  for await (const entry of dir.values?.() ?? []) {
    if (entry.kind === "file") names.push(entry.name);
    else await namesIn(entry, names);
  }
  return names;
}

/**
 * 폴더를 처음 고를 때만 뜨는 안내(시안 ②, 11-09). 바로 다음에 뜨는 브라우저 확인 창은 바꿀 수 없어서,
 * 그 창이 무엇을 묻고 무엇을 누르면 되는지 미리 말한다. 크롬이 「취소」를 칠해 둬서 놀라 누르기 쉬웠다.
 */
function FolderGuide({
  view,
  onGo,
  onClose,
}: {
  view: boolean;
  onGo: () => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);

  return (
    <dialog
      ref={ref}
      className={styles.importDialog}
      aria-labelledby={titleId}
      onClose={onClose}
      onClick={(e) => e.target === ref.current && ref.current.close()}
    >
      <div className={`${styles.importHead} ${styles.guideHead}`}>
        <Posty pose="point" size={44} label={null} />
        <h2 id={titleId}>폴더를 고르기 전에</h2>
        <button
          type="button"
          className={styles.noteClose}
          aria-label="닫기"
          onClick={() => ref.current?.close()}
        >
          ×
        </button>
      </div>
      <div className={styles.importBody}>
        <ol className={styles.guideSteps}>
          <li>
            <span>
              다음 창에서 서류를 모아 둔 <strong>폴더</strong>를 골라요.
            </span>
          </li>
          <li>
            {view ? (
              <span>
                브라우저가 쌤플이 이 폴더의 파일을 <strong>봐도 되는지</strong> 물어요. 허락해
                주세요.
              </span>
            ) : (
              <span>
                브라우저가 「모든 파일을 업로드하시겠습니까?」 하고 물으면 <strong>업로드</strong>를
                눌러 주세요.
              </span>
            )}
          </li>
          <li>
            <span>
              쌤플은 파일 <strong>이름만</strong> 읽어요. 파일은 이 컴퓨터 밖으로 나가지 않고, 찾은{" "}
              <strong>개수</strong>만 저장해요.
            </span>
          </li>
        </ol>
        <div className={styles.guideActions}>
          <button type="button" className={ws.secondary} onClick={() => ref.current?.close()}>
            취소
          </button>
          <button
            type="button"
            className={ws.primary}
            onClick={() => {
              // 고르기 창은 누른 그 순간에만 열린다(사용자 동작). 그래서 안내 창을 닫기 전에 먼저 연다.
              onGo();
              ref.current?.close();
            }}
          >
            폴더 고르러 가기
          </button>
        </div>
      </div>
    </dialog>
  );
}

/** 내 컴퓨터 폴더 — 고르면 파일 이름만 읽어 서류가 있는지 찾는다. 노란 쪽지(시안 ③). */
export function FolderCard({
  scan,
  documents,
  onScan,
}: {
  scan: Scan | null;
  documents: DocumentMark[];
  onScan: (scan: Scan) => void;
}) {
  const input = useRef<HTMLInputElement | null>(null);
  const [at, setAt] = useState<Date | null>(null);
  // 서버에 남은 마지막 검사. 한 번 고르면 6종이 같은 시각으로 저장된다.
  const saved = documents.flatMap((d) => (d.folder ? [d.folder] : []));
  const stat =
    scan && at
      ? { at, total: scan.total, folders: scan.results.map(summarize) }
      : saved.length
        ? { at: new Date(saved[0].scanned_at), folders: saved }
        : null;

  const [guide, setGuide] = useState<"view" | "upload" | null>(null);
  const [reading, setReading] = useState(false);
  const [failed, setFailed] = useState(false);

  function found(names: string[]) {
    onScan(scanNames(names, today()));
    setAt(new Date());
  }

  function pick(e: ChangeEvent<HTMLInputElement>) {
    found(Array.from(e.target.files ?? [], (file) => file.name));
    // 같은 폴더를 다시 골라도 change 가 일어나게 비운다. File 객체는 들고 있지 않는다.
    e.target.value = "";
  }

  function open() {
    setFailed(false);
    if (!canViewFolder()) {
      input.current?.click();
      return;
    }
    (window as FolderWindow).showDirectoryPicker!({ mode: "read" })
      .then((dir) => {
        setReading(true);
        return namesIn(dir);
      })
      // 고르기 창을 닫거나 크롬 확인 창에서 「취소」를 누르면 AbortError 다 — 아무 말도 하지 않는다.
      .then(found, (err: unknown) => setFailed((err as Error)?.name !== "AbortError"))
      .finally(() => setReading(false));
  }

  // 처음 고를 때만 안내 창을 거친다. 한 번 고른 뒤(서버에 결과가 있으면)는 바로 연다.
  const start = () => (stat ? open() : setGuide(canViewFolder() ? "view" : "upload"));

  return (
    <section className={styles.folderNote} aria-label="내 컴퓨터 폴더" data-tour="eval-folder">
      <span aria-hidden="true" className={`${ws.tape} ${styles.noteTape}`} />
      <h2 className={styles.folderTitle}>내 컴퓨터 폴더</h2>
      {/* 설명은 한 문장만 둔다(11-08). 「업로드할까요?」 창 안내(멘토 11-05)는 처음 고를 때 뜨는 안내 창으로 옮겼다(11-09). */}
      <p className={styles.folderLead}>
        폴더를 고르면 파일 <strong>이름만</strong> 읽어요.
      </p>
      <button
        type="button"
        className={stat ? ws.secondary : ws.primary}
        disabled={reading}
        onClick={start}
      >
        {reading ? "폴더를 읽는 중…" : stat ? "폴더 다시 고르기" : "폴더 고르기"}
      </button>
      {stat && <ScanStat {...stat} />}
      {failed && (
        <p role="alert" className={styles.folderLead}>
          폴더를 읽지 못했어요. 다른 폴더를 골라 주세요.
        </p>
      )}
      {guide && <FolderGuide view={guide === "view"} onGo={open} onClose={() => setGuide(null)} />}
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

const directorOn = (checks: DirectorCheck[], item: string) =>
  checks.some((c) => c.item === item && c.checked);
export const directorDone = (checks: DirectorCheck[]) =>
  DIRECTOR_ITEMS.filter((item) => directorOn(checks, item.id)).length;

/**
 * 원장님이 챙기는 서류 체크 목록(서랍 안, 시안 ④). 선생님 폴더에는 보통 없어 찾지 않고 체크만 받는다.
 * 체크는 원 단위다 — 같은 원 선생님이 같이 본다(ADR-074 결정 4).
 */
export function DirectorList({
  checks,
  onToggle,
}: {
  checks: DirectorCheck[];
  onToggle: (item: string, on: boolean) => void;
}) {
  // 안내는 바탕에, 체크는 흰 카드에 — 다른 두 서랍(4-1 · 4-2 카드, 영역 카드)과 같은 틀(11-09).
  return (
    <div className={styles.director}>
      <p className={ws.hint}>같은 원 선생님 모두 같은 체크를 봐요.</p>
      <div className={styles.directorCard}>
        {DIRECTOR_ITEMS.map((item) => (
          <label key={item.id} className={styles.directorItem}>
            <input
              type="checkbox"
              checked={directorOn(checks, item.id)}
              onChange={(e) => onToggle(item.id, e.target.checked)}
            />
            <span>
              {item.title}
              <small>{item.basis}</small>
            </span>
          </label>
        ))}
      </div>
    </div>
  );
}
