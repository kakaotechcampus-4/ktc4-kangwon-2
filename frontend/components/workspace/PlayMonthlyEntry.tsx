"use client";

/**
 * 놀이 프로젝트형 연간 반의 월간 「들어가는 문」 (api-spec §9-7).
 * 기존 월간 화면은 놀이 월간을 목록에서 빼서, 이 반에서는 「만들기」가 409 였다.
 * 지금은 생성이 항상 503 이다 — 서버 문구를 그대로 보여 주고, 강조 고르기는 생성이 열릴 때 붙인다.
 */

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ApiError } from "@/lib/api/client";
import { createPlayMonthly, listPlayMonthly } from "@/lib/api/playMonthly";
import type { PlayMonthlySummary } from "@/lib/api/types";
import { Empty, Message, ws } from "./WorkspaceUI";

const HREF = (id: number) => `/plans/monthly/play/${id}`;
/** 서버의 created_at 은 UTC(`Z`) 다. 자르지 않고 Date 로 읽어 현지로 바꾼다. */
const when = (v: string) =>
  new Date(v).toLocaleString("ko-KR", { dateStyle: "medium", timeStyle: "short" });

export function PlayMonthlyEntryView(props: {
  items: PlayMonthlySummary[] | null;
  month: number;
  busy: boolean;
  problem: string;
  onCreate: () => void;
}) {
  const { items, month, busy, problem, onCreate } = props;
  if (items === null && !problem) return <p role="status">놀이 중심 월간계획안을 불러오는 중…</p>;
  const mine = items?.find((p) => p.month === month);
  return (
    <>
      <Message error>{problem}</Message>
      {!mine && (
        <div className={ws.actions} style={{ marginBottom: 16 }}>
          <button type="button" className={ws.primary} disabled={busy} onClick={onCreate}>
            {busy ? "만드는 중…" : `${month}월 놀이 중심 계획안 만들기`}
          </button>
        </div>
      )}
      {mine && (
        <p className={ws.hint}>
          {month}월 계획안이 이미 있어요. <Link href={HREF(mine.id)}>{month}월 계획안 열기</Link>
        </p>
      )}
      {items?.length === 0 && (
        <Empty title="놀이 중심 월간계획안이 아직 없어요">
          연간계획안을 확정한 뒤 달을 골라 만들 수 있어요.
        </Empty>
      )}
      {!!items?.length && (
        <ul className={ws.list}>
          {items.map((p) => (
            <li key={p.id}>
              <Link href={HREF(p.id)} className={ws.link}>
                {p.month}월
              </Link>{" "}
              <span className={ws.badge}>{p.status === "CONFIRMED" ? "확정됨" : "초안"}</span>{" "}
              <span className={ws.muted}>{when(p.created_at)} 만듦</span>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

export default function PlayMonthlyEntry({ classId, month }: { classId: number; month: number }) {
  const router = useRouter();
  const [items, setItems] = useState<PlayMonthlySummary[] | null>(null);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const running = useRef(false);
  // 이 화면이 떠 있는 동안만 true. 늦게 온 응답이 내려간 화면에서 이동 · 상태 변경을 하지 않게 한다.
  const alive = useRef(false);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  useEffect(() => {
    const ctl = new AbortController();
    listPlayMonthly(classId, ctl.signal).then(
      (r) => setItems(r.items),
      (e) => {
        if (!ctl.signal.aborted) setProblem(e instanceof Error ? e.message : "불러오지 못했어요.");
      },
    );
    return () => ctl.abort();
  }, [classId]);

  async function onCreate() {
    if (running.current) return;
    running.current = true;
    setBusy(true);
    setProblem("");
    try {
      const plan = await createPlayMonthly({ class_id: classId, month, emphasized_row_keys: [] });
      if (alive.current) router.push(HREF(plan.id));
    } catch (e) {
      if (!alive.current) return;
      setProblem(e instanceof Error ? e.message : "처리하지 못했어요.");
      // 이미 있음(409) 이면 목록을 다시 읽어 그 달 계획안으로 가는 링크를 띄운다.
      if (e instanceof ApiError && e.status === 409) {
        const again = await listPlayMonthly(classId).catch(() => null);
        if (alive.current && again) setItems(again.items);
      }
    } finally {
      running.current = false;
      if (alive.current) setBusy(false);
    }
  }

  return (
    <PlayMonthlyEntryView
      items={items}
      month={month}
      busy={busy}
      problem={problem}
      onCreate={onCreate}
    />
  );
}
