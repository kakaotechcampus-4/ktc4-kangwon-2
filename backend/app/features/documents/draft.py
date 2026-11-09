"""문서 초안의 해석 · 지원을 만든다. 사실은 여기서 만들지 않는다 — 라우터가 원문을 붙인다.

**LLM 으로 나가기 전에 실명을 가명으로 바꾸고, 돌아온 글을 실명으로 되돌린다** (ADR-004).
치환에 실패하면 부르지 않고 `DraftFailed` 를 낸다.

LLM 호출 자리는 `_generate` 하나다. 호출과 mock/real 분기는 `shared/llm` 이 한다 —
연간 주제도 같은 문을 쓴다. 각자 부르면 한쪽만 `real` 로 바뀌는 사고가 난다.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass

from ssuksak.adapters.v1_curriculum import v1_curriculum_catalog

from app.shared.childCode import NameTable, SubstitutionError, mask, unmask
from app.shared.llm import LlmFailed, LlmUnavailable, complete_json, is_mock

# 문서의 generation.rule_version 으로 남는다. `_generate` 의 만드는 방식이 바뀌면 올린다.
# v2 (2026-10-15) — 거절 규칙 넷(교사가 안 한 개입 · 진단명/가정 판정 · 근거 없는 변화 ·
#                  개인정보)과 분량(해석 2~4 · 지원 2~3문장)을 프롬프트에 넣었다.
#                  올리지 않으면 v1 로 만든 문서와 구분이 안 된다.
# v3 (2026-11-04) — 관찰일지의 해석(종이의 「배움」 칸)을 교사가 고른 누리과정 영역의
#                  내용범주 · 내용에 비추어 「배움」으로 쓰게 했다(멘토 12주차 리뷰).
RULE_VERSION = "v3"
# mock 초안임을 **본문 밖에서** 알린다. 예전에는 본문 앞에 `[mock]` 을 붙였는데, 교사가 읽는
# 제출 문서에 시스템 글자가 섞였다. 그렇다고 아무 표시도 없으면 mock 을 실제 AI 로 보이게 한다.
# **규칙 버전에서 파생한다** — 규칙이 바뀌었는데 mock 표식만 옛 버전이면 둘이 어긋난다.
MOCK_RULE_VERSION = f"{RULE_VERSION}-mock"


def rule_version() -> str:
    """이 초안이 어떻게 만들어졌나. 화면은 이 값으로 「테스트 초안」을 가른다."""
    return MOCK_RULE_VERSION if is_mock() else RULE_VERSION


KIND_LABELS = {
    "dailyLog": "일일 보육일지",
    "weeklyLog": "주간 보육일지",
    "observation": "관찰일지",
    "assessment": "영유아 평가",
}


SYSTEM_PROMPT = """너는 만 3~5세 유아반 어린이집 교사의 일지 작성을 돕는다.

교사가 적은 **사실**만 받는다. 그 사실에서 「해석」과 「지원」 두 칸을 쓴다.

1. 사실에 없는 일을 쓰지 않는다. 본 것을 넘어서 추측하지 않는다.
   해석에 숫자(횟수 · 날짜 · 인원)를 쓸 때는 사실에 있는 숫자만 쓴다.
2. 해석 — 그 사실이 영유아의 배움·발달에서 무엇을 뜻하는지. 2~4문장.
   어떤 사실에서 나온 말인지 되짚을 수 있어야 한다.
   매일 되풀이되는 일과(간식 · 낮잠 · 손 씻기 · 등하원)는 짧게 쓴다. 같은 말을 길게 늘이지 않는다.
3. 지원 — 교사가 **다음에** 무엇을 어떻게 할지. 구체적인 방법과 후속 관찰 계획. 2~3문장.
4. 각 칸은 20자 이상 쓴다.
5. 아이 이름은 받은 그대로 쓴다. 바꾸거나 빼지 않는다.
6. 한국어로 쓴다. 말투는 현장 일지를 따른다.
   - 해석은 「~한다」 현재형으로 쓴다. 「놀이가 이어진다」 「도움을 청하는 모습을 보인다」
   - 지원은 「~하면 좋을 것 같다」 「~해야겠다」처럼 앞으로의 계획으로 쓴다.
   - 「~했습니다」 같은 경어체는 쓰지 않는다. 일지는 원 안에서 보는 문서다.

**쓰면 안 되는 것**

- 교사가 실제로 하지 않은 개입. 「교사가 격려했다」를 과거형으로 지어내지 않는다.
  지원 칸은 앞으로 할 일이다.
- 진단명과 가정 판정 — ADHD · 자폐 · 언어지연 · 애착장애 · 인지 수준 ·
  가정환경 · 보호자 양육 태도.
- 근거 없는 변화 · 성장. 「예전보다 늘었다」는 **받은 사실 안에 비교할 장면이 있을 때만.**
  한 장면을 장기 변화로 읽지 않는다.
- 가족사 · 건강 · 그 밖의 개인정보. 교사가 사실에 적었어도 해석 · 지원으로 옮기지 않는다.
- 「타고난 집중력」 「뛰어난 사회성」처럼 한 장면을 사람의 성질로 일반화하는 말.

**관찰일지는 해석 칸이 종이에서 「배움」 칸이다.** kind 가 관찰일지면:

