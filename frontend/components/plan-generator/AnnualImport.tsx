"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError } from "@/lib/api/client";
import { syncClass } from "@/lib/api/onboarding";
import {
  blankThemeMonths,
  emptyImportRows,
  extractAnnualFile,
  importAnnualPlan,
  importMonths,
  rowsFromExtract,
  type ImportFileMeta,
  type ImportRow,
} from "@/lib/api/annualImport";
import { classAnnualContext, saveAnnualContext } from "@/lib/plan-generator/context";
import { loadClassSettings, primaryClassFor } from "@/lib/onboarding/settings";

/** 지금 고른 반의 서버 id. 생성 화면과 같은 길로 얻는다. */
async function serverClass() {
  const settings = loadClassSettings(),
    primary = primaryClassFor(settings);
  if (!settings || !primary) throw new Error("반 정보를 먼저 저장해주세요.");
  return { primary, id: await syncClass(settings, primary) };
}

/**
 * 연간 가져오기 (월별 주제형). 파일에서 뽑았든 직접 쓰든 같은 12개월 표를 거친다.
 * [저장]을 누르기 전에는 아무것도 저장하지 않는다 — 자동 저장 · 자동 확정 없음.
 *
 * @param file  null 이면 파일 없이 직접 입력한다.
 */
export default function AnnualImport({
  file,
  onCancel,
}: {
  file: File | null;
  onCancel: () => void;
}) {
  const router = useRouter();
  // null = 파일에서 뽑는 중. 파일 없이 들어오면 처음부터 빈 표다.
  const [rows, setRows] = useState<ImportRow[] | null>(() => (file ? null : emptyImportRows()));
  const [meta, setMeta] = useState<ImportFileMeta | null>(null);
  const [notices, setNotices] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [blank, setBlank] = useState<number[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!file) return;
    const abort = new AbortController();
    (async () => {
      try {
        const { id } = await serverClass();
        const result = await extractAnnualFile(id, file, abort.signal);
        setMeta(result.file);
        setNotices(result.notices);
        setRows(rowsFromExtract(result.months));
      } catch (e) {
        if (abort.signal.aborted) return;
        setError(e instanceof Error ? e.message : "파일을 읽지 못했어요.");
      }
    })();
    return () => abort.abort();
  }, [file]);

  function typeManually() {
    setMeta(null);
    setNotices([]);
    setError("");
    setRows(emptyImportRows());
  }

  function edit(month: number, change: Partial<ImportRow>) {
    setRows((list) =>
      (list ?? []).map((row) => (row.month === month ? { ...row, ...change } : row)),
    );
    if (change.theme?.trim()) setBlank((months) => months.filter((m) => m !== month));
  }

  async function save() {
    if (!rows || saving) return;
    const empty = blankThemeMonths(rows);
    setBlank(empty);
    if (empty.length) {
      setError(`${empty.join("월, ")}월 생활주제를 적어 주세요.`);
      return;
    }
    setSaving(true);
    setError("");
    try {
      const { primary, id } = await serverClass();
      const plan = await importAnnualPlan({
        class_id: id,
        source: meta ? "FILE" : "MANUAL",
        file: meta,
        months: importMonths(rows),
      });
      try {
        saveAnnualContext(plan.id, classAnnualContext(primary, plan.school_year));
      } catch (e) {
        console.warn("계획안 표시 정보 캐시 저장 실패", e);
      }
      router.push("/plans/annual/" + plan.id);
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 409
          ? "이 반에는 이미 연간계획안이 있어요. 계획안 첫 화면의 「이어서 하기」나 문서 보관함에서 열어 주세요."
          : e instanceof Error
            ? e.message
            : "저장하지 못했어요.",
      );
      setSaving(false);
    }
  }

  if (!rows)
    return (
      <ImportShell title="연간계획안 파일 읽는 중" onCancel={onCancel}>
        {error ? (
          <div role="alert" className="flex flex-col items-start gap-3">
            <p className="m-0 text-base">{error}</p>
            <div className="flex gap-3">
              <button type="button" onClick={onCancel} className={SECONDARY}>
                다른 파일 올리기
              </button>
              <button type="button" onClick={typeManually} className={SECONDARY}>
                파일 없이 직접 입력
              </button>
            </div>
          </div>
        ) : (
          <p role="status" aria-busy="true" className="m-0 text-base text-[#5c5243]">
            {file?.name} 에서 달마다 생활주제와 소주제를 찾고 있어요.
          </p>
        )}
      </ImportShell>
    );

  return (
    <ImportShell title="연간계획안 확인하기" onCancel={onCancel}>
      <p className="m-0 text-sm text-[#5c5243]">
        {meta
          ? `${file?.name ?? "올린 파일"}에서 찾은 내용이에요. 틀린 곳은 바로 고쳐 주세요.`
          : "달마다 생활주제와 소주제를 적어 주세요. 소주제는 한 줄에 하나씩 써요."}
      </p>
      {notices.length > 0 && (
        <ul className="m-0 list-none rounded-md bg-[#f8efdc] px-4 py-3 text-sm text-[#705936]">
          {notices.map((notice) => (
            <li key={notice}>{notice}</li>
          ))}
        </ul>
      )}
      <div className="min-h-0 flex-1 overflow-y-auto border border-line bg-paper rounded-md">
        <table className="w-full border-collapse text-left">
          <thead className="sticky top-0 bg-[#fbf9f5] text-sm text-[#5c5243]">
            <tr>
              <th scope="col" className="w-20 px-4 py-3 font-bold">
                월
              </th>
              <th scope="col" className="w-[34%] px-4 py-3 font-bold">
                생활주제
              </th>
              <th scope="col" className="px-4 py-3 font-bold">
                소주제 (한 줄에 하나)
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <MonthRow
                key={row.month}
                row={row}
                blank={blank.includes(row.month)}
                onEdit={(change) => edit(row.month, change)}
              />
            ))}
          </tbody>
        </table>
      </div>
      {error && (
        <p role="alert" className="m-0 text-sm font-bold text-[#a0453a]">
          {error}
        </p>
      )}
      <div className="flex items-center justify-end gap-3">
        <span className="text-sm text-[#5c5243]">저장하면 작성 중인 연간계획안이 돼요.</span>
        <button
          type="button"
          onClick={() => void save()}
          disabled={saving}
          className="min-h-[52px] rounded-md bg-primary hover:bg-primary-hover px-8 text-base font-bold text-white disabled:bg-[#ddd6ca] disabled:text-ink-soft transition-transform active:translate-x-[2px] active:translate-y-[3px] active:shadow-none"
        >
          {saving ? "저장하는 중…" : "저장"}
        </button>
      </div>
    </ImportShell>
  );
}

