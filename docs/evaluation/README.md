# 평가 근거

평가 항목마다 문서 한 장. **주장 옆에 근거를 붙인다.**
근거는 커밋 · PR 번호 · ADR · 코드 경로 · 문서 중 하나다. 근거 없는 줄은 적지 않는다.

> **평가 기준 원문이 아직 저장소에 없다.** 각 파일 맨 위 「기준 원문」 칸은 비어 있다.
> 카테캠에서 받은 기준 문장을 **그대로** 붙인다. 우리가 지어낸 문장을 기준 자리에 쓰지 않는다.
> 기준을 받은 사람이 채우고, 채운 뒤 이 줄을 지운다.

| 파일 | 무엇을 모으나 |
|---|---|
| [01-problem-scenario.md](01-problem-scenario.md) | 누구의 어떤 문제인가 · 실제로 조사한 것 |
| [02-stability-usability.md](02-stability-usability.md) | 안 죽는가 · 교사가 쓸 수 있는가 |
| [03-agentic-experience.md](03-agentic-experience.md) | 교사가 겪는 AI — 어디까지 AI 가 하고 어디서 사람이 정하나 |
| [04-service-completeness.md](04-service-completeness.md) | 기능이 끝까지 도는가 · **핵심 기능** |
| [05-agentic-implementation.md](05-agentic-implementation.md) | 안에서 어떻게 돌아가나 — Rule · LLM · Rule |
| [06-ai-quality.md](06-ai-quality.md) | 나온 글이 쓸 만한가 · 어떻게 재는가 |
| [07-guardrails.md](07-guardrails.md) | 하면 안 되는 것을 코드가 막는가 |
| [08-code-tests.md](08-code-tests.md) | 테스트 · CI |
| [09-deployment.md](09-deployment.md) | 배포 · 운영 |
| [10-collaboration.md](10-collaboration.md) | 여섯 명이 어떻게 일했나 |

## 쓰는 법

한 줄에 **주장 하나 + 근거 하나.**

```
- 아동 실명이 LLM 프롬프트에 안 간다 — `backend/app/shared/childCode/` · ADR-004 · ADR-013
```

- **근거는 저장소 안의 것만.** 개인 문서 · 브랜치에만 있는 문서는 인용하지 않는다 (ADR-031).
- **아직 아닌 것을 숨기지 않는다.** 각 파일에 「아직 아닌 것」 칸이 있다. 비워 두면 평가 때 질문으로 돌아온다.
- 「더 모을 근거」는 체크박스다. 남은 작업 목록으로 쓴다.
