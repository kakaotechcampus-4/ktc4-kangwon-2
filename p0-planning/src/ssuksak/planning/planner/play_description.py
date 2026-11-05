"""Monthly v1 play values keep a short name and a teacher-facing explanation."""

from .v1_guidance import NATURAL_PLAY_GUIDANCE

PLAY_DESCRIPTION_TAG = "+play-descriptions-v1"
PLAY_DESCRIPTION_INVALID = "PLAY_DESCRIPTION_INVALID"
PLAY_KEYS = frozenset({"outdoor_play", "indoor_alternative"})


def describes_play(request, section_key: str) -> bool:
    return section_key in PLAY_KEYS and PLAY_DESCRIPTION_TAG in request.prompt_version


def valid_play_description(value: str, canonical_name: str | None = None) -> bool:
    if canonical_name is not None:
        prefix = canonical_name + ":"
        return value.startswith(prefix) and bool(value[len(prefix):].strip())
    name, separator, description = value.partition(":")
    return bool(name.strip() and separator and description.strip())


def with_play_descriptions(prompt: str) -> str:
    canonical = ("the locked theme text for theme, or the canonical activity name followed by ': ' "
                 "and one short description for outdoor_play")
    prompt = prompt.replace("the canonical label of the\nreferenced item", canonical)
    prompt = prompt.replace("the canonical label of the referenced item", canonical)
    prompt = prompt.replace("reference_id로 고른 활동은 그 이름 그대로 둔다.",
                            "reference_id로 고른 활동은 이름 부분을 그대로 두고 설명을 붙인다.")
    prompt = prompt.replace("outdoor_play · indoor_alternative: 대상과 경험이 드러나는 짧고 익숙한 활동명으로 쓰며",
                            "outdoor_play · indoor_alternative: 활동명 부분은 대상과 경험이 드러나는 짧고 익숙한 이름으로 쓰며")
    prompt = prompt.replace("Write a short activity name, not a lesson script.",
                            "Write 'activity name: one short description', not a lesson script.")
    return prompt + NATURAL_PLAY_GUIDANCE + """
outdoor_play와 indoor_alternative의 value는 반드시 '활동명: 설명'으로 쓴다.
활동명은 무엇을 가지고 무엇을 하는지 보이는 짧은 이름이다. 설명은 v2 놀이 설명과
같은 합니다체 한 문장으로, 교사가 어떤 놀이인지 알도록 대상과 실제 행동을 쓴다.
제목만 반복하거나 '경험합니다'만으로 끝내지 않고, 바깥놀이를 실내로 이어 간다는
배경 설명보다 이 활동에서 무엇을 하는지 직접 쓴다. 진행 순서·발문·발달 효과를
덧붙이지 않는다. 근거에서 확인되는 방법과 재료만 쓰고 준비물이 있다고 단정하지 않는다.
Catalog reference_id를 쓰면 이름은 해당 label을 정확히 유지하고 그 뒤에 ': 설명'을
붙인다. 설명도 그 활동이 뜻하는 경험 안에서만 쓴다. reference_id를 버리거나
다른 활동 이름으로 바꾸지 않는다. theme 및 다른 칸에는 이 형식을 적용하지 않는다.
"""
