# ktc4-kangwon-2

카카오테크 캠퍼스 4기 2단계 팀 프로젝트 — 강원대 2팀

## 브랜치 규칙 (필수)

- 기능 개발은 `develop`에서 `feature/*`를 만들어 진행하고 `develop`으로 PR한다.
- 멘토 피드백 반영은 `develop`에서 `refactor/*`를 만들어 진행하고 `develop`으로 PR한다. `feature/*`에 이어서 하지 않는다.
- `main`과 `develop`에 직접 커밋·push 하지 않는다. 변경은 항상 PR로만 들어간다.
- `develop` → `main` PR은 멘토 리뷰 요청이다. base가 `main`인지 반드시 확인한다(GitHub이 `develop`으로 미리 채워둔다).
- `main` 머지는 팀장(PM)만 한다.
- `.github/` 중 `assign-mentor.yml`, `notify-discord.yml`, `convention-check.yml`, `CODEOWNERS`는 수정·삭제하지 않는다.

전체 흐름과 예외 상황은 [docs/branch-strategy.md](docs/branch-strategy.md)에 있다. 브랜치·PR·머지와 관련된 작업을 하기 전에 이 문서를 읽는다.