const SECONDARY =
  "min-h-[44px] rounded-md border border-[#ddd6ca] bg-white px-4 text-sm font-bold text-[#5e4b96]";

function ImportShell({
  title,
  onCancel,
  children,
}: {
  title: string;
  onCancel: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-[calc(100vh-60px)] w-full flex-col gap-4 px-7 pb-6 pt-6 text-[#2b2826]">
      <div className="flex flex-col gap-1">
        <button
          type="button"
          onClick={onCancel}
          className="flex min-h-[32px] items-center self-start text-sm text-[#5c5243]"
        >
          ← 취소하고 돌아가기
        </button>
        <div className="flex items-center gap-3">
          <h1 className="m-0 font-display text-[34px] font-bold leading-[1.2] text-ink">{title}</h1>
          <span className="rounded-full bg-[#e8f1ea] px-3 py-1 text-[13px] font-bold text-[#3b5441]">
            월별 주제형
          </span>
        </div>
      </div>
      {children}
    </div>
  );
}

function MonthRow({
  row,
  blank,
  onEdit,
}: {
  row: ImportRow;
  blank: boolean;
  onEdit: (change: Partial<ImportRow>) => void;
}) {
  const flagged = blank || (row.missing && !row.theme.trim());
  return (
    <tr className={`border-t border-[#f1ece4] align-top ${flagged ? "bg-[#fdf4f1]" : ""}`}>
      <th scope="row" className="px-4 py-3 text-base font-bold">
        {row.month}월
        {row.missing && (
          <span className="mt-1 block text-xs font-normal text-[#a0453a]">못 찾았어요</span>
        )}
      </th>
      <td className="px-4 py-3">
        <input
          aria-label={`${row.month}월 생활주제`}
          aria-invalid={blank || undefined}
          value={row.theme}
          onChange={(e) => onEdit({ theme: e.target.value })}
          className="min-h-[44px] w-full rounded-md border border-[#ddd6ca] px-3 text-base"
        />
      </td>
      <td className="px-4 py-3">
        <textarea
          aria-label={`${row.month}월 소주제`}
          value={row.subThemes}
          rows={Math.max(2, row.subThemes.split("\n").length)}
          onChange={(e) => onEdit({ subThemes: e.target.value })}
          className="w-full resize-none rounded-md border border-[#ddd6ca] px-3 py-2 text-base leading-relaxed"
        />
      </td>
    </tr>
  );
}
