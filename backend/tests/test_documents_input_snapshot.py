"""문서는 만들 때의 입력을 사본으로 갖는다 — 영역 · 상황 · 영역 축 (ADR-077).

종이 · 미리보기 · stale 판단이 원본 대신 사본을 본다. 실제 LLM 은 부르지 않는다 —
`complete_json` 을 가짜로 바꿔 무엇이 나가는지만 잡는다.
"""

import importlib.util
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.features.centers.models import Center, Class
from app.features.documents import draft as draft_module
from app.features.documents.models import Document, DocumentSource
from app.features.observations.models import Observation
from app.main import app

client = TestClient(app)
ALL_CHECKED = {"checks": {"fact": True, "interpretation": True, "support": True}}
SUPPORT = "다음에는 돋보기를 두고 함께 관찰해 보면 좋을 것 같다."


@pytest.fixture(autouse=True)
def _logged_in(db_session, teacher):
    db_session.info["teacher"] = teacher


@pytest.fixture
def sun(db_session, teacher):
    center = Center(
        name="테스트어린이집", director_name="김원장", region_sido="강원", region_sigungu="춘천"
    )
    db_session.add(center)
    db_session.flush()
    teacher.center_id = center.id
    klass = Class(
        center_id=center.id,
        name="햇살반",
        school_year=2026,
        age_min=4,
        age_max=4,
        teacher_name="김선생",
        consent_confirmed_at=datetime(2026, 3, 2, tzinfo=UTC),
    )
    db_session.add(klass)
    db_session.flush()
    return klass


def _child(klass, name="이서윤"):
    res = client.post(f"/api/classes/{klass.id}/children", json={"name": name})
    assert res.status_code == 201, res.text
    return res.json()


