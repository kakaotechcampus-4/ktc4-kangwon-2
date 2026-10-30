"use client";
import { useEffect, useState } from "react";
import workspace from "@/components/workspace/Workspace.module.css";
import { getPlayMonthlyAudit } from "@/lib/api/playMonthly";
import type { PlayMonthlyAuditEvent } from "@/lib/api/types";
import PlayMonthlyAuditPanel from "./PlayMonthlyAuditPanel";

/**
 * 「변경 이력 보기」 — 누르면 읽고 펼치고, 다시 누르면 접는다(초안 · 확정본 공통).
 * 접거나 주소 id 가 바뀌거나 화면이 내려가면 늦은 응답은 버린다.
 */
export default function PlayMonthlyHistory({ id }: { id: number }) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<{
    events: PlayMonthlyAuditEvent[] | null;
    failed: boolean;
  }>({ events: null, failed: false });
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    getPlayMonthlyAudit(id, controller.signal).then(
      ({ items }) => !controller.signal.aborted && setState({ events: items, failed: false }),
      () => !controller.signal.aborted && setState({ events: null, failed: true }),
    );
    return () => controller.abort();
  }, [id, open]);
  const toggle = () => {
    setState({ events: null, failed: false });
    setOpen(!open);
  };
  return (
    <div>
      <button type="button" className={workspace.secondary} onClick={toggle}>
        {open ? "변경 이력 접기" : "변경 이력 보기"}
      </button>
      {open && state.failed && <p role="alert">변경 이력을 불러오지 못했어요.</p>}
      {open && !state.failed && !state.events && <p role="status">변경 이력을 읽고 있어요.</p>}
      {open && state.events && <PlayMonthlyAuditPanel events={state.events} />}
    </div>
  );
}
