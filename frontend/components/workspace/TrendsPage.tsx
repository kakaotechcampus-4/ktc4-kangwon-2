"use client";
import Link from "next/link";
import { useState } from "react";
import { requestAI } from "@/lib/workspace/ai-client";
import { WorkspacePage, Message, useAIStatus, ws } from "./WorkspaceUI";
type Trend = { title: string; summary: string; idea: string; url: string; publishedAt: string };
const CURATED: Trend[] = [
  {
    title: "그림책에서 시작하는 놀이",
    summary: "서울시교육청은 영유아 그림책 놀이 프로그램 개발 자료를 안내하고 있어요.",
    idea: "그림책 장면에서 아이들이 고른 소재로 역할놀이를 제안하고, 놀이가 확장되는 모습을 관찰해요.",
    url: "https://buseo.sen.go.kr/buseo/bu30/user/bbs/BD_selectBbs.do?q_bbsDocNo=20260211102211534&q_bbsSn=1484",
    publishedAt: "2026-02-11",
  },
  {
    title: "가족과 지역사회를 잇는 놀이",
    summary: "i-누리의 지역사회자원을 활용한 가족 놀이 실천 사례를 참고할 수 있어요.",
    idea: "동네 공원·도서관에서 관심을 보인 장소를 그림 지도로 만들고, 가족과 나눈 경험을 놀이로 이어가요.",
    url: "https://i-nuri.go.kr/parents/index.do",
    publishedAt: "2026-08-26 · 게시 안내",
  },
  {
    title: "2026년 평가 매뉴얼 확인",
    summary:
      "2024 개정 어린이집 평가 매뉴얼의 2026년 적용 자료 안내입니다. 세부 기준은 원문으로 확인해주세요.",
    idea: "계획안에 놀이 관찰, 다음 놀이 지원, 실행 후 돌아보기 항목을 두어 기록을 연결해요.",
    url: "https://www.kicece.or.kr/kce/front/keyword?keyword=%EB%A7%A4%EB%89%B4%EC%96%BC&x=0&y=0",
    publishedAt: "2026년 적용 · 검색 안내",
  },
];
export default function TrendsPage() {
  const available = useAIStatus();
  const [items, setItems] = useState(CURATED);
  const [topic, setTopic] = useState("놀이 중심 보육, 자연 탐구, 그림책");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [live, setLive] = useState(false);
  async function refresh() {
    setBusy(true);
    setMessage("");
    try {
      const result = await requestAI<{ items: Trend[] }>("trends", {
        topic,
        today: new Date().toISOString().slice(0, 10),
      });
      if (!result.items.length)
        throw new Error("확인할 수 있는 자료를 찾지 못했어요. 다른 주제로 검색해주세요.");
      setItems(result.items);
      setLive(true);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "자료를 가져오지 못했어요.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <WorkspacePage
      title="트렌드봇"
      description="보육·교육의 새로운 자료를 우리 반의 놀이 아이디어로 연결해요."
    >
      <section className={ws.hero}>
        <div>
          <div className={ws.eyebrow}>TREND BOT · 다음 놀이의 힌트</div>
          <h2>
            새로운 주제도,
            <br />
            우리 반답게 시작해요.
          </h2>
          <p>출처가 있는 교육 자료와 그 자료에서 착안한 놀이 제안을 함께 살펴보세요.</p>
        </div>
        <span className={ws.heroIcon}>✳</span>
      </section>
      <section className={ws.card}>
        <div className={ws.row}>
          <label className={ws.field}>
            관심 주제
            <input
              maxLength={200}
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="예: 생태놀이, 그림책, 협동놀이"
            />
          </label>
          <button
            className={ws.primary}
            style={{ alignSelf: "end" }}
            disabled={busy || !available || !topic.trim()}
            onClick={refresh}
          >
            {busy ? "공식 자료 찾는 중…" : "최신 자료 검색"}
          </button>
        </div>
        <p className={ws.hint}>
          {available
            ? "검색 버튼을 누르면 웹에서 최신 자료와 원문 출처를 확인해요."
            : "현재는 2026-09-11에 확인한 추천 자료입니다. AI 연결 후 최신 자료 검색을 사용할 수 있어요."}
        </p>
      </section>
      <Message error>{message}</Message>
      <div className={ws.between} style={{ margin: "25px 0 16px" }}>
        <h2>{live ? "검색한 교육 자료" : "살펴볼 만한 공식 자료"}</h2>
        <span className={ws.muted}>{live ? "실시간 검색 결과" : "자료 확인일 2026-09-11"}</span>
      </div>
      <div className={ws.cards}>
        {items.map((item, index) => (
          <article key={`${item.url}-${index}`} className={ws.card}>
            <span className={ws.badge}>자료 {String(index + 1).padStart(2, "0")}</span>
            <h2 style={{ marginTop: 19 }}>{item.title}</h2>
            <p className={ws.muted}>{item.summary}</p>
            <blockquote className={ws.quote}>
              <b>우리 반 놀이 제안</b>
              <br />
              {item.idea}
            </blockquote>
            <a href={item.url} target="_blank" rel="noreferrer" className={ws.source}>
              원문 확인 ↗ · {item.publishedAt}
            </a>
            <Link
              className={ws.primary}
              style={{ marginTop: 19 }}
              href={`/plans/annual/new?topic=${encodeURIComponent(`${item.title}\n${item.idea}\n참고 자료: ${item.url}`)}`}
            >
              계획안에 활용하기 →
            </Link>
          </article>
        ))}
      </div>
    </WorkspacePage>
  );
}
