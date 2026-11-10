/**
 * 하루 장면의 내용 — 소개 화면(/welcome, landing-engine.js)과 로그인 화면 왼쪽(components/auth/LoginDay.tsx)이 함께 쓴다.
 * 한쪽만 고치면 두 화면의 말이 갈라지므로 여기 한 곳에 둔다.
 */

/** 쪽지 판의 다섯 장(소개 화면 칠판 판) */
export const KEYS = [
  {
    id: "obs",
    name: "관찰 기록",
    sub: "본 대로 한 줄",
    peek: '<span class="pk-hand">도토리를 크기별로<br>줄 세웠다.</span>',
  },
  {
    id: "routine",
    name: "일과 기록",
    sub: "칠판에 쪽지로",
    peek: '<span class="pk-list"><span><i>09:20</i>실내놀이</span><span><i>11:00</i>바깥놀이</span></span>',
  },
  {
    id: "journal",
    name: "보육일지",
    sub: "적은 기록으로 초안",
    peek: '<span class="pk-lock">적은 그대로</span><span class="pk-lines"><i></i><i></i></span>',
  },
  {
    id: "eval",
    name: "평가 점검",
    sub: "서류를 한 장에",
    peek: '<span class="pk-bars"><span>보육일지<i style="--w:76%"></i></span><span>계획안<i style="--w:100%"></i></span><span>관찰<i style="--w:45%"></i></span></span>',
  },
  {
    id: "plan",
    name: "계획안",
    sub: "연간 → 월간 → 주간",
    wide: true,
    peek: '<span class="pk-months"><i>3월 우리 원과 친구</i><i>4월 따뜻한 봄</i><i>5월 소중한 나와 가족</i></span>',
  },
];

/** 하루 여섯 장면. 시각(t) · 장면 이름 · 창 제목 · 선생님 생각 한 줄 · 바탕색 */
export const SCENES = [
  {
    t: "0850",
    ampm: "am",
    scene: "등원하고 바깥놀이",
    sub: "수요일 아침",
    title: "관찰 기록",
    quote: "도토리를 크기별로 줄 세우네. 잊기 전에 한 줄만 적어 두자.",
    bg: "#fffdf8",
    night: false,
  },
  {
    t: "1040",
    ampm: "am",
    scene: "간식 먹고 일과 정리",
    sub: "같은 날",
    title: "일과 기록",
    quote: "오늘 일과는 어제랑 거의 같으니까, 기본 하루를 불러오면 되겠다.",
    bg: "#eef4ee",
    night: false,
  },
  {
    t: "0120",
    ampm: "pm",
    scene: "낮잠 시간",
    sub: "40분의 틈",
    title: "보육일지 초안",
    quote: "낮잠 시간 40분. 오늘 일지 초안부터 열어 보자.",
    bg: "#f1ebf6",
    night: false,
  },
  {
    t: "0330",
    ampm: "pm",
    scene: "오후 놀이 뒤",
    sub: "한 아이씩 돌아보기",
    title: "관찰일지",
    quote: "이번 달 아이 A 기록이 세 건 모였네. 관찰일지로 묶어 보자.",
    bg: "#fbf3df",
    night: false,
  },
  {
    t: "0540",
    ampm: "pm",
    scene: "하원 뒤",
    sub: "퇴근 전 30분",
    title: "보육일지 확정",
    quote: "사실 칸은 내가 적은 그대로네. 두 줄만 고치고 확정.",
    bg: "#3a3631",
    night: true,
  },
  {
    t: "0400",
    ampm: "pm",
    scene: "금요일 오후",
    sub: "한 주 마무리",
    title: "주간 기록",
    quote: "이번 주는 빈 날이 없네. 주간 일지도 바로 만들자.",
    bg: "#2b332e",
    night: true,
  },
];

/** 시간표에 보이는 여섯 시각 — SCENES 와 순서가 같다 */
export const MARKS = ["08:50", "10:40", "1:20", "3:30", "5:40", "금 4:00"];

/** 첫 장면(관찰 기록)에 한 글자씩 적히는 관찰 */
export const OBS = "바깥놀이에서 도토리를 크기별로 줄 세웠다. 친구가 와서 같이 세웠다.";
