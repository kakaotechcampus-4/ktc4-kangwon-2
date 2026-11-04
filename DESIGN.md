---
name: 쌤플 (Ssample)
description: 선생님 곁의 조용한 기록장 — 크림 종이 위에 흰 카드, 보라 한 가지, 손글씨 제목, 노란 쪽지와 칠판.
colors:
  primary: "#7053a0"
  primary-hover: "#60438e"
  primary-deep: "#53479a"
  primary-ink: "#5e4b96"
  primary-tint: "#eee4f4"
  primary-tint-line: "#c5b7dd"
  earth-dot: "#c2a36a"
  note: "#f5e6aa"
  note-soft: "#f7edce"
  sage-tint: "#e8f1ea"
  sage-ink: "#49654f"
  peach: "#f8efdc"
  board: "#38453e"
  board-ink: "#f4f1e8"
  frame: "#8c6d49"
  cream: "#f3eee4"
  ivory: "#fbf7ed"
  paper: "#ffffff"
  paper-warm: "#fbf3df"
  shell: "#ede8e0"
  line: "#ddd6ca"
  ink: "#34312f"
  ink-soft: "#5c5243"
  ink-hint: "#a3998a"
  rail: "#2e2a26"
  alert-ink: "#8a3327"
  doc-line: "#555555"
typography:
  display:
    fontFamily: "Gaegu, cursive"
    fontSize: "clamp(64px, 9vw, 96px)"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "-0.02em"
  handwritten-title:
    fontFamily: "Gaegu, cursive"
    fontSize: "34px"
    fontWeight: 700
    lineHeight: 1.2
  headline:
    fontFamily: "Noto Sans KR, Apple SD Gothic Neo, Malgun Gothic, system-ui, sans-serif"
    fontSize: "clamp(30px, 4.2vw, 48px)"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.035em"
  title:
    fontFamily: "Noto Sans KR, Apple SD Gothic Neo, Malgun Gothic, system-ui, sans-serif"
    fontSize: "22px"
    fontWeight: 700
    lineHeight: 1.4
    letterSpacing: "-0.03em"
  body:
    fontFamily: "Noto Sans KR, Apple SD Gothic Neo, Malgun Gothic, system-ui, sans-serif"
    fontSize: "17px"
    fontWeight: 400
    lineHeight: 1.75
  body-small:
    fontFamily: "Noto Sans KR, Apple SD Gothic Neo, Malgun Gothic, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.7
  label:
    fontFamily: "Noto Sans KR, Apple SD Gothic Neo, Malgun Gothic, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.7
rounded:
  slip: "2px"
  form: "4px"
  md: "6px"
  lg: "14px"
  panel: "28px"
  pill: "999px"
spacing:
  xs: "8px"
  sm: "12px"
  md: "16px"
  lg: "28px"
  xl: "64px"
  section: "120px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.paper}"
    rounded: "{rounded.pill}"
    padding: "0 26px"
    height: "50px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.paper}"
  button-workspace:
    backgroundColor: "{colors.primary-tint-line}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "11px 17px"
    height: "44px"
  button-secondary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "11px 17px"
    height: "44px"
  button-secondary-hover:
    backgroundColor: "{colors.primary-tint}"
  text-link:
    textColor: "{colors.primary-ink}"
    height: "44px"
  chip:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    padding: "0 14px"
    height: "40px"
  chip-selected:
    backgroundColor: "{colors.primary-tint}"
    textColor: "{colors.primary-ink}"
    rounded: "{rounded.pill}"
  input-field:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "11px 12px"
    height: "44px"
  card:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "28px"
  card-lifted:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "26px 28px 22px"
  form-sheet:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.form}"
    padding: "22px"
  fact-cell:
    backgroundColor: "{colors.note-soft}"
    textColor: "{colors.ink}"
  sticky-note:
    backgroundColor: "{colors.note-soft}"
    textColor: "{colors.ink}"
    rounded: "{rounded.slip}"
    padding: "13px 15px 14px"
  chalkboard:
    backgroundColor: "{colors.board}"
    textColor: "{colors.board-ink}"
    padding: "22px"
  nav-rail:
    backgroundColor: "{colors.rail}"
    textColor: "{colors.board-ink}"
