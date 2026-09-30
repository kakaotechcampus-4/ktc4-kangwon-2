"""문서 초안의 해석 · 지원을 만든다. 사실은 여기서 만들지 않는다 — 라우터가 원문을 붙인다.

**LLM 으로 나가기 전에 실명을 가명으로 바꾸고, 돌아온 글을 실명으로 되돌린다** (ADR-004).
치환에 실패하면 부르지 않고 `DraftFailed` 를 낸다.

LLM 호출 자리는 `_generate` 하나다. 백엔드 LLM 클라이언트(`shared/llm`)가 생기기 전까지는
`LLM_MODE=mock`(기본값) 에서만 고정 문장을 내고, `real` 에서는 만들지 않고 실패한다.
"""

from dataclasses import dataclass

from app.config import settings
from app.shared.childCode import NameTable, SubstitutionError, mask, unmask

# 문서의 generation.rule_version 으로 남는다. `_generate` 의 만드는 방식이 바뀌면 올린다.
RULE_VERSION = "v1"

KIND_LABELS = {
    "dailyLog": "일일 보육일지",
    "weeklyLog": "주간 보육일지",
    "observation": "관찰일지",
    "assessment": "영유아 평가",
}


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
    if settings.llm_mode != "mock":
        raise DraftFailed("백엔드 LLM 연결이 아직 없습니다 (shared/llm).")
    label = KIND_LABELS[kind]
    return (
        f"[mock] {label} 해석 초안입니다. 기록 {len(masked_facts)}건에 드러난 사실만 근거로 "
        "교사가 의미를 다듬어주세요.",
        f"[mock] {label} 지원 초안입니다. 다음 활동에서 교사가 할 구체적인 방법과 "
        "후속 관찰 계획을 적어주세요.",
    )
