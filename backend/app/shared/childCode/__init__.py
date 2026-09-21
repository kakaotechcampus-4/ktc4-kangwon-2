"""아동 실명 <-> 가명 치환. LLM 으로 나가기 직전에 쓴다 (ADR-004).

왜 치환하나 — 법이 아니라 로그 때문이다.

    LLM 요청 -> 서버 로그 -> 모니터링 -> 에러 리포터 -> 공급자 로그

이 경로 전부에 실명이 흐른다. 치환하면 경로 전체가 개인정보가 아니게 된다.
코드를 6명이 만지는데 `logger.info(prompt)` 한 줄이면 유출이다.

**치환에 실패하면 호출하지 않는다.** 조용히 실명을 내보내느니 에러를 낸다.

대상은 아동 이름만이 아니다. 교사가 자유 입력 칸(계획안 생성 메모 등)에
아이 이름을 적을 수 있다 (docs/api-spec.md).
"""

from .pool import PseudonymPool, has_final
from .substitute import SubstitutionError, mask, unmask

__all__ = ["PseudonymPool", "SubstitutionError", "has_final", "mask", "unmask"]