---

# Design System: 쌤플 (Ssample)

## Overview

**Creative North Star: "조용한 기록장"**

쌤플은 교사가 낮잠 시간과 퇴근 뒤 짧은 틈에 펴는 공책이다. 화면은 교실의 재료로 만든다. 따뜻한 크림 종이 바탕 위에 흰 카드를 놓고, 벽에 붙인 노란 쪽지와 나무테 칠판을 올린다. 강조색은 보라 하나뿐이다. 이름과 제목 몇 군데만 손글씨(Gaegu)로 쓰고, 읽어야 하는 글은 전부 반듯한 본문 글꼴(Noto Sans KR)로 쓴다. 손글씨와 쪽지는 쌤플의 얼굴이다. 그래서 아껴 쓴다. 많이 쓰면 얼굴이 아니라 무늬가 된다.

밀도는 차분하다. 본문은 17px, 줄 간격은 넉넉하게 1.75로 두고, 한글이 단어 중간에서 끊기지 않게 줄을 낱말 단위로 넘긴다. 깊이는 크림 위의 흰 카드, 그리고 멀리 퍼지는 부드러운 그림자로 만든다. 선을 더 긋기보다 종이의 가장자리(톱니로 자른 영수증, 찢은 쪽지, 공책 줄)로 경계를 보인다. 공식 문서를 흉내 내는 자리만 예외다. 그 자리는 한글 양식처럼 진한 선으로 칸을 또렷하게 나눈다.

어두운 면은 두 군데뿐이다. 먹색 사이드바는 메뉴 기둥이고, 칠판은 쪽지를 붙이는 판이다. 화면 전체를 어둡게 하는 다크 테마는 지웠다. 종이 느낌 화면에 어두운 판이 맞지 않아서다(토큰 파일 머리말).

소개 화면(`/welcome`)은 같은 세계를 쓴다. 다만 몇 가지를 바꿨다. 바탕을 크림보다 한 단계 밝은 아이보리로 올렸고, 주 단추를 흰 글자의 보라 알약으로 키웠고, 둥근 정도를 키웠다. 무엇이 다른지는 아래 각 절의 「소개 화면」 문단에 적었다.

**Key Characteristics:**
- 크림 바탕 + 흰 카드. 크림 위에 크림을 올리지 않는다.
- 강조색은 보라 하나. 세이지 · 쪽지 노랑 · 살구는 바탕 면에만 쓴다.
- 손글씨(Gaegu)는 이름과 제목에만. 본문은 Noto Sans KR.
- 재료는 종이 · 쪽지 · 테이프 · 칠판 · 실제 앱 화면. 새로 지어낸 장식은 쓰지 않는다.
- 사실이 들어가는 칸은 노란 쪽지 색으로 잠근다.

## Colors

따뜻한 종이색 바탕 위에 보라 한 가지를 얹고, 교실의 크레파스 같은 옅은 색 몇 가지를 면으로만 까는 팔레트다.

### Primary
- **쌤플 보라** (primary): 주 단추, 선택된 상태, 키보드 초점 테두리. 한 화면에서 가장 먼저 눌러야 할 것에만 쓴다.
- **눌러 볼 보라** (primary-hover): 보라 단추 위에 포인터가 올라갔을 때.
- **로고 보라** (primary-deep): 워드마크 「Ssample」과 「S.」 표시에만 쓴다.
- **연보라 글자** (primary-ink): 연보라 바탕 위의 글자, 글 링크.
- **연보라 바탕** (primary-tint): 고른 칩, 보조 단추를 가리켰을 때, 소개 화면의 판 한 장.
- **연보라 테두리** (primary-tint-line): 연보라 면의 테두리. 작업 화면의 주 단추 면이기도 하다.

### Secondary
- **흙빛 점** (earth-dot): 「Ssample.」과 「S.」의 마침표 한 점. 다른 곳에는 쓰지 않는다.

