"""LLM 이 실패하는 세 가지. **뭉치면 화면이 틀린 안내를 띄운다.**

계약(docs/api-spec.md 「공통」)이 코드를 이렇게 가른다.

    DEPENDENCY_UNAVAILABLE  503   설정이 없다.  재시도해도 같다 — 운영 문의
    LLM_BUDGET_EXCEEDED     503   한도·키 삭제(401·429).  재시도해도 같다 — 운영 문의
    GENERATION_FAILED       500   호출이 깨졌거나 답이 계약을 어겼다.  재시도하면 될 수도

호출 상한(`LlmCallCapExceeded`)은 `LlmFailed` 의 하위라 계약이 같다 — 라우터가 `LlmFailed` 로
잡는 곳은 그대로 `GENERATION_FAILED` 로 간다.

셋을 한 코드로 뭉치면 FE 가 「운영 문의」를 띄워야 할 자리에 「다시 시도」를 띄운다.
"""


class LlmUnavailable(RuntimeError):
    """설정이 없어 부를 수 없다. 교사가 고칠 수 없다."""


class LlmFailed(RuntimeError):
    """불렀는데 실패했거나 답이 계약을 어겼다."""


class LlmBudgetExceeded(RuntimeError):
    """예산·한도에 걸렸다. 키가 삭제됐을 수 있다."""


class LlmCallCapExceeded(LlmFailed):
    """생성 요청 하나가 부를 수 있는 LLM 횟수를 넘었다(ADR-081). 다시 부르지 않는다."""
