"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { SavedDocument } from "@/lib/workspace/model";
import { downloadDocumentHwpx, isStaleWrite, verifyLines } from "@/lib/api/documents";
import type { ExportFormat } from "@/lib/api/export";
import { EXPORTS, FileLogo } from "@/components/plan-generator/AnnualFrame";
import { Icon } from "@/components/app/icons";
import { invalidFields } from "@/lib/api/client";
import { useHwpxDownload } from "@/lib/hooks/use-hwpx-download";
import { useUnsavedWarning } from "@/lib/hooks/use-unsaved-warning";
import { Posty } from "@/components/app/Posty";
import { DOMAIN_LOOK } from "@/lib/workspace/domain-look";
import { AXES, type ObservationAxis } from "@/lib/workspace/observation-axis";
import { Message, ws } from "./WorkspaceUI";
import { serverIssues } from "./document-selection";
import { FieldError, fieldErrorProps } from "./WorkspaceViewState";
import type { ServerDocumentActions } from "./DocumentEditor";

const LAYERS = [
  { heading: "해석", hint: "위 쪽지에서 읽을 수 있는 의미만 적어요." },
  { heading: "지원", hint: "다음 놀이에서 교사가 할 일을 구체적으로 적어요." },
] as const;

/** 서버가 짚는 칸 → 고칠 수 있는 공책 이름. 사실은 여기서 못 고친다. */
const SECTION_FIELDS: Record<string, string> = { "sections.해석": "해석", "sections.지원": "지원" };

/** 양식 맨 아래 칸 이름 (backend documents/export.py AXIS_TAIL). 2축 원은 「총평」이다. */
const tailName = (domains: readonly string[]) => (domains.length === 2 ? "총평" : "종합해석");

/**
 * 관찰일지 한 편 — 초안은 **칠판 위 쪽지와 공책**(근거 쪽지를 보며 해석 · 지원을 고친다),
 * 확정본은 **내려받을 양식 그대로의 종이**로 보여 준다.
 *
 * 문서 보관함의 `DocumentEditor` 는 일지 · 계획안을 다 받는 범용이라 관찰일지에 맞춘
 * 모양을 줄 수 없다. 서버 동작(저장 · 확정 · 충돌)은 같은 `server` 한 벌을 쓴다.
 *
 * 고친 것이 있는데 화면을 떠나려 하면 가운데에 묻는다 — 링크 · 단추 · 브라우저 뒤로 가기
 * 모두. 새로고침 · 탭 닫기는 브라우저 기본 창이 대신 묻는다 (`useLeaveGuard`).
 */
