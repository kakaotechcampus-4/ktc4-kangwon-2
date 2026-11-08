"use client";

import { Fragment, useRef, useState, type ChangeEvent } from "react";
import Link from "next/link";
import type { AutoIndicator } from "@/lib/api/evaluation";
import {
  DIRECTOR_ITEMS,
  TEACHER_DOCS,
  scanNames,
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

const STATUS: Record<DocResult["status"], [text: string, tone: string]> = {
  found: ["이름으로 찾음", styles.SUPPORTED],
  partial: ["일부 빠짐", styles.INSUFFICIENT],
  missing: ["못 찾음", styles.NONE],
};

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
  /** 「22일 / 24일」처럼 한 줄로 읽히는 숫자 */
  text: string;
  done: boolean;
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
 */
function madeInSsample(docId: string, autos: AutoIndicator[]): Made | null {
  const by = (indicator: string) => autos.find((item) => item.indicator === indicator);
  if (docId === "journal") {
    const item = by("4-1");
    if (!item) return null;
    return {
      text: `확정 ${item.document_ids.length}건`,
      done: item.document_ids.length > 0,
      go: { href: "/routines", label: "보육일지 쓰기" },
      importKind: "dailyLog",
    };
  }
  if (docId === "plan") {
    const item = by("4-1");
    if (!item) return null;
    return {
      text: `확정 ${item.plan_ids.length}건`,
      done: item.plan_ids.length > 0,
      go: { href: "/plans/monthly", label: "월간계획안 만들기" },
    };
  }
  if (docId === "assessment") {
    const item = by("4-2");
    if (!item) return null;
    const children = item.children ?? { met: 0, total: 0 };
    return {
      text: `${children.total}명 중 ${children.met}명`,
      done: children.total > 0 && children.met === children.total,
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

function MineCell({ result, picked }: { result: DocResult | undefined; picked: boolean }) {
  // 폴더를 고르기 전에는 여섯 줄이 전부 같은 말이었다. 안내는 열 이름에 한 번만 둔다.
  if (!picked) return <span className={styles.rowFaint}>—</span>;
  if (!result) return <span className={styles.rowFaint}>—</span>;
  return (
    <span className={`${styles.chip} ${STATUS[result.status][1]}`}>{STATUS[result.status][0]}</span>
  );
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
 * `fresh` 는 방금 빈 칸에서 찍힌 칸이다. 그 칸에만 포스티가 걸어 들어와 도장이 된다. 처음 열 때는 움직이지 않는다.
 */
function StampSlot({
  row,
  fresh,
  onPress,
  onSettled,
}: {
  row: SheetRow;
  fresh: boolean;
  onPress: () => void;
  /** 걸어온 포스티가 사라지면 부른다. 안 부르면 투명해진 포스티가 다음 누름까지 제자리에서 계속 걷는다. */
  onSettled: () => void;
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
            {/* 도장 안 포스티와 걸어오는 포스티가 같은 46px 상자를 쓴다 — 내려앉은 만세 포스티가 도장 안 포스티와 딱 겹친다. */}
            <span className={styles.stampArt}>
              <span className={styles.imprint}>
                <Posty pose="cheer" face="done" tone="note" size={46} label={null} />
              </span>
              {fresh && (
                <span
                  className={styles.walker}
                  // 안쪽 팔다리 · 흐려지기 애니메이션도 여기까지 올라온다. 바깥 걸음이 끝났을 때만 받는다.
                  onAnimationEnd={(e) => e.target === e.currentTarget && onSettled()}
                >
                  <span className={styles.walkerOn}>
                    <Posty pose="stand" walk tone="note" size={46} label={null} />
                  </span>
                  <span className={styles.walkerLand}>
                    <Posty pose="cheer" face="done" tone="note" size={46} label={null} />
                  </span>
                </span>
              )}
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
        {doc.title} <span className={styles.docIndicator}>{indicatorOf(doc)}</span>
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
 * 머리에 「오늘 평가를 받는다면 몇 칸 비었나」, 아래에 서류마다 도장 칸 하나.
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
    // 포스티는 빈 칸이 찍힐 때만 걸어온다. 이미 「내컴퓨터」로 찍힌 칸에 직접확인을 더할 때는 글자만 는다.
    // 다른 칸을 지울 때는 아직 걷고 있는 칸을 끊지 않는다.
    setFresh((current) => (on && !row.done ? id : current === id ? null : current));
    onToggle(`doc:${id}`, on);
  }
  const settle = (id: string) => setFresh((current) => (current === id ? null : current));

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
            <p className={styles.stampEyebrow}>오늘 평가를 받는다면</p>
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
            onSettled={() => settle(row.doc.id)}
          />
        ))}
      </ol>
      <p className={styles.stampFoot}>
        내용이 기준을 채웠는지는 선생님께서 한 번 더 확인해 주세요.
      </p>
    </section>
  );
}

/** 표 한 줄과, 누르면 그 밑에 펼치는 줄(찾은 파일 · 예전 서류 올리기). */
function DocRow({
  row,
  scanned,
  onImported,
}: {
  row: SheetRow;
  scanned: boolean;
  onImported: () => void;
}) {
  const { doc, made, result } = row;
  const [open, setOpen] = useState<"found" | "import" | null>(null);
  const id = `eval-doc-${doc.id}`;
  const toggle = (panel: "found" | "import") => setOpen(open === panel ? null : panel);
  return (
    <Fragment>
      <tr>
        <th scope="row">
          <span className={styles.docTitle}>{doc.title}</span>
          <span className={styles.docIndicator}>{indicatorOf(doc)}</span>
          <span className={styles.docBasis}>
            {basisOf(doc)}
            {doc.optional && " · 세지 않아요"}
          </span>
        </th>
        <td>
          {made ? (
            <span className={made.done ? styles.madeDone : styles.madeShort}>{made.text}</span>
          ) : (
            <span className={styles.rowFaint}>만들지 않는 서류</span>
          )}
        </td>
        <td>
          <MineCell result={result} picked={scanned} />
        </td>
        <td>
          <span className={styles.acts}>
            {made?.go && (
              <Link href={made.go.href} className={styles.linkButton}>
                {made.go.label}
              </Link>
            )}
            <button
              type="button"
              className={styles.linkButton}
              aria-expanded={open === "found"}
              aria-controls={`${id}-found`}
              onClick={() => toggle("found")}
            >
              {result?.matched.length ? `찾은 파일 ${result.matched.length}건` : "이름 규칙"} ▾
            </button>
            {made?.importKind && (
              <button
                type="button"
                className={styles.linkButton}
                aria-expanded={open === "import"}
                aria-controls={`${id}-import`}
                onClick={() => toggle("import")}
              >
                예전 서류 올리기 ▾
              </button>
            )}
          </span>
        </td>
      </tr>
      {/* 펼친 내용은 누른 줄 바로 밑에 표 폭 전체로 둔다. 올리기 폼은 칸이 여럿이라 좁은 칸에 못 넣는다. */}
      <tr id={`${id}-found`} className={styles.panelRow} hidden={open !== "found"}>
        <td colSpan={4}>
          <FoundDetail doc={doc} result={result} />
        </td>
      </tr>
      {made?.importKind && (
        <tr id={`${id}-import`} className={styles.panelRow} hidden={open !== "import"}>
          <td colSpan={4}>
            <EvidenceImport kind={made.importKind} onImported={onImported} />
          </td>
        </tr>
      )}
    </Fragment>
  );
}

/** 비어 있는 서류가 위로. 해당 반만 내는 서류는 세지 않으니 맨 아래. */
function rank(row: SheetRow) {
  if (row.doc.optional) return 2;
  return row.done ? 1 : 0;
}

/**
 * 서류마다 자세히 — 도장판 아래 표.
 * 한 줄에 쌤플에서 확정한 것과 선생님 컴퓨터에 있는 것을 **다른 칸으로** 둔다 —
 * 쌤플 쪽은 확정한 문서를 센 것이고, 컴퓨터 쪽은 파일 **이름만** 본 것이라 뜻이 다르다(ADR-019 · ADR-045).
 */
export default function EvaluationSheet({
  rows,
  scanned,
  onImported,
}: {
  rows: SheetRow[];
  /** 폴더를 골랐나. 고르기 전에는 컴퓨터 칸이 전부 「—」다. */
  scanned: boolean;
  /** 예전 서류를 올리면 숫자를 다시 받는다. */
  onImported: () => void;
}) {
  // 순서는 처음 열 때 한 번만 정한다. 도장을 찍거나 예전 서류를 올릴 때마다 줄이 자리를 옮기면 읽던 곳을 잃는다.
  const [order] = useState(() => [...rows].sort((a, b) => rank(a) - rank(b)).map((r) => r.doc.id));
  const sorted = order.flatMap((id) => rows.filter((row) => row.doc.id === id));
  return (
    <section className={styles.detail} aria-label="서류마다 자세히" data-tour="eval-sheet">
      <h2 className={styles.detailTitle}>서류마다 자세히</h2>
      <div className={styles.tableBox}>
        <table className={styles.docTable}>
          <thead>
            <tr>
              <th scope="col">서류</th>
              <th scope="col">쌤플에서 확정한 것</th>
              <th scope="col">내 컴퓨터 · 이름만</th>
              <th scope="col">
                <span className="sr-only">할 일</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((row) => (
              <DocRow key={row.doc.id} row={row} scanned={scanned} onImported={onImported} />
            ))}
          </tbody>
        </table>
      </div>
      <p className={ws.hint}>
        「내 컴퓨터」는 파일 <strong>이름만</strong> 본 결과예요. 새로 고치면 사라지고, 이름은
        어디에도 저장하지 않아요.
      </p>
    </section>
  );
}