### Tertiary
- **벽 쪽지 노랑** (note): 벽에 붙인 쪽지, 글자를 끌어 고른 영역.
- **본문 쪽지 노랑** (note-soft): 본문 안의 쪽지, 그리고 **사실 칸**. 교사가 적은 그대로 잠긴 칸은 이 색으로 칠한다.
- **세이지** (sage-tint, sage-ink): 확정 표시와 강조 바탕. 세이지 글자는 그 바탕 위에서만 쓴다.
- **살구 종이** (peach): 소개 화면의 판 한 장. 앱에서는 옛 「월간 · 주간 · 일간」 색 자리에 남아 있는 값이다.
- **칠판** (board, board-ink, frame): 초록 칠판 면, 분필 글자, 나무테. 면은 가운데가 밝고 가장자리가 어두운 세 겹으로 칠하고, 나무테는 네 변의 색을 달리해 두께를 만든다(`.chalkboard`).

### Neutral
- **크림** (cream): 앱 페이지 바탕. 소개 화면에서는 「그림 여섯 장」 띠 바탕.
- **아이보리** (ivory): 쌓인 것을 올리는 종이. 흰 입력칸보다 한 단계 낮다. 소개 화면의 페이지 바탕이다.
- **흰 종이** (paper): 카드, 입력칸, 문서 미리보기 면.
- **공책 종이** (paper-warm): 입력칸 머리 · 바닥 띠, 소개 화면의 판 한 장.
- **안쪽 바닥** (shell): 표의 머리 칸, 노트북 창의 제목 띠.
- **연한 선** (line): 테두리와 구분선, 공책 줄.
- **먹** (ink): 본문 글자.
- **흐린 먹** (ink-soft): 보조 글자, 입력칸 예시 글. 어느 바탕에서도 6:1을 넘는다.
- **아주 흐린 먹** (ink-hint): 글자가 아닌 선과 그림에만 쓴다(그림 판의 중간 선 등). 흰 바탕에서 2.8:1이라 글자를 받치지 못한다.
- **먹색 기둥** (rail): 어두운 사이드바, 휴대폰 테.
- **빨강 글자** (alert-ink): 되돌리기 어려운 일의 경고 글자. 빨강 면은 연한 것부터 진한 것까지 세 단계가 따로 있다(`--pg-alert-*`).
- **양식 선** (doc-line): 공식 양식을 흉내 내는 표의 선.

### Named Rules
**The 토큰만 Rule.** 화면 코드에는 색 값을 직접 쓰지 않는다. 전부 `var(--pg-*)`로 쓰고, 색을 바꿀 때는 `styles/plan-generator-tokens.css` 한 파일만 고친다.

**The 보라 한 목소리 Rule.** 강조색은 보라 하나다. 세이지 · 노랑 · 살구 · 연보라는 면을 까는 데만 쓰고, 단추나 링크 색으로 쓰지 않는다.

**The 글로 가르는 Rule.** 종류(월간 · 주간 · 일간 등)는 색이 아니라 글로 가른다. 같은 색 단추 셋 가운데 눌린 것만 진해진다.

## Typography

**Display Font:** Gaegu (with cursive)
**Body Font:** Noto Sans KR (with Apple SD Gothic Neo, Malgun Gothic, system-ui, sans-serif)
**Label/Mono Font:** JetBrains Mono — 앱의 숫자 · 코드성 라벨에만 쓴다(라틴만 담은 자체 호스팅 파일). 소개 화면은 쓰지 않는다.

**Character:** 선생님이 칠판에 쓴 듯한 손글씨 이름 아래, 공문서처럼 반듯한 본문이 선다. 손글씨는 따뜻함을, 본문은 믿을 만함을 맡는다.

