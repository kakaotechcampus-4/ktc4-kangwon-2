"use client";
import Link from "next/link";
import { useEffect, useState, useSyncExternalStore } from "react";
import { DOCUMENT_KINDS } from "@/lib/workspace/model";
import {
  listDocuments,
  getDocument,
  getRelatedDocuments,
  type ServerDocument,
} from "@/lib/api/documents";
import { createCompareSelection, type CompareResource } from "./compare-selection";
import { WorkspacePage, Empty, Message, ws } from "./WorkspaceUI";

function DocumentPanel({
  title,
  resource,
  selected,
  retry,
}: {
  title: string;
  resource: CompareResource<ServerDocument>;
  selected: boolean;
  retry: () => Promise<unknown>;
}) {
  const document = resource.data;
  return (
    <section className={ws.card}>
      <h2>{title}</h2>
      {resource.status === "loading" && (
        <div className={ws.loading} role="status" aria-busy="true">
          <span aria-hidden="true">🌱</span>
          <p>문서 상세를 불러오는 중이에요.</p>
        </div>
      )}
      {resource.status === "error" && (
        <>
          <Message error>{resource.error}</Message>
          <button className={ws.secondary} onClick={() => void retry()}>
            {title} 다시 불러오기
          </button>
        </>
      )}
      {document ? (
        <>
          <span className={ws.badge}>{DOCUMENT_KINDS[document.kind]}</span>
          <h3 style={{ marginTop: 18 }}>{document.title}</h3>
          <p className={ws.muted}>
            기간: {document.start} ~ {document.end}
            {"\n"}반: {document.className}
            {"\n"}대상: {document.childName || "반 전체"}
            {"\n"}상태: {document.status === "confirmed" ? "확정" : "검토 중"}
            {"\n"}근거 변경: {document.stale ? "있음 · 재검토 필요" : "없음"}
          </p>
          {document.sections.map((section, index) => (
            <section key={index} style={{ marginTop: 22 }}>
              <h3>{section.heading}</h3>
              <p>{section.body}</p>
            </section>
          ))}
        </>
      ) : !selected ? (
        <Empty title="대조할 관련 문서를 선택해주세요." />
      ) : null}
    </section>
  );
}

export default function ComparePage() {
  const [selection] = useState(() =>
    createCompareSelection({
      list: listDocuments,
      get: getDocument,
      related: getRelatedDocuments,
    }),
  );
  const state = useSyncExternalStore(selection.subscribe, selection.get, selection.get);
  useEffect(() => {
    void selection.loadList();
    return () => selection.dispose();
  }, [selection]);

  const documents = state.list.data;
  const related = state.related.data;
  return (
    <WorkspacePage
      title="기록 간 비교"
      description="확정 문서와 기간이 겹치는 관련 문서의 원문을 나란히 살펴봐요."
    >
      <section className={ws.hero}>
        <div>
          <div className={ws.eyebrow}>COMPARE · 관련 문서 대조</div>
          <h2>사실·해석·지원을 나란히 살펴봐요.</h2>
          <p>겹치는 확정 문서를 찾아 보여드려요. 원문을 읽고 교사가 직접 검토해주세요.</p>
        </div>
        <Link href="/documents" className={ws.primary}>
          문서 보관함 →
        </Link>
      </section>
      {state.list.status === "loading" && (
        <div className={ws.loading} role="status" aria-busy="true">
          <span aria-hidden="true">🌱</span>
          <p>확정된 문서를 불러오는 중이에요.</p>
        </div>
      )}
      {state.list.status === "error" && (
        <>
          <Message error>{state.list.error}</Message>
          <button className={ws.secondary} onClick={() => void selection.loadList()}>
            확정 문서 다시 불러오기
          </button>
        </>
      )}
      {state.list.status === "ready" && !documents?.length && (
        <Empty title="비교할 확정 문서가 없어요.">
          <Link href="/documents">문서 보관함에서 문서를 검토하고 확정해주세요. →</Link>
        </Empty>
      )}
      {!!documents?.length && (
        <section className={ws.card}>
          <label className={ws.field}>
            기준 확정 문서
            <select
              value={state.baseId}
              onChange={(event) => void selection.selectBase(event.target.value)}
            >
              <option value="">문서 선택</option>
              {documents.map((document) => (
                <option key={document.id} value={document.id}>
                  {document.title} · {DOCUMENT_KINDS[document.kind]} · {document.className} ·{" "}
                  {document.childName || "반 전체"} · {document.start} ~ {document.end}
                </option>
              ))}
            </select>
          </label>
        </section>
      )}
      {!!documents?.length && !state.baseId && (
        <Empty title="기준 문서를 선택해주세요.">
          관련 확정 문서를 찾아 원문을 나란히 확인할 수 있어요.
        </Empty>
      )}
      {state.baseId && (
        <>
          <section className={ws.card} style={{ marginTop: 22 }}>
            <div className={ws.between}>
              <h2>관련 확정 문서</h2>
              <button
                className={ws.secondary}
                disabled={state.related.status === "loading"}
                onClick={() => void selection.reloadRelated()}
              >
                관련 목록 다시 불러오기
              </button>
            </div>
            {state.related.status === "loading" && (
              <div className={ws.loading} role="status" aria-busy="true">
                <span aria-hidden="true">🌱</span>
                <p>관련 문서를 찾는 중이에요.</p>
              </div>
            )}
            <Message error>{state.related.error}</Message>
            {related && (
              <>
                <h3 style={{ marginTop: 18 }}>필요한 관련 문서</h3>
                <ul className={ws.hint}>
                  {related.expectedKinds.map((kind) => (
                    <li key={kind}>
                      {DOCUMENT_KINDS[kind]} ·{" "}
                      {related.items.some((item) => item.kind === kind) ? "있음 ✓" : "아직 없음"}
                    </li>
                  ))}
                </ul>
                {related.items.length ? (
                  <label className={ws.field} style={{ marginTop: 18 }}>
                    관련 확정 문서
                    <select
                      value={state.relatedId}
                      onChange={(event) => void selection.selectRelated(event.target.value)}
                    >
                      <option value="">문서 선택</option>
                      {related.items.map((document) => (
                        <option key={document.id} value={document.id}>
                          {document.title} · {DOCUMENT_KINDS[document.kind]} ·{" "}
                          {document.childName || "반 전체"} · {document.start} ~ {document.end}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : state.related.status === "ready" ? (
                  <Empty title="아직 관련 문서가 없어요.">
                    같은 반·아동 범위에서 기간이 겹치는 확정 문서가 생기면 확인할 수 있어요.
                  </Empty>
                ) : null}
              </>
            )}
          </section>
          <div className={ws.equalGrid} style={{ marginTop: 22 }}>
            <DocumentPanel
              title="기준 문서"
              resource={state.base}
              selected
              retry={selection.reloadBase}
            />
            <DocumentPanel
              title="관련 문서"
              resource={state.comparison}
              selected={!!state.relatedId}
              retry={selection.reloadComparison}
            />
          </div>
        </>
      )}
    </WorkspacePage>
  );
}