/**
 * 폴더를 고른 뒤 무엇이 일어났는지 — 몇 개를 봤고, 몇 가지를 찾았고, 어디에 표시했는지.
 * 「봤어요, 저장하지 않아요」만으로는 무엇을 한 건지 알 수 없었다(멘토 11-05).
 */
function ScanResult({ scan }: { scan: Scan }) {
  const found = scan.results.filter((r) => r.status === "found").length;
  const partial = scan.results.filter((r) => r.status === "partial").length;
  return (
    <p role="status" className={styles.folderLead}>
      파일 이름 {scan.total}개를 살펴 서류 <strong>{found}가지</strong>를 이름으로 찾았어요
      {partial > 0 && <>(일부 빠진 서류 {partial}가지는 도장 없이 표에만)</>}. 찾은 서류는 도장에
      「내컴퓨터」로, 모든 결과는 아래 표의 「내 컴퓨터」 칸에 표시했어요. 이름은 저장하지 않아서
      새로 고치면 다시 골라야 해요.
    </p>
  );
}

/** 내 컴퓨터 폴더 — 고르면 파일 이름만 읽어 서류가 있는지 찾는다. */
export function FolderCard({ scan, onScan }: { scan: Scan | null; onScan: (scan: Scan) => void }) {
  const input = useRef<HTMLInputElement | null>(null);

  function pick(e: ChangeEvent<HTMLInputElement>) {
    const names = Array.from(e.target.files ?? [], (file) => file.name);
    onScan(scanNames(names, today()));
    // 같은 폴더를 다시 골라도 change 가 일어나게 비운다. File 객체는 들고 있지 않는다.
    e.target.value = "";
  }

  return (
    <section className={`${ws.card} ${styles.folder}`} data-tour="eval-folder">
      <h2 className={styles.folderTitle}>내 컴퓨터 폴더</h2>
      <p className={styles.folderLead}>
        폴더를 고르면 파일 <strong>이름만</strong> 읽어요. 이름으로 찾은 서류는 도장에
        「내컴퓨터」가 찍혀요. 파일을 열거나 서버로 보내지 않고, 새로 고치면 다시 골라야 해요.
      </p>
      {/* 브라우저 확인창은 「업로드」라고 묻는다 — 우리가 바꿀 수 없는 보안 창이라 미리 알린다(멘토 11-05). */}
      <p className={styles.folderLead}>
        「업로드할까요?」가 뜨면 <strong>업로드</strong>를 눌러 주세요. 이름을 읽는 허락일 뿐이에요.
      </p>
      <button
        type="button"
        className={scan ? ws.secondary : ws.primary}
        onClick={() => input.current?.click()}
      >
        {scan ? "폴더 다시 고르기" : "폴더 고르기"}
      </button>
      {scan && <ScanResult scan={scan} />}
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

/** 원장님이 챙기는 서류. 선생님 폴더에는 보통 없어 찾지 않고 체크만 받는다. */
export function DirectorFold({
  checks,
  onToggle,
}: {
  checks: string[];
  onToggle: (id: string, on: boolean) => void;
}) {
  return (
    <details className={styles.fold} aria-label="원장님이 챙기는 서류">
      <summary>
        <FoldMark />
        원장님이 챙기는 서류 {DIRECTOR_ITEMS.length}가지
      </summary>
      <p className={ws.hint}>선생님 폴더에는 보통 없어 찾지 않습니다. 챙겼으면 체크해 주세요.</p>
      <div className={styles.fileGroup}>
        {DIRECTOR_ITEMS.map((item) => {
          const id = `director:${item.id}`;
          return (
            <label key={item.id} className={styles.element}>
              <input
                type="checkbox"
                checked={checks.includes(id)}
                onChange={(e) => onToggle(id, e.target.checked)}
              />
              <span>
                {item.title} · {item.basis}
              </span>
            </label>
          );
        })}
      </div>
    </details>
  );
}