### Hierarchy
- **Display** (Gaegu 700, clamp 64–96px, 줄 간격 1): 소개 화면 첫 화면의 「쌤플」 한 단어. 마감 제목(「오늘 본 장면 하나부터」)도 같은 결로 44–68px.
- **Handwritten Title** (Gaegu 700, 34px, 1.2): 앱 화면 머리 제목. 소개 화면에서는 「지금, 한 줄」 같은 칸 이름에 28px로 쓴다.
- **Headline** (Noto Sans KR 700, clamp 30–48px, 1.25, 자간 -0.035em): 소개 화면의 절 제목. 줄 나눔은 균형 맞춤.
- **Title** (Noto Sans KR 700, 22px, 자간 -0.03em): 작은 절 제목. 소개 화면의 화면 소개 제목은 28–40px까지 키운다. 앱 카드 안 제목은 17–20px.
- **Body** (Noto Sans KR 400, 17px, 1.75): 본문. 이끄는 문단은 42–46ch에서 끊는다. 앱 카드 안 긴 글은 15px, 1.9, 72ch까지.
- **Body Small** (Noto Sans KR 400, 15px, 1.7): 목록, 보조 설명.
- **Label** (Noto Sans KR 400, 13px, 1.7): 칸 이름, 범례, 「예시 초안」 같은 꼬리표(12px까지).

### Named Rules
**The 손글씨는 얼굴에만 Rule.** Gaegu는 이름과 제목에만 쓴다. 본문에 쓰면 읽기 힘들다(`globals.css`). 소개 화면은 더 아껴서 이름 · 마감 제목 · 칸 이름에만 쓰고, 절 제목은 Noto Sans KR 굵은 글씨로 쓴다.

**The 낱말에서 넘기기 Rule.** 모든 글은 `word-break: keep-all`. 한글 낱말 가운데서 줄이 끊기지 않게 한다.

## Layout

본문 폭은 최대 1080px, 좌우 여백은 20px씩이다(`min(1080px, 100% - 40px)`). 앱은 먹색 사이드바 기둥과 크림 본문으로 나뉜다. 카드 사이는 22px, 카드 안 여백은 28px이다.

소개 화면은 한 줄로 내려가는 이야기다. 절 사이에 120–128px을 비우고, 제목과 그 아래 내용 사이는 40–56px로 둔다. 화면 소개는 글과 그림을 0.85 : 1.15로 놓고 한 줄씩 좌우를 바꾼다. 860px 아래에서는 한 줄로 쌓는다. 그림 여섯 장은 3칸 → 900px 아래 2칸 → 560px 아래 옆으로 넘기기다. 휴대폰 390px에서 가로 넘침이 없어야 한다.

누르는 자리는 최소 44px 높이를 지킨다(작업 화면 단추, 입력칸, 소개 화면 링크). 칩은 40px이다.

**The 한 번에 끝나게 Rule.** 짧은 틈에 쓰는 사람을 기준으로 한다. 한 화면에 한 가지 일을 놓고, 주 행동은 하나만 보라로 칠한다.

## Elevation & Depth

깊이는 바탕 두 겹으로 먼저 만든다. 크림 바탕 위에 흰 카드를 놓으면 선 없이도 떠 보인다. 그림자는 그다음이다. 위로 떠 있는 것에는 아래로 길게 퍼지는 부드러운 그림자를 쓰고(`--pg-shadow`), 크림 위의 크림처럼 경계가 흐린 곳은 그림자보다 바탕색을 먼저 바꾼다. 칠판만 안쪽 그림자로 판의 오목함을 만든다.

소개 화면은 같은 원리를 크게 쓴다. 노트북 창과 휴대폰, 실제 화면 캡처, 그림 판 아래에 멀리 퍼지는 그림자를 깔고, 가장자리에 1px 반투명 테를 그림자로 둘러 경계를 잡는다. 정확한 값은 `.impeccable/design.json`의 shadows에 있다.

앱의 쪽지 · 일과 줄 · 빈 상태 카드에는 흐림 없이 비켜 찍은 그림자(`--pg-shadow-hard`, 「도장 찍은 듯한」)가 남아 있다. 이 문서는 그것을 규칙으로 올리지 않는다. 새 화면은 그것을 따라 쓰지 않는다.

### Shadow Vocabulary
- **떠 있는 카드** (`box-shadow: var(--pg-shadow)`): 흰 카드, 소개 화면의 「지금, 한 줄」 카드와 일지 미리보기.
- **기기와 캡처** (반투명 1px 테 + 아래로 긴 그림자): 소개 화면의 노트북 창 · 휴대폰 · 화면 캡처.
- **칠판** (안쪽 그림자 + 아래 짧은 그림자): 판의 오목함과 벽에서 뜬 느낌.

