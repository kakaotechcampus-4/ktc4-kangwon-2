"use client";
import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api/client";
import { deleteForm, FORM_EXTENSIONS, getForms, registerForm } from "@/lib/api/forms";
import { syncCenter } from "@/lib/api/onboarding";
import type { ApiForm, FormCell } from "@/lib/api/types";
import { loadClassSettings } from "@/lib/onboarding/settings";
import { WorkspacePage, Empty, Message, ws } from "./WorkspaceUI";

/** 서버가 준 문구를 쓴다. 서버 설치 문제(503)만 교사가 할 수 있는 일이 없어 문구를 바꾼다. */
function describe(e: unknown, fallback: string): string {
  if (e instanceof ApiError) {
    const code = (e.body as { error?: { code?: string } } | null)?.error?.code;
    // 재시도로 풀리지 않는다 — 다시 시도하라고 하지 않는다 (docs/api-spec.md §8).
    if (code === "DEPENDENCY_UNAVAILABLE")
      return "지금은 양식을 읽을 수 없어요. 운영팀에 문의해주세요.";
    return e.message;
  }
  return e instanceof Error ? e.message : fallback;
}

const isFormFile = (file: File) =>
  FORM_EXTENSIONS.some((ext) => file.name.toLowerCase().endsWith(ext));

/** 표준 키로 읽힌 라벨만. 키가 없는 칸은 데이터 값이거나 아직 모르는 표현이다. */
const recognized = (form: ApiForm) =>
  Object.entries(form.label_map)
    .filter(([, key]) => key !== null)
    .map(([label]) => label);

function TablePreview({ table }: { table: FormCell[][] }) {
  return (
    <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 12, marginBottom: 12 }}>
      <tbody>
        {table.map((row, r) => (
          <tr key={r}>
            {row.map((cell, c) => (
              <td
                key={c}
                rowSpan={cell.rowspan}
                colSpan={cell.colspan}
                style={{ border: "1px solid var(--pg-line)", padding: "4px 6px" }}
              >
                {cell.text}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function TemplatesPage() {
  const [centerId, setCenterId] = useState<number | null>(null);
  const [forms, setForms] = useState<ApiForm[] | null>(null);
  const [busy, setBusy] = useState<"upload" | "delete" | null>(null);
  const [message, setMessage] = useState("");
  const [problem, setProblem] = useState("");

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const settings = loadClassSettings();
        if (!settings) throw new Error("원 정보를 먼저 설정해주세요.");
        const id = await syncCenter(settings);
        const { items } = await getForms(id);
        if (!alive) return;
        setCenterId(id);
        setForms(items);
      } catch (e) {
        if (alive) setProblem(describe(e, "등록한 양식을 불러오지 못했어요."));
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  async function upload(file?: File) {
    if (!file || centerId === null) return;
    setMessage("");
    setProblem("");
    if (!isFormFile(file)) {
      setProblem("HWP · HWPX 파일만 등록할 수 있어요.");
      return;
    }
    setBusy("upload");
    try {
      const form = await registerForm(centerId, file);
      setForms((prev) => [form, ...(prev ?? [])]);
      setMessage(`「${form.name}」 등록을 마쳤어요.`);
    } catch (e) {
      setProblem(describe(e, "양식을 등록하지 못했어요."));
    } finally {
      setBusy(null);
    }
  }

  async function remove(form: ApiForm) {
    // 수정이 없어 지운 양식은 다시 올려야 한다. 실수로 누르지 않게 한 번 묻는다.
    if (!window.confirm(`「${form.name}」 양식을 삭제할까요?`)) return;
    setMessage("");
    setProblem("");
    setBusy("delete");
    try {
      await deleteForm(form.id);
      setForms((prev) => (prev ?? []).filter((f) => f.id !== form.id));
      setMessage(`「${form.name}」 삭제를 마쳤어요.`);
    } catch (e) {
      setProblem(describe(e, "양식을 삭제하지 못했어요."));
    } finally {
      setBusy(null);
    }
  }

  return (
    <WorkspacePage
      title="원 양식 등록"
      description="우리 원이 쓰는 계획안 양식을 등록하면, 표 구조와 항목을 읽어 둡니다."
    >
      <section className={ws.hero}>
        <div>
          <div className={ws.eyebrow}>TEMPLATE · 우리 원 양식</div>
          <h2>
            쓰던 양식을 올리면,
            <br />
            표의 항목을 읽어 둬요.
          </h2>
          <p>한 번 등록한 양식은 우리 원 선생님들이 계속 같이 써요.</p>
        </div>
        <span className={ws.heroIcon}>▤</span>
      </section>
      <Message error>{problem}</Message>
      <Message>{message}</Message>
      <section className={ws.card}>
        <h2>양식 올리기</h2>
        <div className={ws.upload}>
          <span className={ws.count}>↑</span>
          <h3>기관에서 쓰는 계획안 양식을 선택해주세요</h3>
          <p className={ws.muted}>HWP · HWPX</p>
          <input
            aria-label="기관 양식 파일"
            disabled={busy !== null || centerId === null}
            type="file"
            accept={FORM_EXTENSIONS.join(",")}
            onChange={(e) => {
              void upload(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
        </div>
        <p className={ws.hint}>
          표가 들어 있는 양식만 등록돼요. 원본 파일은 저장하지 않고, 읽어 낸 표 구조와 항목만
          남겨요.
        </p>
        {busy === "upload" && (
          <div className={ws.loading}>
            <span>🌱</span>
            <p>양식의 표를 읽고 있어요.</p>
          </div>
        )}
      </section>
      <div className={ws.between} style={{ margin: "28px 0 15px" }}>
        <h2>등록한 양식 {forms?.length}</h2>
      </div>
      {forms === null ? (
        !problem && (
          <div className={ws.loading}>
            <span>🌱</span>
            <p>등록한 양식을 불러오고 있어요.</p>
          </div>
        )
      ) : forms.length === 0 ? (
        <Empty title="아직 등록한 양식이 없어요">위에서 HWP · HWPX 양식을 올려주세요.</Empty>
      ) : (
        <div className={ws.cards}>
          {forms.map((form) => {
            const labels = recognized(form);
            return (
              <article key={form.id} className={ws.card}>
                <span className={ws.badge}>표 {form.tables.length}개</span>
                <h3 style={{ marginTop: 14 }}>{form.name}</h3>
                <p className={ws.muted}>
                  {labels.length ? labels.join(" · ") : "읽어 낸 항목이 없어요."}
                </p>
                <p className={ws.hint}>
                  {new Date(form.created_at).toLocaleDateString("ko-KR")} 등록
                </p>
                <details style={{ marginTop: 14 }}>
                  <summary className={ws.link}>표 구조 확인</summary>
                  <div className={ws.preview}>
                    {form.tables.map((table, i) => (
                      <TablePreview key={i} table={table} />
                    ))}
                  </div>
                </details>
                <div className={ws.actions} style={{ marginTop: 18 }}>
                  <button
                    className={ws.secondary}
                    disabled={busy !== null}
                    onClick={() => remove(form)}
                  >
                    삭제
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </WorkspacePage>
  );
}
