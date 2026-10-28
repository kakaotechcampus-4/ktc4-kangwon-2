"use client";

import { useRef, type ChangeEvent } from "react";
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
import styles from "./Evaluation.module.css";

const STATUS = {
  found: ["이름으로 찾음", styles.SUPPORTED],
  partial: ["일부 빠짐", styles.INSUFFICIENT],
  missing: ["못 찾음", styles.NONE],
} as const;

const WEEKDAY = ["일", "월", "화", "수", "목", "금", "토"];

/** `2026-10-15` → `10월 15일(목)`, `2026-09` → `9월` */
function shortDate(value: string) {
  const [y, m, d] = value.split("-").map(Number);
  if (!d) return `${m}월`;
  return `${m}월 ${d}일(${WEEKDAY[new Date(y, m - 1, d).getDay()]})`;
}

/** 검사 결과 자세히 — 빈 날 · 날짜 없는 파일 · 센 파일 이름. 이름은 화면에만 보인다. */
function ResultDetail({ doc, result }: { doc: TeacherDoc; result: DocResult }) {
  const shown = result.missing.slice(0, 12);
  // 찾은 파일도 빈 날도 날짜 빠진 파일도 없으면 펼쳐 볼 것이 없다.
  if (!result.matched.length && !result.missing.length && !result.undated.length && !result.outside)
    return null;
  return (
    <details className={styles.fileMore}>
      <summary className={styles.linkButton}>
        {result.matched.length ? `찾은 파일 ${result.matched.length}건 자세히` : "자세히"} ▾
      </summary>
      <div className={styles.fileDetail}>
        {result.missing.length > 0 && (
          <p>
            빈 {doc.rule.kind === "weekdays" ? "평일" : "달"} {result.missing.length}개 —{" "}
            {shown.map(shortDate).join(", ")}
            {result.missing.length > shown.length &&
              ` 외 ${result.missing.length - shown.length}개`}
          </p>
        )}
        {result.undated.length > 0 && (
          <p>날짜가 없어 세지 않은 파일 {result.undated.length}개 — 이름에 날짜를 넣어 주세요.</p>
        )}
        {result.outside > 0 && <p>검토 기간 밖이라 세지 않은 파일 {result.outside}개</p>}
        {doc.caveat && <p>ⓘ {doc.caveat}</p>}
        {result.matched.length > 0 && (
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
 * 서류 점검 탭 — 교사가 고른 폴더의 파일 이름만 본다(ADR-045).
 * 이름으로 찾은 서류는 체크해 두고, 못 찾은 서류는 교사가 직접 체크한다.
 * 찾았다는 것은 이름이 맞았다는 뜻이지 내용이 기준을 채웠다는 뜻이 아니다.
 */
export default function EvaluationFiles({
  scan,
  onScan,
  checks,
  onToggle,
}: {
  scan: Scan | null;
  onScan: (scan: Scan) => void;
  checks: string[];
  onToggle: (id: string, on: boolean) => void;
}) {
  const input = useRef<HTMLInputElement | null>(null);

  function pick(e: ChangeEvent<HTMLInputElement>) {
    const names = Array.from(e.target.files ?? [], (file) => file.name);
    onScan(scanNames(names, today()));
    // 같은 폴더를 다시 골라도 change 가 일어나게 비운다. File 객체는 들고 있지 않는다.
    e.target.value = "";
  }

  return (
    <div className={ws.stack}>
      <div className={styles.titleRow}>
        <div>
          <h2 className={styles.sectionTitle}>서류 점검 · 파일 이름으로 찾아요</h2>
          <p className={ws.hint}>
            서류를 모아 둔 폴더를 고르면 파일 이름만 보고 찾은 서류를 체크해 드려요. 파일은 올리지
            않고, 이름도 저장하지 않아요. 종이로 있거나 다른 이름이면 직접 체크해 주세요.
          </p>
          <ul className={styles.notes}>
            <li>
              이름에 날짜(2026-10-15 또는 2026-10)와 항목마다 적힌 단어 중 하나를 넣어 주세요.
            </li>
          </ul>
        </div>
        <button type="button" className={ws.primary} onClick={() => input.current?.click()}>
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

      <section className={styles.area} aria-label="선생님이 챙기는 서류">
        <div className={styles.areaHead}>
          <h3>선생님이 챙기는 서류</h3>
          <span className={styles.areaCount}>
            {scan && `파일 ${scan.total}개를 봤어요 · ${today()} 기준`}
          </span>
        </div>
        <div className={styles.fileGroup}>
          {TEACHER_DOCS.map((doc) => {
            const result = scan?.results.find((r) => r.id === doc.id);
            const id = `doc:${doc.id}`;
            return (
              // 자세히 보기도 같은 상자 안에 두어 어느 서류의 것인지 헷갈리지 않게 한다.
              <div key={doc.id} className={styles.fileItem}>
                <label className={styles.fileCheck}>
                  <input
                    type="checkbox"
                    checked={checks.includes(id)}
                    onChange={(e) => onToggle(id, e.target.checked)}
                  />
                  <span className={styles.fileText}>
                    {/* 서류 이름과 기준은 한 줄, 파일 이름 규칙은 다음 줄로 떼어 구분한다. */}
                    <span className={styles.fileLine}>
                      <strong>
                        {doc.title}
                        {doc.optional && " · 해당 없으면 체크"}
                      </strong>{" "}
                      <span>{doc.basis}</span>
                    </span>
                    <span>
                      파일 이름 - 날짜 + {doc.keywords.join(" / ")} · 예: {doc.example}
                    </span>
                  </span>
                  {result && (
                    <span className={`${styles.chip} ${STATUS[result.status][1]}`}>
                      {STATUS[result.status][0]}
                    </span>
                  )}
                </label>
                {result && <ResultDetail doc={doc} result={result} />}
              </div>
            );
          })}
        </div>
      </section>

      <section className={styles.area} aria-label="원장님이 챙기는 서류">
        <div className={styles.areaHead}>
          <h3>원장님이 챙기는 서류</h3>
          <span className={styles.areaCount}>선생님 폴더에는 보통 없어 검사하지 않아요</span>
        </div>
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
      </section>
    </div>
  );
}