export default function ObservationJournalEditor({
  initial,
  server,
  domains,
}: {
  initial: SavedDocument;
  server: ServerDocumentActions;
  domains: readonly string[];
}) {
  const [baseline, setBaseline] = useState(initial);
  const [doc, setDoc] = useState(initial);
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [issues, setIssues] = useState<string[]>([]);
  /** 서버가 짚은 공책 (`해석` · `지원`). */
  const [invalid, setInvalid] = useState<string[]>([]);
  const [staleWrite, setStaleWrite] = useState(false);
  const hwpx = useHwpxDownload(setMessage);
  const [exporting, setExporting] = useState<ExportFormat | null>(null);
  const working = busy || hwpx.exporting || server.pending;

  const body = (heading: string) => doc.sections.find((s) => s.heading === heading)?.body ?? "";
  const dirty =
    doc.status !== "confirmed" &&
    JSON.stringify(doc.sections) !== JSON.stringify(baseline.sections);
  useUnsavedWarning(dirty);

  function edit(heading: string, text: string) {
    setDoc((prev) => ({
      ...prev,
      sections: prev.sections.map((s) => (s.heading === heading ? { ...s, body: text } : s)),
    }));
    setChecked(false);
    setIssues([]);
    setInvalid((prev) => prev.filter((name) => name !== heading));
  }

  function adopt(next: SavedDocument, note: string) {
    setBaseline(next);
    setDoc(next);
    setChecked(false);
    setIssues([]);
    setInvalid([]);
    setStaleWrite(false);
    setMessage(note);
  }

  /** 서버 요청 하나. 실패하면 고친 글을 그대로 둔다. 성공하면 true. */
  async function run(call: () => Promise<SavedDocument | null>, note: string) {
    if (working) return false;
    setBusy(true);
    setMessage("");
    try {
      const next = await call();
      if (next) adopt(next, note);
      return true;
    } catch (e) {
      if (isStaleWrite(e)) {
        setStaleWrite(true);
        return false;
      }
      // 서버가 짚은 칸을 버리지 않는다 — 어느 공책을 고칠지 알아야 한다.
      setInvalid(invalidFields(e, SECTION_FIELDS));
      setMessage(e instanceof Error ? e.message : "요청을 처리하지 못했어요.");
      return false;
    } finally {
      setBusy(false);
    }
  }

  const save = () => run(() => server.save(doc.sections, "교사 검토 전"), "초안을 저장했어요.");
  const refresh = () =>
    run(() => server.refresh(), "바뀐 근거를 받아 왔어요. 해석과 지원을 다시 봐 주세요.");

  /** 반영하면 서버 글로 바뀐다 — 저장 안 한 해석 · 지원이 있으면 먼저 묻는다. */
  const refreshAsk = useRef<HTMLDialogElement>(null);
  function askRefresh() {
    if (!dirty) return void refresh();
    refreshAsk.current?.showModal();
  }
  async function refreshAfter(keep: boolean) {
    refreshAsk.current?.close();
    if (keep && !(await save())) return;
    await refresh();
  }

  /** 3단 AI 검토 — 쪽지(기록)와 어긋나거나 써선 안 되는 표현을 문장마다 짚는다. 저장하지 않는다. */
  async function review() {
    if (working) return;
    const blocking = serverIssues(doc);
    if (blocking.length) {
      setIssues(blocking);
      return;
    }
    setBusy(true);
    setMessage("");
    setIssues([]);
    try {
      const result = await server.verify(doc.sections);
      setIssues(verifyLines(result));
      if (!result.judged)
        setMessage("AI 검토가 꺼져 있어 판정하지 않았어요. 쪽지와 직접 대조해 주세요.");
      else if (!result.issues.length)
        setMessage("AI 검토에서 고칠 곳을 찾지 못했어요. 확정 전에 쪽지와 한 번 더 대조해 주세요.");
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "AI 검토를 하지 못했어요.");
    } finally {
      setBusy(false);
    }
  }

  function confirm() {
    const blocking = serverIssues(doc);
    if (blocking.length || !checked) {
      setIssues(blocking);
      setMessage(blocking.length ? "" : "쪽지와 대조했는지 먼저 체크해 주세요.");
      return;
    }
    if (server.stale) {
      setMessage("근거 기록이 바뀌었어요. 반영한 뒤 확정해 주세요.");
      return;
    }
    void run(() => server.saveAndConfirm(doc.sections, "교사 사실·해석·지원 검토 완료"), "");
  }

  const { dialog: leaveDialog, stay, go, saveThenGo } = useLeaveGuard(dirty);

  return (
    <section className={ws.ojWrap} aria-label="관찰일지">
      {staleWrite && (
        <>
          <Message error>
            다른 곳에서 이 일지가 고쳐졌어요. 최신 내용을 불러온 뒤 다시 고쳐 주세요.
          </Message>
          <button
            type="button"
            className={ws.secondary}
            disabled={working}
            onClick={() => run(() => server.reload(), "최신 일지를 불러왔어요.")}
          >
            최신 일지 불러오기
          </button>
        </>
      )}

      {doc.status === "confirmed" ? (
        <JournalSheet doc={doc} domains={domains}>
          {server.stale && (
            <Message error>
              근거 기록이 바뀌어 내려받을 수 없어요. 다시 고치기를 눌러 반영해 주세요.
            </Message>
          )}
          {/* 계획안 확정 화면(PlanDone)과 같은 파일 그림 단추 — 이름은 aria-label · title. */}
          <h4 className={ws.ojExportHead}>내보내기</h4>
          <div className={ws.ojExports} role="group" aria-label="내보내기">
            {(Object.keys(EXPORTS) as ExportFormat[]).map((format) => (
              <button
                key={format}
                type="button"
                aria-label={EXPORTS[format].label}
                title={EXPORTS[format].label}
                disabled={working || server.stale}
                onClick={async () => {
                  setExporting(format);
                  await hwpx.download(
                    () => downloadDocumentHwpx(doc.id, format),
                    EXPORTS[format].done,
                  );
                  setExporting(null);
                }}
              >
                <FileLogo format={format} busy={exporting === format} />
              </button>
            ))}
          </div>
          {message && (
            <p role="status" className={ws.ojNote}>
              {message}
            </p>
          )}
          <button
            type="button"
            className={ws.ojRedo}
            disabled={working}
            onClick={() => run(() => server.unconfirm(), "확정을 풀었어요. 다시 고칠 수 있어요.")}
          >
            <Icon name="edit" width={17} height={17} />
            <span>
              <b>다시 고치기</b>
              <small>확정을 풀고 칠판으로 돌아가요</small>
            </span>
          </button>
        </JournalSheet>
      ) : (
        <div className={`chalkboard ${ws.ojBoard}`}>
          <header className={ws.ojHead}>
            <h2>{doc.title}</h2>
            <span>
              {doc.className} · {periodLabel(doc.start, doc.end)}
            </span>
            {doc.origin === "ai" && <em>AI 초안</em>}
            {server.stale && <em data-alert>근거가 바뀜</em>}
          </header>
          {doc.mockDraft && (
            <p className={ws.ojChalk}>
              테스트 모드(mock)로 만든 초안이에요. 실제 AI 결과가 아니니 다시 써 주세요.
            </p>
          )}

          <ul className={ws.ojNotes} aria-label="근거 기록">
            {doc.sources.map((s) => {
              const domain = s.domain ?? "";
              return (
                <li key={s.id} data-tone={DOMAIN_LOOK[domain]?.tone}>
                  <small>
                    {shortDate(s.date)}
                    {domain && ` · ${domain}`}
                  </small>
                  {s.text}
                </li>
              );
            })}
          </ul>
          <p className={ws.ojChalk}>
            쪽지는 교사가 적은 원문이라 여기서 못 고쳐요.{" "}
            <Link href="/records">관찰 기록에서 고치기 →</Link>
          </p>
          {server.stale && (
            <div className={ws.ojStale}>
              <p>근거 기록이 바뀌었어요. 바뀐 쪽지를 받아 온 뒤 해석 · 지원을 다시 봐 주세요.</p>
              <button
                type="button"
                className={ws.secondary}
                disabled={working}
                onClick={askRefresh}
              >
                바뀐 근거 반영하기
              </button>
            </div>
          )}

          <div className={ws.ojPads}>
            {LAYERS.map(({ heading, hint }) => (
              <label key={heading} className={ws.ojPad}>
                <span>{heading}</span>
                <small>{hint}</small>
                <textarea
                  aria-label={`${heading} 내용`}
                  maxLength={15000}
                  disabled={working}
                  value={body(heading)}
                  {...fieldErrorProps(heading, invalid)}
                  onChange={(e) => edit(heading, e.target.value)}
                />
                <FieldError name={heading} invalid={invalid} />
              </label>
            ))}
          </div>

          {issues.length > 0 && <Message error>{issues.join("\n")}</Message>}
          <Message>{message}</Message>
          <footer className={ws.ojFoot}>
            <label className={ws.ojCheck}>
              <input
                type="checkbox"
                checked={checked}
                disabled={working}
                onChange={(e) => setChecked(e.target.checked)}
              />
              쪽지와 대조했어요 — 사실과 맞고, 해석 · 지원이 알맞아요
            </label>
            <button type="button" className={ws.ojSave} disabled={working} onClick={review}>
              AI 검토
            </button>
            <button type="button" className={ws.ojSave} disabled={working || !dirty} onClick={save}>
              {busy ? "저장하는 중…" : dirty ? "초안 저장" : "저장됨"}
            </button>
            <button
              type="button"
              className={ws.ojStamp}
              disabled={working || !checked}
              onClick={confirm}
            >
              <b>확정</b>
              <small>출력 보기</small>
            </button>
          </footer>
          <button
            type="button"
            className={ws.ojRemove}
            disabled={working}
            onClick={async () => {
              if (!window.confirm("이 초안을 지울까요? 되돌릴 수 없어요.")) return;
              try {
                await server.remove();
              } catch (e) {
                setMessage(e instanceof Error ? e.message : "지우지 못했어요.");
              }
            }}
          >
            이 초안 지우기
          </button>
        </div>
      )}

      <dialog
        ref={leaveDialog}
        className={ws.ojLeave}
        aria-labelledby="oj-leave-title"
        onClose={stay}
      >
        <Posty pose="hand" face="oh" tone="note" size={78} label={null} />
        <h3 id="oj-leave-title">잠깐만요!</h3>
        <p>고친 내용이 사라져요.</p>
        <div>
          <button
            type="button"
            className={ws.primary}
            disabled={working}
            onClick={() => saveThenGo(save)}
          >
            저장하고 나가기
          </button>
          <button type="button" className={ws.secondary} autoFocus onClick={stay}>
            계속 쓰기
          </button>
          <button type="button" className={ws.link} onClick={go}>
            저장 안 하고 나가기
          </button>
        </div>
      </dialog>

      <dialog ref={refreshAsk} className={ws.ojLeave} aria-labelledby="oj-refresh-title">
        <Posty pose="hand" face="oh" tone="note" size={78} label={null} />
        <h3 id="oj-refresh-title">잠깐만요!</h3>
        <p>바뀐 근거를 받으면 저장 안 한 해석 · 지원이 사라져요.</p>
        <div>
          <button
            type="button"
            className={ws.primary}
            disabled={working}
            onClick={() => refreshAfter(true)}
          >
            저장하고 반영
          </button>
          <button
            type="button"
            className={ws.secondary}
            disabled={working}
            onClick={() => refreshAfter(false)}
          >
            편집 버리고 반영
          </button>
          <button
            type="button"
            className={ws.link}
            autoFocus
            onClick={() => refreshAsk.current?.close()}
          >
            취소
          </button>
        </div>
      </dialog>
    </section>
  );
}