- 해석에 사실을 다시 늘어놓지 않는다. 사실은 이미 사실 칸에 있다.
  그 장면에서 아이가 **무엇을 경험하고 배우고 있는지**를 쓴다.
- `curriculum` 이 오면 교사가 고른 누리과정 영역의 내용범주 · 내용이다. 사실에 드러난 것과
  맞닿는 내용을 골라 그 말로 배움을 쓴다. 「(내용범주)의 '(내용)'을 경험한다」처럼 잇는다.
  **목록에 없는 영역 · 내용범주 · 내용을 지어내지 않는다.** 맞닿는 것이 없으면 억지로 잇지 않는다.
- 「~을 경험한다」 「~을 즐긴다」 「~하며 …을 알아 간다」처럼 배움으로 맺는다.

**무엇을 눈여겨보나** — 받은 사실에 드러난 것만 고른다. 나이를 추측하지 않는다.

```
놀이를 스스로 고르고 말로 표현하는 모습
또래와 역할을 맞추고 감정을 조절해 보는 모습
규칙을 이해하고 협상하거나 문제를 풀어 보는 모습
```

반드시 아래 JSON 으로만 답한다.

{"해석": "...", "지원": "..."}"""


def rule_id(kind: str) -> str:
    return f"{kind}-draft"


NAME_MASK_FAILED = "아동 이름을 가명으로 바꾸지 못해 AI 를 부르지 않았습니다."


class DraftFailed(Exception):
    """초안을 만들지 못했다. 부분 결과를 저장하지 않는다 (GENERATION_FAILED)."""


@dataclass(frozen=True)
class DraftSection:
    heading: str
    body: str
    source_ids: list[int]


def draft_sections(
    kind: str,
    facts: list[str],
    source_ids: list[int],
    table: NameTable | None,
    domains: Sequence[str] = (),
) -> list[DraftSection]:
    """해석 · 지원 두 칸을 만든다.

    `table` 은 원 전체 아이(다른 반 포함) 가운데 `facts` 에 나온 아이의 실명 <-> 가명 표다
    (documents.verify.name_table). 글에 아이 이름이 없으면 None 이다.
    - 교사가 `fact` 에 반 친구 · 옆 반 아이 이름을 같이 적기도 해서
      문서 대상 아이 한 명만으로는 부족하다.
    `domains` 는 관찰 기록에 교사가 고른 누리과정 영역이다. 관찰일지 배움 칸의 근거가 된다.
    """
    try:
        masked = facts if table is None else [mask(fact, table) for fact in facts]
    except SubstitutionError as exc:
        raise DraftFailed(NAME_MASK_FAILED) from exc

    def restore(text: str) -> str:
        return text if table is None else unmask(text, table)

    curriculum = _curriculum_for(domains) if kind == "observation" else []
    interpretation, support = _generate(kind, masked, curriculum)
    return [
        DraftSection("해석", restore(interpretation), list(source_ids)),
        DraftSection("지원", restore(support), list(source_ids)),
    ]


def _curriculum_for(domains: Sequence[str]) -> list[dict[str, str]]:
    """그 영역의 누리과정 내용범주 · 내용 — 고시문 전사본(승인된 것)에서 그대로 꺼낸다.

    못 읽으면 빈 목록이다. 배움 칸을 고시문에 잇는 것은 덤이라, 이것 때문에 초안을 막지 않는다.
    """
    if not domains:
        return []
    try:
        catalog = v1_curriculum_catalog()
    except (ValueError, OSError, KeyError, TypeError):
        return []
    return [
        {"영역": c.domain, "내용범주": c.category, "내용": c.text}
        for c in catalog.contents
        if c.domain in domains
    ]


def _generate(
    kind: str, masked_facts: list[str], curriculum: list[dict[str, str]] = ()
) -> tuple[str, str]:
    """가명으로 바뀐 사실만 받는다. 여기서 실명을 볼 일이 없다."""
    label = KIND_LABELS[kind]
    if is_mock():
        # **본문에 `[mock]` 을 붙이지 않는다** — 제출 문서에 시스템 글자가 남는다.
        # mock 이라는 사실은 `rule_version()` 이 `-mock` 꼬리로 알리고 화면이 본문 밖에 띄운다.
        return (
            # 해석에 숫자를 넣지 않는다. 사실에 없는 숫자는 shared/gates 가 막는다.
            f"{label} 해석 초안입니다. 기록에 드러난 사실만 근거로 교사가 의미를 다듬어주세요.",
            f"{label} 지원 초안입니다. 다음 활동에서 교사가 할 구체적인 방법과 "
            "후속 관찰 계획을 적어주세요.",
        )
    try:
        content = complete_json(
            SYSTEM_PROMPT,
            json.dumps(
                {"kind": label, "facts": masked_facts}
                | ({"curriculum": list(curriculum)} if curriculum else {}),
                ensure_ascii=False,
            ),
        )
    except LlmUnavailable as exc:
        # 설정 문제는 교사가 고칠 수 없다. 원인을 감추지 않고 그대로 올린다.
        # LlmBudgetExceeded 는 감싸지 않는다 — 라우터가 503 LLM_BUDGET_EXCEEDED 로 따로 낸다.
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
