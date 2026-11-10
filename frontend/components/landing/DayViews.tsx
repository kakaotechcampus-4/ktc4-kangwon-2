import type { CSSProperties } from "react";

/**
 * 하루 장면의 기록 창 속 여섯 장면. 소개 화면(/welcome)과 로그인 화면 왼쪽(components/auth/LoginDay.tsx)이 함께 쓴다.
 * id 를 지우지 않는다 — 두 화면 모두 id 로 찾아 글자 · 표시를 바꾼다. 그래서 한 화면에 한 번만 그린다.
 */
export default function DayViews() {
  return (
    <>
      <div className="view" data-view="0">
        <span className="tag note">관찰 기록</span>
        <div className="field">
          <label>아이, 영역, 언제</label>
          <div style={{ marginTop: "6px", display: "flex", flexWrap: "wrap", gap: "6px" }}>
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
              등원 및 자유놀이 <small>07:30</small>
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
        <h3 className="doc-h">11월 4일 일일 보육일지</h3>
        <div className="r fact">
          <b>사실</b>
          <span>
            <em>선생님이 적은 그대로</em>바깥놀이에서 도토리를 크기별로 줄 세웠다. 친구가 와서 같이
            세웠다.
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
        <h3 className="doc-h">아이 A 11월 관찰일지</h3>
        <div className="picks" id="ojPicks">
          <span>11.02 블록으로 다리 만들기</span>
          <span>11.03 모래에 물길 파기</span>
          <span>11.04 도토리 크기별로 줄 세우기</span>
        </div>
        <div className="r fact">
          <b>관찰 내용</b>
          <span>
            <em>선생님이 적은 기록 3건 그대로</em>블록으로 다리를 만들었다. 모래에 물길을 파고
            「바다야」라고 말했다. 도토리를 크기별로 줄 세웠다.
          </span>
        </div>
        <div className="r gen" id="oj1">
          <b>해석</b>
          <span>
            <em>초안</em>크기와 모양을 비교하고 물길을 바꿔 보며 주변 사물을 탐색하는 모습이
            이어졌다.
          </span>
        </div>
        <div className="r gen" id="oj2">
          <b>배움</b>
          <span>
            <em>누리과정 자연탐구 초안</em>주변 세계와 자연에 대해 지속적으로 궁금증을 가진다.
          </span>
        </div>
      </div>
      <div className="view doc" data-view="4">
        <h3 className="doc-h">11월 4일 일일 보육일지</h3>
        <div className="r fact">
          <b>사실</b>
          <span>바깥놀이에서 도토리를 크기별로 줄 세웠다. 친구가 와서 같이 세웠다.</span>
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
          <span className="arch-h">문서 보관함 › 보육일지</span>
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
        <span className="tag sage">11월 2일 – 6일 주간 기록</span>
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
    </>
  );
}