/**
 * 고친 것이 있을 때 이 화면을 떠나려 하면 붙잡는다 — 어떻게 떠나든 같은 창을 띄운다.
 *
 * - **앱 안 링크 · `data-leave` 단추**: 누르기 전에 잡는다(캡처 단계). Next 앱 라우터에는
 *   이동을 멈추는 훅이 없다. 「나가기」를 고르면 막았던 그 요소를 다시 누른다.
 * - **브라우저 뒤로 가기(마우스 · 키보드 · 스와이프)**: 고치기 시작할 때 history 에 같은
 *   주소 한 칸을 끼워 둔다. 뒤로 가면 그 칸만 빠지므로 화면은 그대로고, 다시 끼운 뒤 묻는다.
 *   「나가기」면 두 칸 뒤로 간다.
 * - **새로고침 · 탭 닫기**: 브라우저가 직접 만든 창만 띄울 수 있다(`useUnsavedWarning`).
 *
 * 끼운 칸은 저장해서 고친 것이 없어지거나 「나가기」로 떠날 때 먼저 뺀다 — 남겨 두면
 * 뒤로 가기를 한 번 더 눌러야 해서 고장으로 읽힌다.
 */
function useLeaveGuard(dirty: boolean) {
  const dialog = useRef<HTMLDialogElement>(null);
  const held = useRef<HTMLElement | null>(null);
  const passing = useRef(false);
  /** history 에 한 칸을 끼워 두었나. */
  const armed = useRef(false);
  /** 창을 뒤로 가기가 띄웠나. */
  const viaBack = useRef(false);
  /** 떠나는 중 — 그사이의 popstate · 칸 빼기를 건너뛴다. */
  const leaving = useRef(false);

  useEffect(() => {
    if (!dirty) return;
    const open = () => {
      if (!dialog.current?.open) dialog.current?.showModal();
    };
    if (!armed.current) {
      window.history.pushState(window.history.state, "", window.location.href);
      armed.current = true;
    }
    const onBack = () => {
      if (leaving.current) return;
      // 끼워 둔 칸을 지나왔다. 다시 끼우고 묻는다.
      window.history.pushState(window.history.state, "", window.location.href);
      held.current = null;
      viaBack.current = true;
      open();
    };
    const catchLeave = (event: MouseEvent) => {
      if (passing.current || event.defaultPrevented || event.button !== 0) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const target = (event.target as Element | null)?.closest<HTMLElement>(
        'a[href]:not([target="_blank"]):not([download]), [data-leave]',
      );
      if (!target || dialog.current?.contains(target)) return;
      if (target instanceof HTMLAnchorElement && target.getAttribute("href")?.startsWith("#"))
        return;
      event.preventDefault();
      event.stopPropagation();
      held.current = target;
      viaBack.current = false;
      open();
    };
    window.addEventListener("popstate", onBack);
    document.addEventListener("click", catchLeave, true);
    return () => {
      window.removeEventListener("popstate", onBack);
      document.removeEventListener("click", catchLeave, true);
    };
  }, [dirty]);

  // 저장해서 고친 것이 없어졌다 — 끼워 둔 칸을 뺀다. 같은 주소라 화면은 그대로다.
  useEffect(() => {
    if (dirty || !armed.current || leaving.current) return;
    armed.current = false;
    window.history.back();
  }, [dirty]);

  function close() {
    if (dialog.current?.open) dialog.current.close();
  }
  function go() {
    const target = held.current;
    const back = viaBack.current;
    held.current = null;
    viaBack.current = false;
    leaving.current = true;
    close();
    if (back) {
      // [앞 화면, 이 화면, 끼운 칸] 에서 앞 화면으로.
      armed.current = false;
      window.history.go(-2);
      return;
    }
    const press = () => {
      passing.current = true;
      target?.click();
      passing.current = false;
      leaving.current = false;
    };
    if (!armed.current) return press();
    // 끼운 칸을 먼저 빼고 나서 누른다 — 새 화면 뒤에 같은 주소가 두 칸 남지 않게.
    armed.current = false;
    window.addEventListener("popstate", () => setTimeout(press, 0), { once: true });
    window.history.back();
  }

  return {
    dialog,
    stay: () => {
      held.current = null;
      viaBack.current = false;
      close();
    },
    go,
    /** 저장하고 나가기. 저장하는 동안 「고친 것 없음」이 칸을 먼저 빼지 않게 막는다. */
    saveThenGo: async (save: () => Promise<boolean>) => {
      leaving.current = true;
      const saved = await save();
      leaving.current = false;
      if (saved) go();
      else {
        held.current = null;
        viaBack.current = false;
        close();
      }
    },
  };
}