### Named Rules
**The 크림 바탕, 흰 카드 Rule.** 바탕은 크림(또는 아이보리), 카드는 흰색. 크림 위에 크림을 올리면 경계가 사라져 글자가 묻힌다.

## Shapes

모서리는 무엇인지에 따라 다르다. 공식 양식을 닮은 것일수록 각지고, 화면을 감싸는 것일수록 둥글다.

- **쪽지** (rounded.slip, 2px): 벽에 붙인 종이. 거의 각진 종이다.
- **양식 종이** (rounded.form, 4px): 일지 미리보기처럼 공식 양식을 흉내 내는 면.
- **작업 도구** (rounded.md, 6px): 앱의 카드 · 입력칸 · 단추.
- **떠 있는 판** (rounded.lg, 14px): 소개 화면의 카드, 그림 판, 노트북 창.
- **큰 판** (rounded.panel, 28px): 소개 화면의 화면 캡처를 담는 정사각 판(폰에서는 22px).
- **알약** (rounded.pill, 999px): 칩과 소개 화면의 주 단추.

종이 가장자리 모양도 형태 언어다. 톱니로 자른 영수증 띠(`.slipEdge`), 아래를 찢은 쪽지(`.tornPaper`), 글줄 높이에 맞춘 공책 줄(`.ruledPaper`, 소개 화면의 「지금, 한 줄」)이 있다.

**The 줄은 글줄에 맞춘다 Rule.** 공책 줄 간격은 글줄 높이와 같아야 글자가 줄 위에 앉는다. 글자 크기를 바꾸면 줄 간격도 같이 바꾼다.

## Components

### Buttons
- **Shape:** 앱은 살짝 둥근 네모(6px), 소개 화면은 알약(999px).
- **Primary (소개 화면):** 보라 면에 흰 글자, 높이 50px, 좌우 26px, 굵게 16.5px. 아래로 옅은 보라 그림자. 가리키면 한 단계 진한 보라로 바뀌고 1px 떠오른다.
- **Primary (작업 화면):** 연보라 테두리 색 면에 먹 글자, 높이 44px, 여백 11px 17px.
- **Secondary:** 흰 면, 연한 선 테두리, 먹 글자. 가리키면 연보라 바탕.
- **Hover / Focus:** 초점은 보라 테두리(소개 화면 3px, 작업 화면 2px), 3px 띄움. 끌 수 없는 단추는 반투명 0.5.
- **Text Link:** 연보라 글자, 굵기 500, 오른쪽에 선으로 그린 꺾쇠. 가리키면 꺾쇠가 3px 앞으로 간다.

### Chips
- **Style:** 흰 바탕, 연한 선 테두리, 알약 모양, 높이 40px. 소개 화면의 누리과정 영역 고르기.
- **State:** 고르면 연보라 바탕 · 연보라 테두리 · 연보라 글자 · 굵게. 실제 라디오 단추를 칩 전체에 투명하게 덮어 키보드로도 고른다.

### Cards / Containers
- **Corner Style:** 앱 6px, 소개 화면 14px.
- **Background:** 흰 종이.
- **Shadow Strategy:** 앱은 연한 선 테두리 하나, 소개 화면은 떠 있는 카드 그림자 하나. 둘을 겹치지 않는다.
- **Border:** 카드 안에 카드가 들어가면 안쪽은 선과 그림자를 버리고 여백으로만 가른다.
- **Internal Padding:** 28px(소개 화면 26px 28px 22px).

### Inputs / Fields
- **Style:** 앱은 흰 면, 연한 선 테두리, 6px, 높이 44px. 고르는 칸은 브라우저 화살표를 끄고 오른쪽 12px 자리에 직접 그린 꺾쇠를 둔다.
- **Ruled input:** 소개 화면의 「지금, 한 줄」은 테두리 없는 공책 줄 칸이다. 줄 간격 2.2em, 예시 글은 흐린 먹.
- **Focus:** 보라 테두리, 칸에서 띄워 그린다.

