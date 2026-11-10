"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, type CSSProperties, type MouseEvent } from "react";
import { LegalFooter } from "@/components/legal/LegalPage";
import { startLanding } from "./landing-engine";
import "./landing.css";

/**
 * 로그인 전에 보는 소개 화면(`/welcome`) — 스크롤하면 장면이 바뀌는 인터랙티브판.
 *
 * 순서: 첫 화면(실제 홈 · 일과 캡처) → 약속 넷 → 쪽지 다섯 장(칠판) → 선생님의 하루(6장면) →
 * 계획안 연간 → 월간 → 주간 → 휴대폰 → 비교 → 직접 써 보기 → 마감.
 * 실제 캡처는 멘토용 테스트 계정(가짜 아이 · 가짜 기록, 이름은 흐림)이고, 하루 장면의 말과
 * 주간 계획안 표는 예시다. 연간 · 월간 표는 테스트 계정에서 실제로 만든 계획안 내용이다.
 *
 * 스타일은 landing.css 하나에 있고, 모든 규칙이 `.lp` 안에서만 걸린다.
 * 옛 소개 화면은 `/welcome/classic` 에 그대로 남아 있다.
 */
export default function InteractiveLanding() {
  useEffect(() => startLanding(), []);
  const router = useRouter();

  /**
   * 로그인 · 가입 화면으로 갈 때 뚝 바뀌지 않고 겹쳐 사라지게 한다(View Transitions).
   * 새 화면이 그려져 소개 화면이 빠지면 전환을 끝낸다 — 2초가 지나도 안 빠지면 그냥 끝낸다.
   * 이 기능을 모르는 브라우저 · 「움직임 줄이기」 · 새 탭 열기(⌘ · Ctrl · Shift 클릭)는 원래대로 간다.
   */
  function fadeTo(e: MouseEvent<HTMLAnchorElement>) {
    const href = e.currentTarget.getAttribute("href");
    const plainClick = e.button === 0 && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey;
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!href || !plainClick || reduce || !document.startViewTransition) return;
    e.preventDefault();
    document.startViewTransition(
      () =>
        new Promise<void>((done) => {
          router.push(href);
          const start = performance.now();
          const wait = () =>
            !document.querySelector(".lp") || performance.now() - start > 2000
              ? done()
              : requestAnimationFrame(wait);
          wait();
        }),
    );
  }

  return (
    <div className="lp">
      <div className="progress" id="progress" aria-hidden="true" />
      <header className="nav" id="nav">
        <a className="mark" href="#top" aria-label="쌤플 소개 맨 위로">
          Ssample<i>.</i>
          <small>쌤플</small>
        </a>
        <nav className="nav-links" aria-label="바로 가기">
          <a href="#keys" data-sec="keys">
            쪽지 다섯 장
          </a>
          <a href="#day" data-sec="day">
            하루
          </a>
          <a href="#plan" data-sec="plan">
            계획안
          </a>
          <a href="#try" data-sec="try">
            써 보기
          </a>
        </nav>
        <div className="nav-end">
          <Link className="nav-login" href="/login" onClick={fadeTo}>
            로그인
          </Link>
          <Link className="nav-cta" href="/signup" onClick={fadeTo}>
            시작하기
          </Link>
        </div>
      </header>

      <main id="top">
        <section className="hero" id="hero" aria-labelledby="hero-title">
          <div>
            <h1 id="hero-title">
              <span className="nw">선생님의 기록장,</span>
              <br />
              <span className="brand">
                쌤플<em>.</em>
              </span>
            </h1>
            <p className="lede">
              기록은 한 줄로,
              <br />
              계획안과 일지는 초안부터.
            </p>
            <p className="small">
              관찰부터 일과, 일지, 평가와 계획안까지. 선생님의 문서 업무를 한곳에 모았어요.
            </p>
            <div className="hero-cta">
              <Link className="btn" href="/signup" onClick={fadeTo}>
                우리 반으로 시작하기
              </Link>
              <a className="btn ghost" href="#try">
                직접 써 보기
              </a>
            </div>
          </div>
          <div className="hero-devices" id="heroDevices">
            <p className="hd-note" aria-hidden="true">
              쌤의 계획이
              <br />
              쉬워지는 순간,
              <br />
              <b>쌤플.</b>
            </p>
            <figure className="hd-mac" style={{ margin: "0" }}>
              <div className="hd-bar" aria-hidden="true">
                <i></i>
                <i></i>
                <i></i>
                <span>ssample.duckdns.org</span>
              </div>
              <Image
                src="/landing/v2/hero-pc.webp"
                alt="쌤플 홈 화면. 「지금, 한 줄」 입력 칸과 오늘 적은 기록, 오른쪽 칠판에 이번 주 기록이 없는 아이가 보인다."
                width={2400}
                height={1500}
                sizes="(max-width: 900px) 92vw, 760px"
                priority
              />
            </figure>
            <figure className="hd-phone" style={{ margin: "0" }}>
              <Image
                src="/landing/v2/phone-routines.webp"
                alt="휴대폰에서 연 쌤플 일과 기록 화면. 달력에서 11월 4일을 골랐다."
                width={780}
                height={1688}
                sizes="210px"
                priority
              />
            </figure>
          </div>
          <div className="hero-hint" aria-hidden="true">
            스크롤
          </div>
        </section>

        <section className="promise" aria-label="쌤플의 약속">
          <ul>
            <li>
              <strong>아이 이름은 가명으로</strong>
              <span>AI에 전달할 때는 가명으로 바꾸고, 초안에는 원래 이름을 보여줘요.</span>
            </li>
            <li>
              <strong>확정은 선생님이</strong>
              <span>AI가 만든 건 초안이에요. 선생님이 읽고 수정한 뒤 확정해요.</span>
            </li>
            <li>
              <strong>한글 파일 그대로</strong>
              <span>원에서 쓰던 양식대로 내려받아 제출해요.</span>
            </li>
            <li>
              <strong>컴퓨터 · 휴대폰 어디서나</strong>
              <span>설치 없이 브라우저로. 같은 반 기록이 이어져요.</span>
            </li>
          </ul>
        </section>

        <section
          className="pin"
          id="keys"
          style={{ height: "520vh" }}
          data-pin="keys"
          aria-label="쌤플이 하는 다섯 가지 일"
        >
          <div className="stage board keys-stage">
            <div className="keys-copy">
              <p className="hand" id="kNo">
                쪽지 다섯 장
              </p>
              <h2 className="step-title swap" id="kTitle">
                한 장마다,
                <br />
                하는 일이 하나씩.
              </h2>
              <p className="step-text swap" id="kText">
                스크롤하면 쪽지가 한 장씩 앞으로 나와요.
              </p>
              <div className="dots" id="kDots"></div>
            </div>
            <div className="keys-center">
              <span
                className="chip"
                data-for="obs"
                style={{ left: "2%", top: "18%", "--c": "var(--note)" } as CSSProperties}
              >
                말로 적기
              </span>
              <span
                className="chip"
                data-for="obs"
                style={
                  {
                    left: "0",
                    top: "70%",
                    "--c": "var(--note)",
                    animationDelay: "-2s",
                  } as CSSProperties
                }
              >
                누리과정 5영역
              </span>
              <span
                className="chip"
                data-for="routine"
                style={
                  {
                    right: "2%",
                    top: "8%",
                    "--c": "var(--sage)",
                    animationDelay: "-1s",
                  } as CSSProperties
                }
              >
                시계판
              </span>
              <span
                className="chip"
                data-for="routine"
                style={
                  {
                    right: "0",
                    top: "46%",
                    "--c": "var(--sage)",
                    animationDelay: "-3s",
                  } as CSSProperties
                }
              >
                시간 겹침 알림
              </span>
              <span
                className="chip"
                data-for="journal"
                style={
                  {
                    left: "0",
                    top: "44%",
                    "--c": "var(--plum)",
                    animationDelay: "-4s",
                  } as CSSProperties
                }
              >
                근거 연결
              </span>
              <span
                className="chip"
                data-for="journal"
                style={
                  {
                    right: "10%",
                    top: "86%",
                    "--c": "var(--plum)",
                    animationDelay: "-5s",
                  } as CSSProperties
                }
              >
                이름은 가명으로
              </span>
              <span
                className="chip"
                data-for="plan"
                style={
                  {
                    left: "12%",
                    top: "88%",
                    "--c": "var(--primary-tint-line)",
                    animationDelay: "-1.5s",
                  } as CSSProperties
                }
              >
                HWPX · HWP · PDF
              </span>
              <span
                className="chip"
                data-for="plan"
                style={
                  {
                    right: "0",
                    top: "30%",
                    "--c": "var(--primary-tint-line)",
                    animationDelay: "-2.5s",
                  } as CSSProperties
                }
              >
                안전교육 배치
              </span>
              <span
                className="chip"
                data-for="eval"
                style={
                  {
                    left: "14%",
                    top: "6%",
                    "--c": "var(--clay)",
                    animationDelay: "-3.5s",
                  } as CSSProperties
                }
              >
                지표 4-1 · 4-2
              </span>
              <span
                className="chip"
                data-for="eval"
                style={
                  {
                    right: "0",
                    top: "64%",
                    "--c": "var(--clay)",
                    animationDelay: "-.5s",
                  } as CSSProperties
                }
              >
                부족한 서류 알림
              </span>
              <div className="pad" data-pad id="boardPad"></div>
            </div>
          </div>
        </section>

        <section className="intro" aria-labelledby="intro-title">
          <div>
            <h2 id="intro-title">
              아침 등원부터
              <br />
              하원 뒤 30분까지.
            </h2>
            <p>쌤플과 함께하는 담임 선생님의 하루예요. 장면은 예시예요.</p>
          </div>
        </section>

        <section
          className="pin day"
          id="day"
          style={{ height: "720vh" }}
          data-pin="day"
          aria-label="쌤플과 함께하는 하루"
        >
          <div className="stage day-stage">
            <div>
              <div className="clock" id="clock" aria-hidden="true"></div>
              <p className="scene" id="scene"></p>
              <div className="track" aria-hidden="true">
                <i id="trackDot"></i>
              </div>
              <div className="marks" id="marks"></div>
              <div className="mini" aria-hidden="true">
                <div className="pad" data-pad id="miniPad"></div>
                <p className="mini-cap" id="miniCap"></p>
              </div>
            </div>
            <div>
              <p className="quote">
                <span className="typed" id="typed"></span>
                <span className="caret" aria-hidden="true"></span>
                <span id="rest"></span>
              </p>
              <div className="window">
                <div className="win-bar" aria-hidden="true">
                  <i></i>
                  <i></i>
                  <i></i>
                  <span id="winTitle">관찰 기록</span>
                </div>
                <div className="win-body">
                  <div className="view" data-view="0">
                    <span className="tag note">관찰 기록</span>
                    <div className="field">
                      <label>아이 · 영역 · 언제</label>
                      <div
                        style={{ marginTop: "6px", display: "flex", flexWrap: "wrap", gap: "6px" }}
                      >
                        <span className="tag plum">아이 A</span>
                        <span className="tag sage">자연탐구</span>
                        <span className="tag note">오전 바깥놀이</span>
                      </div>
                    </div>
                    <div className="field">
                      <label>본 대로 적기</label>
                      <div className="lined" id="obsLine"></div>
                    </div>
                    <div className="row-btn">
                      <span className="pill-btn soft">말로 적기</span>
                      <span className="pill-btn">남기기</span>
                    </div>
                  </div>
                  <div className="view" data-view="1">
                    <div className="chalkmini" id="chalk">
                      <div
                        className="slip"
                        style={{ background: "var(--plum)", "--r": "-1.5deg" } as CSSProperties}
                      >
                        <b>
                          등원 · 자유놀이 <small>07:30</small>
                        </b>
                        좋아하는 영역에서 놀이
                      </div>
                      <div
                        className="slip"
                        style={{ background: "var(--clay)", "--r": "1deg" } as CSSProperties}
                      >
                        <b>
                          실내놀이 <small>09:20</small>
                        </b>
                        블록으로 길 만들기
                      </div>
                      <div
                        className="slip"
                        style={{ background: "var(--sage)", "--r": "1.4deg" } as CSSProperties}
                      >
                        <b>
                          오전 간식 <small>10:40</small>
                        </b>
                        스스로 손 씻고 먹기
                      </div>
                      <div
                        className="slip"
                        style={{ background: "var(--note)", "--r": "-1deg" } as CSSProperties}
                      >
                        <b>
                          바깥놀이 <small>11:00</small>
                        </b>
                        낙엽 모아 색깔별로
                      </div>
                    </div>
                  </div>
                  <div className="view doc" data-view="2">
                    <h3 className="doc-h">일일 보육일지 · 11월 4일</h3>
                    <div className="r fact">
                      <b>사실</b>
                      <span>
                        <em>선생님이 적은 그대로</em>바깥놀이에서 도토리를 크기별로 줄 세웠다.
                        친구가 와서 같이 세웠다.
                      </span>
                    </div>
                    <div className="r gen" id="gen1">
                      <b>놀이 모습</b>
                      <span>
                        <em>초안</em>도토리를 크기별로 늘어놓으며 크기를 비교하는 모습을 보였다.
                      </span>
                    </div>
                    <div className="r gen" id="gen2">
                      <b>내일 이어갈 것</b>
                      <span>
                        <em>초안</em>무게나 길이로도 비교해 볼 수 있게 자연물을 더 준비한다.
                      </span>
                    </div>
                  </div>
                  <div className="view doc oj" data-view="3">
                    <h3 className="doc-h">관찰일지 · 아이 A · 11월</h3>
                    <div className="picks" id="ojPicks">
                      <span>11.02 블록으로 다리 만들기</span>
                      <span>11.03 모래에 물길 파기</span>
                      <span>11.04 도토리 크기별로 줄 세우기</span>
                    </div>
                    <div className="r fact">
                      <b>관찰 내용</b>
                      <span>
                        <em>선생님이 적은 기록 3건 그대로</em>블록으로 다리를 만들었다. 모래에
                        물길을 파고 「바다야」라고 말했다. 도토리를 크기별로 줄 세웠다.
                      </span>
                    </div>
                    <div className="r gen" id="oj1">
                      <b>해석</b>
                      <span>
                        <em>초안</em>크기와 모양을 비교하고 물길을 바꿔 보며 주변 사물을 탐색하는
                        모습이 이어졌다.
                      </span>
                    </div>
                    <div className="r gen" id="oj2">
                      <b>배움</b>
                      <span>
                        <em>초안 · 누리과정 자연탐구</em>주변 세계와 자연에 대해 지속적으로 궁금증을
                        가진다.
                      </span>
                    </div>
                  </div>
                  <div className="view doc" data-view="4">
                    <h3 className="doc-h">일일 보육일지 · 11월 4일</h3>
                    <div className="r fact">
                      <b>사실</b>
                      <span>
                        바깥놀이에서 도토리를 크기별로 줄 세웠다. 친구가 와서 같이 세웠다.
                      </span>
                    </div>
                    <div className="r">
                      <b>놀이 모습</b>
                      <span>도토리를 크기별로 늘어놓으며 크기를 비교해 보았다.</span>
                    </div>
                    <div className="stamp" id="stamp">
                      확정
                    </div>
                    <div className="files">
                      <div className="file">
                        <i>HWPX</i>11월 4일 보육일지.hwpx
                      </div>
                    </div>
                    <div className="arch">
                      <span className="arch-h">문서 보관함 · 보육일지</span>
                      <div className="arch-days">
                        <i>11.2 월</i>
                        <i>11.3 화</i>
                        <i className="new">11.4 수</i>
                        <i className="off">11.5 목</i>
                        <i className="off">11.6 금</i>
                      </div>
                    </div>
                  </div>
                  <div className="view" data-view="5">
                    <span className="tag sage">주간 기록 · 11월 2일 – 6일</span>
                    <div className="week" id="week">
                      <div>
                        <span>월</span>
                        <strong>2</strong>
                        <em>기록 전</em>
                      </div>
                      <div>
                        <span>화</span>
                        <strong>3</strong>
                        <em>기록 전</em>
                      </div>
                      <div>
                        <span>수</span>
                        <strong>4</strong>
                        <em>기록 전</em>
                      </div>
                      <div>
                        <span>목</span>
                        <strong>5</strong>
                        <em>기록 전</em>
                      </div>
                      <div>
                        <span>금</span>
                        <strong>6</strong>
                        <em>기록 전</em>
                      </div>
                    </div>
                    <div className="row-btn" style={{ marginTop: "22px" }}>
                      <span className="pill-btn">주간 보육일지 만들기</span>
                    </div>
                  </div>
                </div>
              </div>
              <p className="day-label" id="dayLabel"></p>
            </div>
          </div>
        </section>

        <section
          className="pin plan"
          id="plan"
          style={{ height: "720vh" }}
          data-pin="plan"
          aria-labelledby="plan-title"
        >
          <div className="stage plan-stage">
            <div>
              <p className="hand" id="pNo">
                계획안 · 1 / 3
              </p>
              <h2 id="plan-title" className="swap">
                <span id="pTitle">
                  누르면,
                  <br />
                  <em>1년 계획</em>이<br />
                  채워져요.
                </span>
              </h2>
              <p className="sub swap" id="pSub">
                월별 주제형과 놀이 중심형 중에서 고르면 연간 계획안 초안이 만들어져요.
              </p>
              <div className="prompt" aria-hidden="true">
                <span id="pPrompt">2026학년도 · 햇살반 · 월별 주제형</span>
                <span className="go" id="pGo">
                  연간 계획안 만들기
                </span>
              </div>
              <div className="checks" id="checks"></div>
            </div>
            <div className="sheet">
              <div className="sheet-top">
                <h3 id="sheetTitle">2026학년도 연간 보육계획안</h3>
                <div className="seg" role="group" aria-label="계획안 보기">
                  <button type="button" aria-pressed="true" data-plan="annual">
                    연간
                  </button>
                  <button type="button" aria-pressed="false" data-plan="monthly">
                    월간
                  </button>
                  <button type="button" aria-pressed="false" data-plan="weekly">
                    주간
                  </button>
                  <button type="button" aria-pressed="false" data-plan="real">
                    실제 화면
                  </button>
                </div>
              </div>
              <div id="annualView">
                <table className="t" id="annualTable">
                  <thead>
                    <tr>
                      <th>월</th>
                      <th>생활주제</th>
                      <th>주별 소주제</th>
                    </tr>
                  </thead>
                  <tbody></tbody>
                </table>
              </div>
              <div id="monthlyView" hidden>
                <table className="t t-month">
                  <tbody>
                    <tr>
                      <td className="th">놀이 주제</td>
                      <td colSpan={4}>
                        <span data-type="우리 주변 환경과 생활"></span>{" "}
                        <span className="tag plum inherit">연간 11월에서 이어받음</span>
                      </td>
                    </tr>
                    <tr className="hd">
                      <td className="th">구분</td>
                      <td>1주 · 11.02</td>
                      <td>2주 · 11.09</td>
                      <td>3주 · 11.16</td>
                      <td>4주 · 11.23</td>
                    </tr>
                    <tr>
                      <td className="th">바깥놀이</td>
                      <td className="w" data-type="흙과 돌멩이로 놀이하기"></td>
                      <td className="w" data-type="바람으로 나뭇잎 보내기"></td>
                      <td className="w" data-type="자연의 소리 들어 보기"></td>
                      <td className="w" data-type="분리수거장 찾으며 산책하기"></td>
                    </tr>
                    <tr>
                      <td className="th">안전교육</td>
                      <td className="w slot" data-slot="0"></td>
                      <td className="w slot" data-slot="1"></td>
                      <td className="w slot" data-slot="2"></td>
                      <td className="w slot" data-slot="3"></td>
                    </tr>
                  </tbody>
                </table>
                <p className="pool-h">안전교육 후보 · 법정 교육 기준에서 골랐어요</p>
                <div className="pool" id="pool">
                  <span data-cand="0">
                    <b>성폭력 예방</b>좋은 느낌과 싫은 느낌을 구별해요.
                  </span>
                  <span data-cand="1">
                    <b>교통안전</b>걸을 때는 어른의 손을 잡아요.
                  </span>
                  <span data-cand="2">
                    <b>재난대비</b>옷에 불이 붙으면 어떻게 해야 하는지 알아봐요.
                  </span>
                  <span data-cand="3">
                    <b>아동학대 예방</b>내 감정을 말하고 도움을 청해요.
                  </span>
                  <span>
                    <b>실종 예방</b>어떤 상황에서 길을 잃을 수 있는지 알아봐요.
                  </span>
                  <span>
                    <b>약물 오남용 예방</b>집에서 쓰는 화학제품은 만지거나 먹지 않아요.
                  </span>
                </div>
              </div>
              <div id="weeklyView" hidden>
                <table className="t t-week">
                  <tbody>
                    <tr>
                      <td className="th">주제</td>
                      <td colSpan={5}>
                        우리 주변 환경과 생활 · 1주{" "}
                        <span className="tag plum">월간 1주에서 이어받음</span>
                      </td>
                    </tr>
                    <tr className="hd">
                      <td className="th">요일</td>
                      <td>월</td>
                      <td>화</td>
                      <td>수</td>
                      <td>목</td>
                      <td>금</td>
                    </tr>
                    <tr>
                      <td className="th">바깥놀이</td>
                      <td colSpan={5} className="span">
                        <span data-type="흙과 돌멩이로 놀이하기"></span>
                      </td>
                    </tr>
                    <tr>
                      <td className="th">놀이 활동</td>
                      <td className="d" data-type="흙 만져 보기"></td>
                      <td className="d" data-type="돌멩이 크기 비교"></td>
                      <td className="d" data-type="물 붓고 흙 관찰"></td>
                      <td className="d" data-type="돌멩이 그림 그리기"></td>
                      <td className="d" data-type="흙 놀이 이야기 나누기"></td>
                    </tr>
                  </tbody>
                </table>
                <p className="pool-h">요일마다 따로 다시 만들 수 있어요 · 이 주간 표는 예시예요</p>
              </div>
              <div className="real" id="realView" hidden>
                <Image
                  id="realAnnual"
                  src="/landing/v2/plan-annual.webp"
                  alt="쌤플에서 확정한 2026학년도 연간 보육계획안 실제 화면"
                  width={1600}
                  height={1074}
                  sizes="(max-width: 900px) 92vw, 640px"
                />
                <Image
                  id="realMonthly"
                  hidden
                  src="/landing/v2/plan-monthly.webp"
                  alt="쌤플에서 만든 11월 월간계획안 편집 실제 화면"
                  width={1600}
                  height={976}
                  sizes="(max-width: 900px) 92vw, 640px"
                />
                <p id="realCap">테스트 계정에서 실제로 만든 연간 계획안 화면이에요.</p>
              </div>
              <div className="chain">
                <b className="on" id="chA">
                  연간
                </b>
                →<b id="chM">월간</b>→<b id="chW">주간</b>
                <span style={{ marginLeft: "auto" }}>PDF · HWPX · HWP</span>
              </div>
            </div>
          </div>
        </section>

        <section className="try" id="try" aria-labelledby="try-title">
          <h2 id="try-title">
            기록 한 줄로
            <br />
            일지를 써 보세요.
          </h2>
          <p className="sub">
            적은 문장은 일지의 사실 칸에 그대로 들어가요.
            <br />
            아래 두 줄은 쌤플이 만들어 주는 초안의 예시예요.
          </p>
          <div className="try-grid">
            <form className="try-card" id="tryForm">
              <label className="lab" htmlFor="tryLine">
                지금, 한 줄
              </label>
              <textarea
                id="tryLine"
                rows={3}
                maxLength={200}
                placeholder="오늘 본 장면을 본 대로 적어 보세요"
                defaultValue="바깥놀이에서 도토리를 크기별로 줄 세웠다. 친구가 와서 같이 세웠다."
              ></textarea>
              <fieldset className="areas" id="areas">
                <legend>영역</legend>
              </fieldset>
              <p className="try-note">여기 적은 글은 저장되지 않아요.</p>
            </form>
            <figure className="try-doc" style={{ margin: "0" }} aria-label="일일 보육일지 미리보기">
              <h3 className="doc-h">일일 보육일지 · 미리보기</h3>
              <div className="r fact">
                <b>사실</b>
                <span>
                  <em>선생님이 적은 그대로</em>
                  <i className="fact-text" id="tryFact"></i>
                </span>
              </div>
              <div className="r draft" id="tryPlay">
                <b>놀이 모습</b>
                <span></span>
              </div>
              <div className="r draft" id="tryNext">
                <b>내일 이어갈 것</b>
                <span></span>
              </div>
            </figure>
          </div>
        </section>

        <section className="where" aria-labelledby="where-title">
          <h2 id="where-title">
            교실에서는 휴대폰,
            <br />
            하원 뒤엔 컴퓨터.
          </h2>
          <p className="sub">
            설치하지 않아도 돼요. 브라우저로 열면 같은 반 기록이 그대로 이어져요.
          </p>
          <div className="phones" id="phones">
            <figure>
              <Image
                src="/landing/v2/phone-records.webp"
                alt="휴대폰의 관찰 기록 화면"
                width={780}
                height={1688}
                sizes="240px"
              />
            </figure>
            <figure>
              <Image
                src="/landing/v2/phone-routines.webp"
                alt="휴대폰의 일과 기록 화면"
                width={780}
                height={1688}
                sizes="240px"
              />
            </figure>
            <figure>
              <Image
                src="/landing/v2/phone-weekly.webp"
                alt="휴대폰의 주간 기록 화면"
                width={780}
                height={1688}
                sizes="240px"
              />
            </figure>
          </div>
        </section>

        <section className="compare" id="compare" aria-labelledby="cmp-title">
          <h2 id="cmp-title">
            그냥 한글 파일에
            <br />
            쓰면 안 될까요?
          </h2>
          <p className="sub">그래도 돼요. 다만 이런 점이 달라요.</p>
          <div className="toggle" id="toggle" role="group" aria-label="비교 보기">
            <span className="knob" aria-hidden="true"></span>
            <button type="button" aria-pressed="true" data-side="a">
              빈 한글 파일
            </button>
            <button type="button" aria-pressed="false" data-side="b">
              쌤플
            </button>
          </div>
          <div className="rows">
            <div className="row">
              <b>첫 문장</b>
              <p>
                <span className="a">빈 칸에서 시작해요.</span>
                <span className="b">초안이 먼저 채워져 있어요.</span>
              </p>
            </div>
            <div className="row">
              <b>근거</b>
              <p>
                <span className="a">「이거 어디서 나왔지?」 기억에 기대요.</span>
                <span className="b">문장마다 어느 기록에서 왔는지 보여요.</span>
              </p>
            </div>
            <div className="row">
              <b>이어 쓰기</b>
              <p>
                <span className="a">작년 파일을 복사해서 고쳐 써요.</span>
                <span className="b">확정한 연간이 월간으로, 월간이 주간으로.</span>
              </p>
            </div>
            <div className="row">
              <b>아이 이름</b>
              <p>
                <span className="a">AI를 안 쓰니 걱정할 일이 없어요.</span>
                <span className="b">AI에는 가명만 보내요.</span>
              </p>
            </div>
            <div className="row">
              <b>제출</b>
              <p>
                <span className="a">한글 파일 그대로.</span>
                <span className="b">한글 파일 그대로. 이건 같아요.</span>
              </p>
            </div>
          </div>
        </section>

        <section className="end" id="end" aria-labelledby="end-title">
          <div>
            <h2 id="end-title" className="note">
              쌤의 계획이
              <br />
              쉬워지는 순간,
              <br />
              <b>쌤플.</b>
            </h2>
            <div>
              <Link className="btn" href="/signup" onClick={fadeTo}>
                우리 반으로 시작하기
              </Link>
            </div>
            <small>설치 없이 브라우저에서 바로 시작해요. 요금은 받지 않아요.</small>
          </div>
        </section>
      </main>
      <div className="lp-footer">
        <LegalFooter width="max-w-[1180px]" />
      </div>
    </div>
  );
}
