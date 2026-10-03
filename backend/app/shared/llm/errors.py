"""LLM 이 실패하는 세 가지. **뭉치면 화면이 틀린 안내를 띄운다.**

계약(docs/api-spec.md 「공통」)이 코드를 이렇게 가른다.

    DEPENDENCY_UNAVAILABLE  503   설정이 없다.  재시도해도 같다 — 운영 문의
    LLM_BUDGET_EXCEEDED     503   한도·키 삭제(401·429).  재시도해도 같다 — 운영 문의
    GENERATION_FAILED       500   호출이 깨졌거나 답이 계약을 어겼다.  재시도하면 될 수도

셋을 한 코드로 뭉치면 FE 가 「운영 문의」를 띄워야 할 자리에 「다시 시도」를 띄운다.
"""


class LlmUnavailable(RuntimeError):
    """설정이 없어 부를 수 없다. 교사가 고칠 수 없다."""


class LlmFailed(RuntimeError):
    """불렀는데 실패했거나 답이 계약을 어겼다."""


class LlmBudgetExceeded(RuntimeError):
    """예산·한도에 걸렸다. 키가 삭제됐을 수 있다."""
