# 브랜치 전략 · 리뷰 흐름

카카오테크 캠퍼스 4기 2단계 — 강원대 2팀

## 브랜치 역할

| 브랜치 | 역할 | 직접 커밋 |
|---|---|---|
| `main` | 멘토 리뷰를 통과한 결과물. 팀장(PM)만 머지한다. | ❌ |
| `develop` | 팀의 기본 브랜치. 팀 내 리뷰를 통과한 코드가 모인다. | ❌ (PR로만) |
| `feature/*` | 주간 기능 개발 | ✅ |
| `refactor/*` | 멘토 피드백 반영 | ✅ |

## 주간 사이클

```
feature/*  ──PR──▶  develop        (1) 팀 내 리뷰
                       │
                       └──PR──▶  main   (2) 멘토 리뷰 요청
                       ┌───────────┘
refactor/*  ◀─분기──  develop      (3) 멘토 피드백 반영
    └──PR──▶  develop              (4) 반영분 머지
                       └──PR──▶  main   (5) 팀장(PM)이 머지
```

1. **기능 개발** — 매주 `develop`에서 `feature/*`를 만들어 개발하고, `develop`으로 PR을 올린다. 팀원끼리 리뷰한다.
2. **멘토 리뷰 요청** — 팀 내 리뷰가 끝나면 `develop` → `main` PR을 만든다. 이 PR에 멘토가 자동 지정된다.
3. **피드백 반영** — 멘토 피드백을 받으면 `develop`에서 `refactor/*`를 만들어 반영한다. `feature/*`에 이어서 하지 않는다.
4. **반영분 머지** — `refactor/*` → `develop` PR로 머지한다.
5. **최종 머지** — `main` 머지는 팀장(PM)이 한다.

## 실수하기 쉬운 지점

- **`develop` → `main` PR의 base 확인.** `develop`이 기본 브랜치라서 GitHub이 base를 `develop`으로 미리 채워둔다. `main`으로 바꾸지 않으면 멘토가 자동 지정되지 않고 리뷰가 시작되지 않는다.
- **재리뷰 PR에는 반영 내역을 쓴다.** PR 템플릿의 "지난 리뷰 반영" 항목에 어떤 피드백을 어디서 반영했는지, 반영하지 않기로 한 것은 그 이유를 적는다.
- **`.github/` 일부는 운영진 소유다.** `assign-mentor.yml`, `notify-discord.yml`, `convention-check.yml`, `CODEOWNERS` 네 파일은 수정·삭제하지 않는다. 지우면 멘토 자동 지정과 Discord 알림이 멈춘다. 그 외 `.github/` 파일(PR 템플릿, 팀 자체 CI 등)은 자유롭게 추가·수정해도 된다. 자세한 내용은 `.github/CODEOWNERS` 주석에 있다.