/**
 * 확정본 — 내려받는 한글 양식과 같은 칸으로 그린다 (backend documents/export.py `_observation`).
 *
 * 행은 **문서를 만들 때 찍은 축**이다 (ADR-088). 원이 나중에 축을 바꿔도 종이와 같게 그린다.
 * 사본이 없는 옛 문서만 지금 원 설정(`current`)을 쓴다.
 */
function JournalSheet({
  doc,
  domains: current,
  children,
}: {
  doc: SavedDocument;
  domains: readonly string[];
  children: React.ReactNode;
}) {
  const domains = AXES[doc.observationAxis as ObservationAxis] ?? current;
  const sorted = [...doc.sources].sort((a, b) => a.date.localeCompare(b.date));
  const rows = domains.map((domain) => ({
    domain,
    lines: sorted
      .filter((s) => s.domain === domain)
      // 종이와 같은 한 줄: `(9/5) (바깥놀이) 사실`. 상황이 없으면 괄호를 붙이지 않는다.
      .map((s) => `(${shortNumber(s.date)}) ${s.context ? `(${s.context}) ` : ""}${s.text}`),
  }));
  const section = (heading: string) => doc.sections.find((s) => s.heading === heading)?.body ?? "";
  return (
    <div className={ws.ojPreview}>
      <article className={ws.ojSheet} aria-label="출력 미리보기">
        <h2>{doc.title}</h2>
        <table>
          <thead>
            <tr>
              <th scope="col">영역</th>
              <th scope="col">관찰내용</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ domain, lines }) => (
              <tr key={domain}>
                <th scope="row">{domain}</th>
                <td>
                  {lines.map((line) => (
                    <p key={line}>{line}</p>
                  ))}
                </td>
              </tr>
            ))}
            <tr>
              <th scope="row">{tailName(domains)}</th>
              <td>
                <p>▸ 배움) {section("해석")}</p>
                <p>▸ 지원) {section("지원")}</p>
              </td>
            </tr>
          </tbody>
        </table>
      </article>
      <aside className={ws.ojRail}>
        <span className={ws.ojDone}>확정</span>
        <h3>이렇게 출력돼요</h3>
        <p className={ws.ojWho}>
          <b>{doc.childName}</b>
          <span>{periodLabel(doc.start, doc.end)}</span>
        </p>
        {children}
      </aside>
    </div>
  );
}

const WEEK = ["일", "월", "화", "수", "목", "금", "토"];
const at = (date: string) => new Date(`${date}T00:00:00Z`);
/** 「2026-11-03」 → 「11/3(화)」 */
function shortDate(date: string) {
  const d = at(date);
  if (Number.isNaN(d.getTime())) return date;
  return `${d.getUTCMonth() + 1}/${d.getUTCDate()}(${WEEK[d.getUTCDay()]})`;
}
/** 「2026-11-03」 → 「11/3」 — 양식 칸의 머리. 서버와 같은 모양이다. */
function shortNumber(date: string) {
  const d = at(date);
  return Number.isNaN(d.getTime()) ? date : `${d.getUTCMonth() + 1}/${d.getUTCDate()}`;
}
function periodLabel(start: string, end: string) {
  const s = at(start),
    e = at(end);
  if (Number.isNaN(s.getTime()) || Number.isNaN(e.getTime())) return `${start} ~ ${end}`;
  const day = (d: Date) => `${d.getUTCMonth() + 1}월 ${d.getUTCDate()}일`;
  return start === end ? day(s) : `${day(s)} ~ ${day(e)}`;
}
