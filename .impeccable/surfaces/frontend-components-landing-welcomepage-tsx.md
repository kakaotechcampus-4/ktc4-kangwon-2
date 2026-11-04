---
version: 1
slug: "frontend-components-landing-welcomepage-tsx"
primary_target: "frontend/components/landing/WelcomePage.tsx"
related_targets: ["frontend/app/welcome/page.tsx"]
---

# /welcome — 소개 화면

Scope: 로그인 전 소개 화면 한 장(`/welcome`). Visitor mode: Persuade.
Audience: 만 3~5세 유아반 담임교사. 낮잠 시간 · 퇴근 뒤 짧은 틈에 혼자 문서를 쓰는 사람.
Action: 가입(「우리 반으로 시작하기」 → /signup). 보조: 로그인.
Proof: 운영 화면 실제 캡처(멘토 테스트 계정, 아이 이름 흐림) · 공식 기준(누리과정 5영역, 평가제 지표, 공식 양식). 후기 · 로고 · 숫자는 없음 — 후기는 받으면 넣는다(그 전엔 안 보임).
Constraints: 색은 `--pg-*` 토큰만. 옛 화면은 `/welcome/classic` 에 보관.

## Direction contract

THESIS: 「적은 사실은 그대로, 문장만 초안으로」를 방문자가 직접 해 보게 한다. 기능 카드 나열과 AI 마법 문구(「AI가 다 써 줘요」)를 거부한다.
OWN-WORLD: 아이보리 종이 바탕 · 크림 띠, 보라 한 가지 강조, 손글씨 Gaegu 는 이름과 마감 제목에만, 본문 Noto Sans KR. 노란 쪽지 · 칠판 · 실제 앱 캡처가 재료. 선 그림(hairline)은 잉크 갈색 선에 보라 하이라이트.
STORY: 무엇인지(조용한 기록장) → 실제 화면 → 약속 셋 → 한 줄을 직접 적어 사실이 잠기는 걸 본다 → 그림 여섯 장으로 흐름 → 화면별 실제 캡처 → 작은 것 → 어디서나 → 아이 정보 · 묻는 것 → 가입.
FIRST VIEWPORT: 가운데 정렬. 위에서부터 큰 「S.」 아이콘 104px, Gaegu 「쌤플」 96px, 한 줄 소개, 보조 문장, 보라 알약 단추(주 행동)와 글 링크. 그 아래 노트북 창(홈 캡처) 86% 폭 + 오른쪽 아래 휴대폰이 겹쳐 첫 화면 아래쪽을 채운다.
FORM: 사용자가 고른 시안 D(앱 소개형, things 짜임) — 「시안 D를 채택해보자」. roll 은 5번을 배정했으나 사용자 고정이 우선(엔진: "A user- or brief-pinned decision beats the roll, always."). seed:9ebf741092f746a8
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

Memorable moment: 「직접 한 줄」 — 방문자가 적은 문장이 그대로 「사실 · 잠금」 칸에 들어가고, 고른 영역에 맞는 예시 초안 두 줄이 그 아래 겹쳐 놓인다(예시라고 밝힘).
Unresolved: 파일럿 후기 문구 · 동의.
