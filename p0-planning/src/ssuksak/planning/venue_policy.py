"""Keep another institution's destinations out of automatically generated plans."""

import json
import re

VENUE_POLICY_TAG = "+teacher-venues-v1"
VENUE_GUIDANCE = (
    " 교사가 현재 요청 사항에 직접 지정하지 않은 특정 지역·시설의 이름을 활동 장소로 쓰지 않는다. "
    "다른 기관의 근거·부모 AI 초안에 나온 장소는 우리 원의 방문 예정지가 아니다. "
    "그 장소의 이름만 지워 일반 활동으로 바꾸지 말고, 허용된 다른 일반 활동 근거를 고른다. "
    "교사가 지정한 장소도 이용 가능·예약·방문 일정이 확정됐다고 단정하지 않는다. "
)

_VENUE = re.compile(
    r"(?<![가-힣A-Za-z0-9])(?P<prefix>[가-힣A-Za-z0-9·]{1,30}?)(?P<gap>[ \t]*)"
    r"(?P<kind>유아숲체험원|유아숲체험장|유아숲터|숲체험원|숲체험장|생태공원|"
    r"어린이박물관|어린이회관|문화회관|해수욕장|과학관|박물관|미술관|도서관|"
    r"수목원|식물원|동물원|공원|체험관|체험원|체험장|계곡|유치원|어린이집|"
    r"소방서|경찰서|우체국)"
    r"(?=$|[^가-힣A-Za-z0-9]|에서|으로|에|을|를|은|는|이|가|와|과|의|도)"
)
_GENERIC_PREFIXES = frozenset({
    "우리", "우리원", "우리반", "우리동네", "동네", "마을", "가까운", "주변", "근처", "작은", "큰",
    "새로운", "안전한", "봄", "여름", "가을", "겨울", "어린이", "유아", "실내", "실외",
    "종이", "상자", "블록", "재활용품", "상상", "가상", "놀이", "숲속",
})
_FIELD_TRIP = re.compile(r"[<\[【(]\s*(?:현장\s*학습|견학|현장\s*체험)\s*[>\]】)]")
_DENIAL = re.compile(r"제외|금지|말고|쓰지|넣지|방문하지|가지\s*(?:않|마)|안\s*가|빼\s*(?:줘|주|고|요)")


def named_venues(text: str) -> frozenset[str]:
    # shortcut: suffix detection can miss/overblock names; use reviewed venue annotations if those cases recur.
    return frozenset(
        re.sub(r"\s+", "", match.group()) for match in _VENUE.finditer(text)
        if match.group("prefix") not in _GENERIC_PREFIXES
        and (not match.group("gap") or match.group("kind").startswith("유아숲"))
    )


def unrequested_venues(text: str, teacher_text: str = "") -> frozenset[str]:
    allowed = {
        venue for clause in re.split(r"[\n.!?;]", teacher_text) if not _DENIAL.search(clause)
        for venue in named_venues(clause)
    }
    return named_venues(text) - allowed


def venue_bound_evidence(text: str) -> bool:
    return bool(named_venues(text) or _FIELD_TRIP.search(text))


def venue_memo(user_content: str) -> str:
    """Only the original teacher memo authorizes a venue; rejected output never does."""
    body = json.loads(user_content)
    body = body.get("original_request", body.get("original", body))
    return body.get("teacher_memo", {}).get("text", "")
