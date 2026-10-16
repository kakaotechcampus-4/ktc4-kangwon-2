"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { getTrends, type TrendItem } from "@/lib/api/trends";
import { ApiError } from "@/lib/api/client";
import { WorkspacePage, Message, ws } from "./WorkspaceUI";

/**
 * 트렌드봇 (ADR-016 · FR-806 · FR-808).
 *
 * **여기서 찾지 않는다.** 주 1회 서버가 승인 채널에서 모으고, 사람이 PR 에서 읽고
 * 이상한 줄을 지운 뒤 머지한 것만 내려온다. 교사가 버튼을 누를 때 찾으면 느리고,
 * API 한도가 오전에 끝나고, 위험한 놀이가 검열을 못 거치고 교사에게 간다.
 *
 * 예전에는 이 화면이 `/api/assistant` 로 web_search 를 돌렸다. ADR-016 이 그 경로를
 * 지우기로 했다 — 출처를 확인할 수 없고 같은 질문에 매번 다른 답이 왔다.
 */
export default function TrendsPage() {
  const [data, setData] = useState<{ week: string; items: TrendItem[] } | null>(null);
  const [state, setState] = useState<"loading" | "off" | "error" | "ready">("loading");
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let alive = true;
    (async () => {
      setState("loading");
      try {
        const trends = await getTrends();
        if (!alive) return;
        setData(trends);
        setState("ready");
      } catch (e) {
        if (!alive) return;
        // **꺼둔 것과 못 불러온 것을 섞지 않는다.** 섞으면 교사가 「내가 껐었나」 하고
        // 설정을 뒤진다.
        setState(e instanceof ApiError && e.status === 403 ? "off" : "error");
      }
    })();
    return () => {
      alive = false;
    };
  }, [reload]);

  if (state === "loading")
    return (
      <WorkspacePage title="트렌드봇" description="">
        <p role="status">자료를 불러오고 있어요.</p>
      </WorkspacePage>
    );

  if (state === "off")
    return (
      <WorkspacePage title="트렌드봇" description="지금은 꺼져 있어요.">
        <section className={ws.card}>
          <p>트렌드봇을 쓰지 않도록 해두셨어요. 설정에서 켜면 요즘 놀이 소재를 모아 보여드려요.</p>
          <Link href="/settings" className={ws.secondary}>
            설정으로 가기
          </Link>
        </section>
      </WorkspacePage>
    );

  if (state === "error")
    return (
      <WorkspacePage title="트렌드봇" description="">
        <section className={ws.card}>
          <Message error>자료를 불러오지 못했어요.</Message>
          <button type="button" className={ws.secondary} onClick={() => setReload((n) => n + 1)}>
            다시 시도
          </button>
        </section>
      </WorkspacePage>
    );

  const items = data?.items ?? [];
  return (
    <WorkspacePage
      title="트렌드봇"
      description="승인한 곳에서 주 1회 모은 자료예요. 놀이 아이디어로만 참고해주세요."
    >
      {data?.week && <p className={ws.eyebrow}>{data.week} 에 모았어요</p>}
      {items.length === 0 ? (
        <section className={ws.card}>
          <p>아직 모인 자료가 없어요. 다음 수집은 월요일 새벽에 돌아요.</p>
        </section>
      ) : (
        items.map((item) => (
          <section key={item.url} className={ws.card}>
            <h2>{item.title}</h2>
            <p>{item.summary}</p>
            <p className={ws.eyebrow}>
              {item.origin} · {item.published_at}
            </p>
            <div className={ws.actions}>
              {/* **계획안으로 넘기는 길을 남긴다.** 이 버튼이 이 화면의 쓸모다 —
                  원문만 열어주면 교사가 제목을 손으로 옮겨 적어야 한다.
                  PlanGeneratorPage 가 `topic` 을 메모 칸에 넣는다. */}
              <Link
                href={`/plans/annual/new?topic=${encodeURIComponent(
                  `${item.title}\n${item.summary}\n참고 자료: ${item.url}`,
                )}`}
                className={ws.primary}
              >
                계획안에 활용하기 →
              </Link>
              <a href={item.url} target="_blank" rel="noreferrer" className={ws.secondary}>
                원문 보기
              </a>
            </div>
          </section>
        ))
      )}
    </WorkspacePage>
  );
}