### Navigation
- **앱:** 먹색 사이드바 기둥. 메뉴 글자는 밝은 회색, 묶음 제목은 더 흐리게, 지금 보는 메뉴는 어둡게 누른 보라 면. 워드마크는 그 위에서 연보라로 쓴다.
- **소개 화면:** 맨 위에 붙어 따라오는 띠. 아이보리 86% 반투명에 흐림을 깔고 아래에 연한 선 하나. 왼쪽 워드마크, 오른쪽 글 링크와 보라 알약 「시작하기」. 720px 아래에서는 바로 가기 링크를 접는다.

### Wordmark (Signature)
「Ssample」은 로고 보라, 마침표 한 점만 흙빛. 그 아래 손글씨 「쌤플」. 네모 자리에는 크림 타일 위의 「S.」 표시를 쓴다. 이 표시는 `app/icon.svg`와 모양이 같아야 한다.

### 사실 칸 (Signature)
공식 양식처럼 진한 선(양식 선)으로 나눈 표. 왼쪽 머리 칸은 안쪽 바닥색. 교사가 적은 그대로 들어가는 **사실 칸만** 본문 쪽지 노랑으로 칠하고 「선생님이 적은 그대로 · 잠금」 꼬리표를 단다. 그 아래 칸은 「예시 초안」 꼬리표를 달고 흰 바탕에 둔다.

### 칠판과 쪽지 (Signature)
초록 칠판 위에 일과 쪽지를 붙인다. 쪽지는 2px 모서리의 노랑 · 연보라 · 살구 · 세이지 종이이고, 색은 줄 번호로 정해 다시 그려도 같은 색이다. 쪽지 캐릭터 「포스티」는 쪽지 몸에 팔다리가 달려 있고, 걸을 때는 팔다리를 번갈아 돌리며 한 걸음에 한 번 뜬다.

### 선 그림 판 (소개 화면)
「그림 여섯 장」은 선으로 그린 등각 그림(hairline)이다. 선은 흐린 먹, 가리킨 부분은 보라로 밝힌다. 판 위에는 제목과 해 볼 일만 적고, 손가락만 쓰는 기기에서는 그림이 스스로 움직인다.

## Do's and Don'ts

### Do:
- **Do** 색은 `var(--pg-*)`로만 쓴다. 새 색이 필요하면 토큰 파일에 이름을 붙여 먼저 넣는다.
- **Do** 크림(또는 아이보리) 바탕 위에 흰 카드를 놓아 경계를 만든다.
- **Do** 보라는 한 화면의 주 행동 하나와 선택 · 초점 상태에만 쓴다.
- **Do** 교사가 적은 사실이 들어가는 칸은 본문 쪽지 노랑으로 칠하고, AI 초안 칸과 꼬리표로 구분한다.
- **Do** 보조 글자와 예시 글은 흐린 먹(ink-soft)으로 쓴다. 어느 바탕에서도 6:1을 넘는다.
- **Do** 움직임은 `prefers-reduced-motion`에서 끈다.
- **Do** 경계가 더 필요하면 선을 하나 더 긋기 전에 종이 가장자리(톱니 · 찢김 · 공책 줄)를 먼저 생각한다.

### Don't:
- **Don't** Gaegu를 본문이나 긴 설명에 쓰지 않는다.
- **Don't** 크림 위에 크림 면을 올리지 않는다.
- **Don't** 종류를 색으로 가르지 않는다(무지개 색 구분 금지).
- **Don't** 아주 흐린 먹(ink-hint)을 글자 색으로 쓰지 않는다.
- **Don't** 화면 전체를 어둡게 하는 다크 테마를 만들지 않는다. 어두운 면은 사이드바와 칠판뿐이다.
- **Don't** 빨강을 가벼운 알림에 쓰지 않는다. 빨강 세 단계는 되돌리기 어려운 일에만 쓴다.
- **Don't** 카드 안에 테두리 있는 카드를 또 넣지 않는다.
