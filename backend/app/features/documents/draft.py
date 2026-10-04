"""문서 초안의 해석 · 지원을 만든다. 사실은 여기서 만들지 않는다 — 라우터가 원문을 붙인다.

**LLM 으로 나가기 전에 실명을 가명으로 바꾸고, 돌아온 글을 실명으로 되돌린다** (ADR-004).
치환에 실패하면 부르지 않고 `DraftFailed` 를 낸다.

LLM 호출 자리는 `_generate` 하나다. 호출과 mock/real 분기는 `shared/llm` 이 한다 —
연간 주제도 같은 문을 쓴다. 각자 부르면 한쪽만 `real` 로 바뀌는 사고가 난다.
"""

import json
from dataclasses import dataclass

from app.shared.childCode import NameTable, SubstitutionError, mask, unmask
from app.shared.llm import LlmBudgetExceeded, LlmFailed, LlmUnavailable, complete_json, is_mock

# 문서의 generation.rule_version 으로 남는다. `_generate` 의 만드는 방식이 바뀌면 올린다.
RULE_VERSION = "v1"

KIND_LABELS = {
    "dailyLog": "일일 보육일지",
    "weeklyLog": "주간 보육일지",
    "observation": "관찰일지",
    "assessment": "영유아 평가",
}


SYSTEM_PROMPT = """너는 어린이집 교사의 일지 작성을 돕는다.

교사가 적은 **사실**만 받는다. 그 사실에서 「해석」과 「지원」 두 칸을 쓴다.

1. 사실에 없는 일을 쓰지 않는다. 본 것을 넘어서 추측하지 않는다.
   해석에 숫자(횟수 · 날짜 · 인원)를 쓸 때는 사실에 있는 숫자만 쓴다.
2. 해석 — 그 사실이 영유아의 배움·발달에서 무엇을 뜻하는지.
3. 지원 — 교사가 다음에 무엇을 어떻게 할지. 구체적인 방법과 후속 관찰 계획.
4. 각 칸은 20자 이상 쓴다.
5. 아이 이름은 받은 그대로 쓴다. 바꾸거나 빼지 않는다.
6. 한국어로 쓴다.

반드시 아래 JSON 으로만 답한다.

{"해석": "...", "지원": "..."}"""


def rule_id(kind: str) -> str:
    return f"{kind}-draft"


class DraftFailed(Exception):
    """초안을 만들지 못했다. 부분 결과를 저장하지 않는다 (GENERATION_FAILED)."""


@dataclass(frozen=True)
class DraftSection:
    heading: str
    body: str
    source_ids: list[int]


def draft_sections(
    kind: str, facts: list[str], source_ids: list[int], children: dict[str, str]
) -> list[DraftSection]:
    """해석 · 지원 두 칸을 만든다.

    `children` 은 이 반 아이들의 {실명: 가명} 이다.
    - 교사가 `fact` 에 반 친구 이름을 같이 적기도 해서 문서 대상 아이 한 명만으로는 부족하다.
    """
    try:
        table = NameTable(children)
        masked = [mask(fact, table) for fact in facts]
    except SubstitutionError as exc:
        raise DraftFailed("아동 이름을 가명으로 바꾸지 못해 AI 를 부르지 않았습니다.") from exc

    interpretation, support = _generate(kind, masked)
    return [
        DraftSection("해석", unmask(interpretation, table), list(source_ids)),
        DraftSection("지원", unmask(support, table), list(source_ids)),
    ]


def _generate(kind: str, masked_facts: list[str]) -> tuple[str, str]:
    """가명으로 바뀐 사실만 받는다. 여기서 실명을 볼 일이 없다."""
    label = KIND_LABELS[kind]
    if is_mock():
        # **`[mock]` 을 앞에 붙인다.** 교사가 눈으로 알아보고, 그대로 확정하지 않게 한다.
        return (
            # 해석에 숫자를 넣지 않는다. 사실에 없는 숫자는 shared/gates 가 막는다.
            f"[mock] {label} 해석 초안입니다. 기록에 드러난 사실만 근거로 "
            "교사가 의미를 다듬어주세요.",
            f"[mock] {label} 지원 초안입니다. 다음 활동에서 교사가 할 구체적인 방법과 "
            "후속 관찰 계획을 적어주세요.",
        )
    try:
        content = complete_json(
            SYSTEM_PROMPT,
            json.dumps({"kind": label, "facts": masked_facts}, ensure_ascii=False),
        )
    except (LlmUnavailable, LlmBudgetExceeded) as exc:
        # 설정·한도 문제는 교사가 고칠 수 없다. 원인을 감추지 않고 그대로 올린다.
        raise DraftFailed(str(exc)) from exc
    except LlmFailed as exc:
        raise DraftFailed("AI 초안을 만들지 못했습니다. 다시 시도해주세요.") from exc
    return _parse(content)


def _parse(content: str) -> tuple[str, str]:
    """**모델이 준 것을 그대로 믿지 않는다.**

    한 칸이라도 비면 거부한다. 빈 칸을 그대로 내보내면 3층 규격 검사(`shared/gates`)가
    나중에 막긴 하지만, 교사는 그때까지 「AI 가 만들어줬다」고 믿는다.
    """
    try:
        parsed = json.loads(content)
        interpretation, support = parsed["해석"], parsed["지원"]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise DraftFailed("AI 응답이 약속한 형식이 아닙니다.") from exc
    for name, value in (("해석", interpretation), ("지원", support)):
        if not isinstance(value, str) or not value.strip():
            raise DraftFailed(f"AI 가 「{name}」 칸을 채우지 못했습니다.")
    return interpretation.strip(), support.strip()
