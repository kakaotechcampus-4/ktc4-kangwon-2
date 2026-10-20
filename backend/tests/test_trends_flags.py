"""검열 2단 — 표시만 하고 거르지 않는다 (ADR-016)."""

from app.features.trends.flags import RiskGroup, flags, load
from app.features.trends.item import RawItem


def item(title: str, description: str = "") -> RawItem:
    return RawItem(
        source="youtube",
        source_id="x",
        title=title,
        description=description,
        url="https://example.com",
        published_at="2026-10-16",
        origin="테스트채널",
    )


GROUPS = (RiskGroup(name="질식·기절", why="", words=("기절", "목 조르")),)


def test_제목이_아니라_설명에서도_찾는다():
    """위험한 동작은 제목에 안 나온다 (ADR-016 3단과 같은 이유)."""
    assert flags(item("재미있는 놀이", "친구 목 조르기 놀이예요"), GROUPS) == ["질식·기절"]


def test_안_걸리면_빈_목록():
    assert flags(item("신문지 공 만들기", "바구니에 던져요"), GROUPS) == []


def test_같은_무리가_여러_낱말로_걸려도_한_번만_적는다():
    assert flags(item("기절", "목 조르기도 한다"), GROUPS) == ["질식·기절"]


def test_목록에_출처가_적혀_있다():
    """낱말을 지어내지 않는다. 「왜 걸렀나」를 설명 못 하면 검열이 아니라 취향이다."""
    import yaml

    from app.features.trends.flags import RISK_PATH

    body = yaml.safe_load(RISK_PATH.read_text(encoding="utf-8"))
    assert body["sources"], "출처가 비어 있다"
    assert all(s.get("url", "").startswith("http") for s in body["sources"])
    for group in body["groups"]:
        assert group.get("why"), f"{group['name']} 에 왜 위험한지가 없다"


def test_실제_목록이_읽힌다():
    groups = load()
    assert len(groups) >= 5
    assert any(g.name == "질식·기절" for g in groups)
