"use client";

import { useRef, type ChangeEvent } from "react";
import Link from "next/link";
import type { AutoIndicator } from "@/lib/api/evaluation";
import {
  DIRECTOR_ITEMS,
  TEACHER_DOCS,
  scanNames,
  type DocResult,
  type Scan,
  type TeacherDoc,
} from "@/lib/workspace/evaluation-files";
import { today } from "@/lib/workspace/model";
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
      go: { href: "/routines", label: "일과 기록 쓰기" },
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

function MineCell({ result, picked }: { result: DocResult | undefined; picked: boolean }) {
  if (!picked) return <span className={styles.rowFaint}>폴더를 고르면 찾아요</span>;
  if (!result) return <span className={styles.rowFaint}>—</span>;
  return (
    <span className={`${styles.chip} ${STATUS[result.status][1]}`}>
      {STATUS[result.status][0]}
    </span>
  );
}

/**
 * 이름 규칙과 검사 결과. 줄마다 펴 두면 표가 길어져 접어 둔다.
 * 찾은 이름은 화면에만 보이고 저장하지 않는다(ADR-013).
 */
function Found({ doc, result }: { doc: TeacherDoc; result: DocResult | undefined }) {
  const shown = result?.missing.slice(0, 12) ?? [];
  return (
    <details className={styles.fileMore}>
      <summary className={styles.linkButton}>
        {result?.matched.length ? `찾은 파일 ${result.matched.length}건` : "이름 규칙"} ▾
      </summary>
      <div className={styles.fileDetail}>
        <p>
          이름에 날짜 + {doc.keywords.join(" / ")}
          <br />예: {doc.example}
        </p>
        {result && result.missing.length > 0 && (
          <p>
            빈 {doc.rule.kind === "weekdays" ? "평일" : "달"} {result.missing.length}개 —{" "}
            {shown.map(shortDate).join(", ")}
            {result.missing.length > shown.length &&
              ` 외 ${result.missing.length - shown.length}개`}
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
    </details>
  );
}

/**
 * 평가 때 낼 서류 한 장.
 *
 * **평가항목이 아니라 서류를 앞세운다.** 평가 당일 교사가 꺼내는 단위가 서류이기 때문이다.
 * 한 줄에 쌤플에서 만든 것과 선생님 컴퓨터에 있는 것을 나란히 두되, **열 이름으로 분명히 가른다** —
 * 쌤플 쪽은 확정한 문서를 센 것이고, 컴퓨터 쪽은 파일 **이름만** 본 것이라 뜻이 다르다(ADR-019 · ADR-045).
 */
export default function EvaluationSheet({
  autos,
  scan,
  onScan,
  checks,
  onToggle,
  onImported,
}: {
  autos: AutoIndicator[];
  scan: Scan | null;
  onScan: (scan: Scan) => void;
  checks: string[];
  onToggle: (id: string, on: boolean) => void;
  onImported: () => void;
}) {
  const input = useRef<HTMLInputElement | null>(null);

  function pick(e: ChangeEvent<HTMLInputElement>) {
    const names = Array.from(e.target.files ?? [], (file) => file.name);
    onScan(scanNames(names, today()));
    // 같은 폴더를 다시 골라도 change 가 일어나게 비운다. File 객체는 들고 있지 않는다.
    e.target.value = "";
  }

  const rows = TEACHER_DOCS.map((doc) => {
    const made = madeInSsample(doc.id, autos);
    const result = scan?.results.find((r) => r.id === doc.id);
    const checked = checks.includes(`doc:${doc.id}`);
    return { doc, made, result, checked, done: checked || made?.done === true };
  });
  const left = rows.filter((row) => !row.done && !row.doc.optional).length;

  return (
    <div className={ws.stack}>
      <div className={styles.titleRow}>
        <div>
          <h2 className={styles.sectionTitle}>평가 때 낼 서류</h2>
          <p className={ws.hint}>
            쌤플에서 확정한 문서와 선생님 컴퓨터에 있는 파일을 한 장에서 봅니다. 폴더를 고르면 파일
            <strong> 이름만 </strong>
            읽습니다 — 파일을 열지도, 올리지도 않습니다.
          </p>
        </div>
        <button
          type="button"
          className={scan ? ws.secondary : ws.primary}
          onClick={() => input.current?.click()}
        >
          {scan ? "폴더 다시 고르기" : "폴더 고르기"}
        </button>
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
      </div>

      {/* 남은 것을 맨 위 한 줄로. 표를 끝까지 읽지 않아도 오늘 뭘 할지는 알 수 있어야 한다. */}
      <div className={styles.lead}>
        <strong className={styles.leadCount}>{left}</strong>
        <div>
          <p className={styles.leadTitle}>
            {left
              ? `오늘 평가를 받는다면 서류 ${left}가지가 아직 비어 있습니다.`
              : "낼 서류를 다 챙겼습니다."}
          </p>
          <p className={styles.leadNote}>
            쌤플이 셀 수 있는 것만 셉니다. 센 것이 내용까지 확인해 준 것은 아닙니다.
          </p>
        </div>
      </div>

      <section className={styles.sheet} aria-label="평가 때 낼 서류">
        <div className={`${styles.row} ${styles.sheetHead}`}>
          <span className={styles.colDoc}>서류</span>
          <span className={styles.colMade}>쌤플에서 만든 것</span>
          <span className={styles.colMine}>내 컴퓨터에 있는 것</span>
          <span className={styles.colAct} />
        </div>

        {rows.map(({ doc, made, result, checked, done }) => (
          <div key={doc.id} className={styles.row} data-done={done || undefined}>
            <div className={styles.colDoc}>
              <p className={styles.docTitle}>
                {doc.title}
                <span className={styles.docIndicator}>{indicatorOf(doc)}</span>
              </p>
              <p className={styles.docBasis}>{doc.basis.split(" · ").slice(1).join(" · ")}</p>
              <Found doc={doc} result={result} />
            </div>

            <div className={styles.colMade}>
              {made ? (
                <span className={made.done ? styles.madeDone : styles.madeShort}>{made.text}</span>
              ) : (
                <span className={styles.rowFaint}>만들지 않는 서류</span>
              )}
            </div>

            <div className={styles.colMine}>
              <MineCell result={result} picked={!!scan} />
            </div>

            <div className={styles.colAct}>
              {made?.go && (
                <Link href={made.go.href} className={ws.secondary}>
                  {made.go.label}
                </Link>
              )}
              {!made && (
                <label className={styles.rowCheck}>
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={(e) => onToggle(`doc:${doc.id}`, e.target.checked)}
                  />
                  챙겼어요
                </label>
              )}
              {made?.importKind && (
                <details className={styles.fileMore}>
                  <summary className={styles.linkButton}>예전 서류 올리기 ▾</summary>
                  <div className={styles.fileDetail}>
                    <EvidenceImport kind={made.importKind} onImported={onImported} />
                  </div>
                </details>
              )}
            </div>
          </div>
        ))}

        <p className={styles.sheetFoot}>
          「내 컴퓨터에 있는 것」은 파일 <strong>이름만</strong> 본 결과입니다. 새로 고치면
          사라지고, 이름은 어디에도 저장하지 않습니다.
          {scan && ` · 파일 ${scan.total}개를 봤어요 · ${today()} 기준`}
        </p>
      </section>

      <details className={styles.fold} aria-label="원장님이 챙기는 서류">
        <summary>원장님이 챙기는 서류 {DIRECTOR_ITEMS.length}가지</summary>
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
    </div>
  );
}