def _obs(klass, child, day, fact, domain="자연탐구", context="바깥놀이", month=9):
    res = client.post(
        "/api/observations",
        json={
            "class_id": klass.id,
            "child_id": child["id"],
            "date": f"2026-{month:02d}-{day:02d}",
            "domain": domain,
            "context": context,
            "fact": fact,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _create(klass, child, observations, month=9):
    return client.post(
        "/api/documents",
        json={
            "kind": "observation",
            "class_id": klass.id,
            "child_id": child["id"],
            "start": f"2026-{month:02d}-01",
            "end": f"2026-{month:02d}-30",
            "source_ids": [o["id"] for o in observations],
        },
    )


def _put_obs(obs, **changes):
    body = {k: obs[k] for k in ("date", "domain", "context", "fact")} | changes
    return client.put(f"/api/observations/{obs['id']}", json=body)


def _set_axis(klass, axis):
    res = client.put(f"/api/centers/{klass.center_id}/settings", json={"observation_axis": axis})
    assert res.status_code == 200, res.text


@pytest.fixture
def llm_seen(monkeypatch):
    """draft 가 LLM 에 넘기는 user 글을 잡는다. 해석은 `interpretation` 으로 바꿀 수 있다."""
    seen = {"payloads": [], "interpretation": "작은 생물을 오래 지켜보며 자연에 관심을 보인다."}

    def fake_complete_json(system_prompt, user_content, **_):
        seen["payloads"].append(user_content)
        return json.dumps({"해석": seen["interpretation"], "지원": SUPPORT}, ensure_ascii=False)

    monkeypatch.setattr(draft_module, "is_mock", lambda: False)
    monkeypatch.setattr(draft_module, "complete_json", fake_complete_json)
    return seen


# ── 만들 때 사본을 찍는다 ─────────────────────────────────────────────────────


def test_만들_때_영역_상황_축을_사본으로_찍고_상세가_준다(sun):
    me = _child(sun)
    obs = _obs(sun, me, 5, "개미를 바라보았다.", context="모래놀이터")
    plain = _obs(sun, me, 6, "지렁이를 찾았다.", domain="의사소통", context="")

    res = _create(sun, me, [obs, plain])

    assert res.status_code == 201, res.text
    body = res.json()
    assert body["observation_axis"] == "NURI_5"
    assert [(s["domain"], s["context"]) for s in body["sources"]] == [
        ("자연탐구", "모래놀이터"),
        ("의사소통", ""),
    ]


def test_원의_지금_축이_아닌_기록으로는_만들지_않는다(sun):
    """양식에 그 영역 줄이 없다. 만들어 두면 확정한 뒤 내보낼 때야 막힌다."""
    me = _child(sun)
    old = _obs(sun, me, 5, "개미를 바라보았다.")
    _set_axis(sun, "DAILY_PLAY_2")

    res = _create(sun, me, [old])

    assert res.status_code == 422
    assert res.json()["error"]["fields"] == [f"sources.{old['id']}"]


# ── S1 · S7 (재현 테스트를 뒤집은 것) ────────────────────────────────────────


@pytest.mark.parametrize(
    "changes", [{"domain": "신체운동·건강"}, {"context": "실내"}], ids=["domain", "context"]
)
def test_S1_확정본_근거의_영역이나_상황만_고쳐도_stale_이라_내보내지_않는다(sun, changes):
    me = _child(sun)
    obs = _obs(sun, me, 5, "개미를 바라보았다.")
    doc_id = _create(sun, me, [obs]).json()["id"]
    assert client.post(f"/api/documents/{doc_id}/confirm", json=ALL_CHECKED).status_code == 200

    assert _put_obs(obs, **changes).status_code == 200

    assert client.get(f"/api/documents/{doc_id}").json()["stale"] is True
    res = client.get(f"/api/documents/{doc_id}/export/hwp")
    assert res.status_code == 409
    assert res.json()["error"]["fields"] == ["stale"]


def test_S7_원이_축을_바꿔도_확정본은_만들_때의_양식으로_나간다(sun):
    me = _child(sun)
    obs = _obs(sun, me, 5, "개미를 바라보았다.")
    doc_id = _create(sun, me, [obs]).json()["id"]
    assert client.post(f"/api/documents/{doc_id}/confirm", json=ALL_CHECKED).status_code == 200

    _set_axis(sun, "DAILY_PLAY_2")

    assert client.get(f"/api/documents/{doc_id}/export/hwp").status_code == 200
    assert client.get(f"/api/documents/{doc_id}").json()["observation_axis"] == "NURI_5"


# ── refresh ─────────────────────────────────────────────────────────────────


def test_refresh_는_영역_상황_사본도_새로_뜬다(sun):
    me = _child(sun)
    obs = _obs(sun, me, 5, "개미를 바라보았다.")
    doc_id = _create(sun, me, [obs]).json()["id"]
    assert _put_obs(obs, domain="신체운동·건강", context="실내").status_code == 200

    res = client.post(f"/api/documents/{doc_id}/refresh")

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["stale"] is False
    assert (body["sources"][0]["domain"], body["sources"][0]["context"]) == (
        "신체운동·건강",
        "실내",
    )


def test_refresh_는_축이_다른_원본이면_거절한다(sun):
    """원이 축을 바꾼 뒤 옛 기록을 새 축 영역으로 고쳤다. 이 문서의 양식(5영역)에 그 줄이 없다."""
    me = _child(sun)
    obs = _obs(sun, me, 5, "개미를 바라보았다.")
    doc_id = _create(sun, me, [obs]).json()["id"]
    _set_axis(sun, "DAILY_PLAY_2")
    assert _put_obs(obs, domain="놀이활동").status_code == 200

    res = client.post(f"/api/documents/{doc_id}/refresh")

    assert res.status_code == 409
    assert res.json()["error"]["code"] == "GATE_BLOCKED"
    assert res.json()["error"]["fields"] == [f"sources.{obs['id']}"]
    assert client.get(f"/api/documents/{doc_id}").json()["stale"] is True


def test_refresh_는_사본이_없는_옛_문서를_채운다(sun, db_session):
    """「다시 확인」 문서는 refresh 로 지금 원본의 영역 · 상황과 원의 지금 축을 찍는다."""
    me = _child(sun)
    obs = _obs(sun, me, 5, "개미를 바라보았다.")
    doc_id = _create(sun, me, [obs]).json()["id"]
    copy = db_session.query(DocumentSource).filter_by(document_id=doc_id).one()
    copy.domain = copy.context = None
    db_session.get(Document, doc_id).observation_axis = None
    db_session.flush()

    body = client.post(f"/api/documents/{doc_id}/refresh").json()

    assert body["observation_axis"] == "NURI_5"
    assert (body["sources"][0]["domain"], body["sources"][0]["context"]) == ("자연탐구", "바깥놀이")


# ── G1 · G2 LLM 입력 (재현 테스트를 뒤집은 것) ───────────────────────────────


def test_G1_G2_LLM_에_사실마다_날짜_영역_상황이_가명으로_간다(sun, llm_seen):
    me = _child(sun)
    friend = _child(sun, "박하준")
    a = _obs(sun, me, 5, "개미를 바라보았다.", context="박하준과 모래놀이터")
    b = _obs(sun, me, 9, "이서윤이 말을 걸었다.", domain="의사소통", context="")

    res = _create(sun, me, [a, b])

    assert res.status_code == 201, res.text
    assert res.json()["generation"]["rule_version"] == "v4"
    raw = llm_seen["payloads"][0]
    assert "이서윤" not in raw and "박하준" not in raw
    assert json.loads(raw)["facts"] == [
        {
            "fact": "개미를 바라보았다.",
            "date": "2026-09-05",
            "domain": "자연탐구",
            "context": f"{friend['code']}과 모래놀이터",
        },
        {
            "fact": f"{me['code']}이 말을 걸었다.",
            "date": "2026-09-09",
            "domain": "의사소통",
            "context": "",
        },
    ]


def test_해석에_근거_날짜를_써도_숫자_게이트를_지난다(sun, llm_seen):
    """「11월 4일」은 사실 글에 없지만 교사가 준 날짜다. 지어낸 숫자가 아니다."""
    me = _child(sun)
    obs = _obs(sun, me, 4, "개미를 바라보았다.", month=11)
    llm_seen["interpretation"] = "11월 4일에 작은 생물을 오래 지켜보며 자연에 관심을 보인다."

    res = _create(sun, me, [obs], month=11)

    assert res.status_code == 201, res.text
    doc_id = res.json()["id"]
    assert client.post(f"/api/documents/{doc_id}/confirm", json=ALL_CHECKED).status_code == 200


def test_근거에_없는_날짜는_여전히_숫자_게이트에_걸린다(sun, llm_seen):
    me = _child(sun)
    obs = _obs(sun, me, 4, "개미를 바라보았다.", month=11)
    llm_seen["interpretation"] = "11월 7일에 작은 생물을 오래 지켜보며 자연에 관심을 보인다."

    res = _create(sun, me, [obs], month=11)

    assert res.status_code == 500
    assert res.json()["error"]["code"] == "GENERATION_FAILED"


# ── 마이그레이션 채우기 규칙 ─────────────────────────────────────────────────

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic/versions/20261109_1200_6aca7868e15a_document_input_snapshot.py"
)


def _backfill():
    spec = importlib.util.spec_from_file_location("snapshot_migration", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.backfill


def _legacy(db_session, klass, child_id, rows, created=datetime(2026, 9, 10, tzinfo=UTC)):
    """사본 칸이 생기기 전의 문서. `rows` 는 (영역, 원본 마지막 수정 시각, 사본 글) 목록이다."""
    doc = Document(
        kind="observation",
        title="t",
        class_id=klass.id,
        child_id=child_id,
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 30),
        status="CONFIRMED",
        origin="AI",
        created_at=created,
    )
    db_session.add(doc)
    db_session.flush()
    for domain, updated, text in rows:
        obs = Observation(
            class_id=klass.id,
            child_id=child_id,
            date=date(2026, 9, 5),
            domain=domain,
            context="바깥놀이",
            fact="개미를 바라보았다.",
            updated_at=updated,
        )
        db_session.add(obs)
        db_session.flush()
        db_session.add(
            DocumentSource(
                document_id=doc.id,
                source_kind="observation",
                source_id=obs.id,
                class_id=klass.id,
                child_id=child_id,
                date=obs.date,
                text=text,
            )
        )
    db_session.flush()
    return doc


def _snapshot_of(db_session, doc):
    db_session.expire_all()
    copies = db_session.query(DocumentSource).filter_by(document_id=doc.id).order_by("id")
    return db_session.get(Document, doc.id).observation_axis, [
        (c.domain, c.context) for c in copies
    ]


def test_채우기_규칙(sun, db_session):
    child_id = _child(sun)["id"]
    before = datetime(2026, 9, 9, 23, 58, tzinfo=UTC)  # 문서보다 2분 먼저
    edge = datetime(2026, 9, 9, 23, 59, 30, tzinfo=UTC)  # 30초 먼저 — 1분 안이라 확실하지 않다
    after = datetime(2026, 9, 11, tzinfo=UTC)
    same = "개미를 바라보았다."

    filled = _legacy(db_session, sun, child_id, [("자연탐구", before, same)])
    play = _legacy(db_session, sun, child_id, [("놀이활동", before, same)])
    mixed = _legacy(
        db_session, sun, child_id, [("자연탐구", before, same), ("놀이활동", before, same)]
    )
    edited = _legacy(
        db_session, sun, child_id, [("자연탐구", before, same), ("자연탐구", after, same)]
    )
    near = _legacy(db_session, sun, child_id, [("자연탐구", edge, same)])
    differs = _legacy(db_session, sun, child_id, [("자연탐구", before, "옛 글")])

    _backfill()(db_session.connection())

    assert _snapshot_of(db_session, filled) == ("NURI_5", [("자연탐구", "바깥놀이")])
    assert _snapshot_of(db_session, play) == ("DAILY_PLAY_2", [("놀이활동", "바깥놀이")])
    # 영역이 두 축에 걸치면 축을 정하지 않는다.
    assert _snapshot_of(db_session, mixed) == (
        None,
        [("자연탐구", "바깥놀이"), ("놀이활동", "바깥놀이")],
    )
    # 문서 뒤에 고친 원본은 만들 때 값을 모른다. 하나라도 모르면 축도 정하지 않는다.
    assert _snapshot_of(db_session, edited) == (None, [("자연탐구", "바깥놀이"), (None, None)])
    assert _snapshot_of(db_session, near) == (None, [(None, None)])
    # 사본 글이 원본과 다르면(그 뒤 고쳤다가 되돌렸을 수도 있다) 채우지 않는다.
    assert _snapshot_of(db_session, differs) == (None, [(None, None)])


def test_채우기는_다시_돌려도_채운_값을_덮지_않는다(sun, db_session):
    child_id = _child(sun)["id"]
    doc = _legacy(
        db_session,
        sun,
        child_id,
        [("자연탐구", datetime(2026, 9, 1, tzinfo=UTC), "개미를 바라보았다.")],
    )
    backfill = _backfill()
    backfill(db_session.connection())
    db_session.query(Observation).update({"context": "실내"})
    db_session.flush()

    backfill(db_session.connection())

    assert _snapshot_of(db_session, doc) == ("NURI_5", [("자연탐구", "바깥놀이")])
