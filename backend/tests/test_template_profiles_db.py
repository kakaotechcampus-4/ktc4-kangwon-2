"""월간 TemplateProfile 저장과 선택 정책. 진짜 Postgres 로 본다(Contract 2, 결정 문서 C2.6 · C2.7).

기반 Template 은 실제 데이터 파일을 읽는다. v0.1.1 · v0.2.1 은 **사람 승인 대기**라 그대로는
Reference 기반 시작이 거절된다(결정 문서 12.8). 승인이 필요한 테스트는 OD-N11 (A) 방식 —
테스트 안에서만 `replace(template, runtime_active=True)` 로 만든 승인 객체 — 를 쓴다. 데이터
파일과 운영 코드는 그대로다.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest
from sqlalchemy import delete, inspect, select, update
from sqlalchemy.dialects.postgresql import Insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ssuksak.adapters.monthly_reference_repositories import JsonMonthlyTemplateRepository
from ssuksak.planning import TemplateProfileRef
from ssuksak.planning.application.ports import TemplateProfileRepository
from ssuksak.planning.domain.monthly_template import RepeatBy, SemanticVariant, TemplateRef
from ssuksak.planning.domain.monthly_template_snapshot import TemplateSnapshot

from app.db import engine
from app.features.auth.models import User
from app.features.centers.models import Center, Class
from app.features.template_profiles.models import (
    TemplateProfileDefault,
    TemplateProfileOverride,
    TemplateProfileVersion,
)
from app.features.template_profiles.repository import (
    CLASSROOM_OVERRIDE,
    EXPLICIT_SELECTION,
    INSTITUTION_DEFAULT,
    SELECTION_REQUIRED,
    PostgresTemplateProfileRepository,
    TemplateProfileError,
)

PLAIN = TemplateRef("ssuksak.monthly-template-a", "monthly-template-a-v0.1.1")
FOCUS = TemplateRef("ssuksak.monthly-template-a", "monthly-template-a-v0.2.1")
DEFAULTS = TemplateProfileDefault.__tablename__
LABELS = {
    "theme": "주제",
    "week_axis": "주",
    "outdoor_play": "바깥놀이",
    "safety_education": "안전교육",
    "focus": "소주제",
}


class ApprovedTemplates:
    """OD-N11 (A): 실제 파일을 읽어 테스트 안에서만 승인 상태로 바꾼다."""

    def __init__(self):
        self._real = JsonMonthlyTemplateRepository()

    def get_template(self, template_id, template_version):
        template = self._real.get_template(template_id, template_version)
        return None if template is None else replace(template, runtime_active=True)


def _center(session, name="테스트어린이집") -> Center:
    center = Center(
        name=name, director_name="김원장", region_sido="강원특별자치도", region_sigungu="춘천시"
    )
    session.add(center)
    session.flush()
    return center


def _user(session, center: Center, email="t@example.com") -> User:
    user = User(
        email=email,
        name="선생",
        password_hash=b"x" * 64,
        password_salt=b"y" * 16,
        center_id=center.id,
    )
    session.add(user)
    session.flush()
    return user


def _class(session, center: Center, name="햇살반", school_year=2026) -> Class:
    classroom = Class(
        center_id=center.id,
        name=name,
        school_year=school_year,
        age_min=4,
        age_max=4,
        teacher_name="선생",
    )
    session.add(classroom)
    session.flush()
    return classroom


@pytest.fixture
def world(db_session):
    """원 둘. 각 원에 교사 하나, 반 하나."""
    a = _center(db_session, "가원")
    b = _center(db_session, "나원")
    return {
        "session": db_session,
        "a": a,
        "b": b,
        "user_a": _user(db_session, a, "a@example.com"),
        "user_b": _user(db_session, b, "b@example.com"),
        "class_a": _class(db_session, a),
        "class_b": _class(db_session, b),
        "repo_a": PostgresTemplateProfileRepository(db_session, center_id=a.id),
        "repo_b": PostgresTemplateProfileRepository(db_session, center_id=b.id),
    }


def _start(repo, user, template=FOCUS, optional=("focus",)) -> TemplateProfileRef:
    return repo.start_from_reference(
        ApprovedTemplates(),
        template,
        selected_optional_keys=optional,
        display_labels=LABELS,
        focus_variant=SemanticVariant.SUBTHEME if "focus" in optional else None,
        actor_id=user.id,
    )


def _second_ready(repo, ref, user) -> TemplateProfileRef:
    """READY → DRAFT 파생 → 확정. 같은 계열의 다음 READY."""
    draft = repo.derive_draft(ref, actor_id=user.id)
    repo.publish(draft)
    return draft


def _code(excinfo) -> str:
    return excinfo.value.code


# ── migration ────────────────────────────────────────────────────────────


def test_migration이_테이블과_무결성_제약을_올린다(db_session):
    inspector = inspect(db_session.connection())
    assert {"template_profiles", "template_profile_defaults", "template_profile_overrides"} <= set(
        inspector.get_table_names()
    )
    uniques = {u["name"] for u in inspector.get_unique_constraints("template_profiles")}
    assert {
        "uq_template_profiles_owner_ref",
        "uq_template_profiles_profile_id_profile_version",
    } <= uniques
    for table in ("template_profile_defaults", "template_profile_overrides"):
        targets = [fk for fk in inspector.get_foreign_keys(table) if fk["name"].endswith("_target")]
        assert len(targets) == 1
        assert targets[0]["constrained_columns"] == [
            "center_id",
            "doc_kind",
            "profile_id",
            "profile_version",
        ]
    assert inspector.get_pk_constraint("template_profile_defaults")["constrained_columns"] == [
        "center_id",
        "doc_kind",
    ]
    assert inspector.get_pk_constraint("template_profile_overrides")["constrained_columns"] == [
        "class_id",
        "doc_kind",
    ]


# ── Reference 기반 시작 · 저장 · 왕복 ───────────────────────────────────────


def test_승인_대기_Template_으로는_시작하지_않는다(world):
    """12.8: 실제 v0.1.1 · v0.2.1 은 PENDING 이다. 우회 없이 거절하고 아무것도 남기지 않는다."""
    repo = world["repo_a"]
    for template in (PLAIN, FOCUS):
        with pytest.raises(TemplateProfileError) as excinfo:
            repo.start_from_reference(
                JsonMonthlyTemplateRepository(),
                template,
                selected_optional_keys=(),
                display_labels=LABELS,
                focus_variant=None,
                actor_id=world["user_a"].id,
            )
        assert _code(excinfo) == "TEMPLATE_NOT_APPROVED"
    assert repo.list_ready() == ()


def test_없는_Template_과_잘못된_칸_선택은_저장하지_않는다(world):
    repo, user = world["repo_a"], world["user_a"]
    with pytest.raises(TemplateProfileError) as excinfo:
        _start(repo, user, template=TemplateRef("ssuksak.monthly-template-a", "latest"))
    assert _code(excinfo) == "NOT_FOUND"
    # focus 를 골랐는데 의미(소주제 · 예상놀이)를 안 정하면 Core 가 막는다.
    with pytest.raises(TemplateProfileError) as excinfo:
        repo.start_from_reference(
            ApprovedTemplates(),
            FOCUS,
            selected_optional_keys=("focus",),
            display_labels=LABELS,
            focus_variant=None,
            actor_id=user.id,
        )
    assert _code(excinfo) == "INVALID"
    assert repo.list_ready() == ()


def test_저장한_Profile_이_그대로_돌아오고_Snapshot_과_repeat_by_도_같다(world):
    repo, user = world["repo_a"], world["user_a"]
    ref = _start(repo, user)

    assert ref.profile_version == "v1"
    assert isinstance(repo, TemplateProfileRepository)
    restored = repo.get_profile(ref.profile_id, ref.profile_version)
    assert restored is not None
    assert restored.institution_ref == str(world["a"].id)
    assert restored.classroom_ref is None
    assert restored.base_template_ref == FOCUS
    assert restored.selected_optional_keys == ("focus",)

    # 같은 입력으로 다시 만든 Profile(저장 안 함)과 값이 같아야 한다 — 저장이 무엇도 바꾸지 않았다.
    rebuilt = PostgresTemplateProfileRepository(
        world["session"], center_id=world["a"].id, new_profile_id=lambda: ref.profile_id
    )
    world["session"].execute(
        delete(TemplateProfileVersion).where(TemplateProfileVersion.profile_id == ref.profile_id)
    )
    _start(rebuilt, user)
    assert rebuilt.get_profile(ref.profile_id, "v1") == restored

    snapshot = TemplateSnapshot.from_profile(restored)
    assert snapshot.profile_ref == ref
    repeat_by = {section.section_key: section.repeat_by for section in restored.sections}
    assert repeat_by == {
        "theme": RepeatBy.NONE,
        "week_axis": None,
        "outdoor_play": RepeatBy.WEEK,
        "safety_education": RepeatBy.WEEK,
        "focus": RepeatBy.WEEK,
    }
    assert restored.section("focus").semantic_variant is SemanticVariant.SUBTHEME
    assert {s.section_key: s.display_label for s in restored.sections} == LABELS


def test_정확한_버전만_찾는다(world):
    repo, user = world["repo_a"], world["user_a"]
    v1 = _start(repo, user)
    v2 = _second_ready(repo, v1, user)
    v3 = repo.derive_draft(v2, actor_id=user.id)

    assert repo.get_profile(v1.profile_id, "v1").profile_ref == v1
    assert repo.get_profile(v2.profile_id, "v2").profile_ref == v2
    # DRAFT 로는 생성하지 않는다. latest · 없는 번호는 없다.
    assert repo.get_profile(v3.profile_id, "v3") is None
    assert repo.get_profile(v1.profile_id, "latest") is None
    assert repo.get_profile(v1.profile_id, "v9") is None


# ── 상태: DRAFT 편집 · READY 불변 · 여러 READY ──────────────────────────────


def test_READY_는_고칠_수_없고_고치려면_새_DRAFT_버전이_생긴다(world):
    session, repo, user = world["session"], world["repo_a"], world["user_a"]
    v1 = _start(repo, user)
    original = repo.get_profile(v1.profile_id, "v1")
    relabeled = replace(
        original,
        sections=tuple(
            replace(s, display_label="이번 달 주제") if s.section_key == "theme" else s
            for s in original.sections
        ),
    )

    with pytest.raises(TemplateProfileError) as excinfo:
        repo.update_draft(relabeled)
    assert _code(excinfo) == "NOT_DRAFT"
    with pytest.raises(TemplateProfileError) as excinfo:
        repo.publish(v1)
    assert _code(excinfo) == "NOT_DRAFT"

    v2 = repo.derive_draft(v1, actor_id=user.id)
    assert v2 == TemplateProfileRef(v1.profile_id, "v2")
    repo.update_draft(replace(relabeled, profile_ref=v2))
    repo.update_draft(replace(relabeled, profile_ref=v2))  # DRAFT 는 여러 번 고쳐도 버전이 그대로다
    repo.publish(v2)

    row = session.scalar(
        select(TemplateProfileVersion).where(TemplateProfileVersion.profile_version == "v2")
    )
    assert (row.status, row.parent_version) == ("READY", "v1")
    assert repo.get_profile(v1.profile_id, "v1") == original
    assert repo.get_profile(v1.profile_id, "v2").section("theme").display_label == "이번 달 주제"
    with pytest.raises(TemplateProfileError) as excinfo:
        repo.update_draft(replace(relabeled, profile_ref=v2))
    assert _code(excinfo) == "NOT_DRAFT"

    # DRAFT 에서도 기반 Template 은 못 바꾼다 — 승인 검사를 건너뛰는 길이 된다.
    v3 = repo.derive_draft(v2, actor_id=user.id)
    with pytest.raises(TemplateProfileError) as excinfo:
        repo.update_draft(replace(relabeled, profile_ref=v3, base_template_ref=PLAIN))
    assert _code(excinfo) == "INVALID"


def test_원_하나에_READY_가_여러_개_있을_수_있다(world):
    repo, user = world["repo_a"], world["user_a"]
    a1 = _start(repo, user)
    a2 = _second_ready(repo, a1, user)
    b1 = _start(repo, user, template=PLAIN, optional=())

    assert repo.list_ready() == (a1, a2, b1)
    assert a1.profile_id != b1.profile_id


def test_같은_버전은_두_번_생기지_않는다(world):
    session, user = world["session"], world["user_a"]
    fixed = PostgresTemplateProfileRepository(
        session, center_id=world["a"].id, new_profile_id=lambda: "tprofile_fixed"
    )
    _start(fixed, user)
    with pytest.raises(TemplateProfileError) as excinfo:
        _start(fixed, user)
    assert _code(excinfo) == "CONFLICT"

    # 다른 원도 같은 (profile_id, version) 을 못 가진다 — Core 는 원 없이 이 둘로 찾는다.
    other = PostgresTemplateProfileRepository(
        session, center_id=world["b"].id, new_profile_id=lambda: "tprofile_fixed"
    )
    with pytest.raises(TemplateProfileError) as excinfo:
        _start(other, world["user_b"])
    assert _code(excinfo) == "CONFLICT"
    assert fixed.list_ready() == (TemplateProfileRef("tprofile_fixed", "v1"),)


# ── 포인터: 원 기본 · 반 override ─────────────────────────────────────────


def test_해석_순서는_override_다음_원_기본_둘_다_없으면_선택_필요(world):
    repo, user, class_a = world["repo_a"], world["user_a"], world["class_a"]
    base = _start(repo, user)
    special = _start(repo, user, template=PLAIN, optional=())

    assert repo.resolve(class_a.id).source == SELECTION_REQUIRED
    assert repo.resolve(class_a.id).profile_ref is None

    repo.set_default(base, expected=None, actor_id=user.id)
    assert (repo.resolve(class_a.id).source, repo.resolve(class_a.id).profile_ref) == (
        INSTITUTION_DEFAULT,
        base,
    )

    repo.set_override(class_a.id, special, expected=None, actor_id=user.id)
    assert (repo.resolve(class_a.id).source, repo.resolve(class_a.id).profile_ref) == (
        CLASSROOM_OVERRIDE,
        special,
    )

    # override 를 지우면 원 기본으로 돌아간다.
    repo.clear_override(class_a.id, expected=special)
    assert repo.resolve(class_a.id).profile_ref == base

    # 원 기본도 지우면 다시 선택 필요. 직접 고른 버전은 READY 인지 보고 그대로 쓴다.
    repo.clear_default(expected=base)
    assert repo.resolve(class_a.id).source == SELECTION_REQUIRED
    assert repo.select(special).source == EXPLICIT_SELECTION
    assert repo.select(special).profile_ref == special


def test_포인터는_변경자와_시각을_남긴다(world):
    session, repo, user = world["session"], world["repo_a"], world["user_a"]
    ref = _start(repo, user)
    repo.set_default(ref, expected=None, actor_id=user.id)
    repo.set_override(world["class_a"].id, ref, expected=None, actor_id=user.id)

    for model in (TemplateProfileDefault, TemplateProfileOverride):
        row = session.scalar(select(model))
        assert row.changed_by == user.id
        assert row.changed_at is not None


def test_새_READY_가_생겨도_기본은_움직이지_않는다(world):
    repo, user, class_a = world["repo_a"], world["user_a"], world["class_a"]
    v1 = _start(repo, user)
    repo.set_default(v1, expected=None, actor_id=user.id)
    v2 = _second_ready(repo, v1, user)

    assert repo.resolve(class_a.id).profile_ref == v1
    repo.set_default(v2, expected=v1, actor_id=user.id)  # 사용자가 옮길 때만 움직인다
    assert repo.resolve(class_a.id).profile_ref == v2


def test_포인터는_READY_만_가리킨다(world):
    repo, user, class_a = world["repo_a"], world["user_a"], world["class_a"]
    v1 = _start(repo, user)
    draft = repo.derive_draft(v1, actor_id=user.id)

    for point in (
        lambda ref: repo.set_default(ref, expected=None, actor_id=user.id),
        lambda ref: repo.set_override(class_a.id, ref, expected=None, actor_id=user.id),
    ):
        with pytest.raises(TemplateProfileError) as excinfo:
            point(draft)
        assert _code(excinfo) == "NOT_READY"
        with pytest.raises(TemplateProfileError) as excinfo:
            point(TemplateProfileRef(v1.profile_id, "v9"))
        assert _code(excinfo) == "NOT_FOUND"
    with pytest.raises(TemplateProfileError) as excinfo:
        repo.select(draft)
    assert _code(excinfo) == "NOT_READY"
    assert repo.resolve(class_a.id).source == SELECTION_REQUIRED


def test_다른_원의_Profile_과_반은_없는_것과_같다(world):
    repo_a, repo_b = world["repo_a"], world["repo_b"]
    a_ref = _start(repo_a, world["user_a"])
    b_ref = _start(repo_b, world["user_b"])

    assert repo_b.get_profile(a_ref.profile_id, a_ref.profile_version) is None
    assert repo_b.list_ready() == (b_ref,)
    calls = (
        lambda: repo_b.set_default(a_ref, expected=None, actor_id=world["user_b"].id),
        lambda: repo_b.set_override(
            world["class_b"].id, a_ref, expected=None, actor_id=world["user_b"].id
        ),
        # 남의 원 반에 자기 Profile 을 거는 것도 막는다.
        lambda: repo_a.set_override(
            world["class_b"].id, a_ref, expected=None, actor_id=world["user_a"].id
        ),
        lambda: repo_b.resolve(world["class_a"].id),
        lambda: repo_b.select(a_ref),
        lambda: repo_b.derive_draft(a_ref, actor_id=world["user_b"].id),
        lambda: repo_b.archive(a_ref),
    )
    for call in calls:
        with pytest.raises(TemplateProfileError) as excinfo:
            call()
        assert _code(excinfo) == "NOT_FOUND"
    # 남의 원 Profile 을 자기 원 것인 척 고치지도 못한다.
    draft = repo_a.derive_draft(a_ref, actor_id=world["user_a"].id)
    with pytest.raises(TemplateProfileError) as excinfo:
        repo_b.update_draft(replace(repo_a.get_profile(*_pair(a_ref)), profile_ref=draft))
    assert _code(excinfo) == "NOT_FOUND"


def test_DB_가_다른_원_Profile_을_가리키는_포인터를_막는다(world):
    """Application 검사를 건너뛰어도 복합 FK 가 막는다."""
    session = world["session"]
    a_ref = _start(world["repo_a"], world["user_a"])
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(
                TemplateProfileDefault(
                    center_id=world["b"].id,
                    doc_kind="monthly",
                    profile_id=a_ref.profile_id,
                    profile_version=a_ref.profile_version,
                    changed_by=world["user_b"].id,
                )
            )


def test_보관은_포인터가_가리키면_막고_보관된_버전은_대상이_못_된다(world):
    session, repo, user = world["session"], world["repo_a"], world["user_a"]
    last_year = _class(session, world["a"], school_year=2025)
    by_default = _start(repo, user)
    by_old_override = _start(repo, user, template=PLAIN, optional=())
    unused = _start(repo, user)
    repo.set_default(by_default, expected=None, actor_id=user.id)
    # 지난 학년도 반의 override 도 「사용 중」이다 — 학년도로 거르지 않는다.
    repo.set_override(last_year.id, by_old_override, expected=None, actor_id=user.id)

    for ref in (by_default, by_old_override):
        with pytest.raises(TemplateProfileError) as excinfo:
            repo.archive(ref)
        assert _code(excinfo) == "IN_USE"

    repo.archive(unused)
    assert repo.get_profile(*_pair(unused)) is None
    assert unused not in repo.list_ready()
    assert (
        session.scalar(  # 지우지 않는다
            select(TemplateProfileVersion.status).where(
                TemplateProfileVersion.profile_id == unused.profile_id
            )
        )
        == "ARCHIVED"
    )
    with pytest.raises(TemplateProfileError) as excinfo:
        repo.set_default(unused, expected=by_default, actor_id=user.id)
    assert _code(excinfo) == "NOT_READY"


def test_포인터_대상이_쓸_수_없게_되면_원_기본으로_내려가지_않는다(world):
    """R3 방어. 보관 금지 때문에 정상 경로로는 생기지 않는 데이터를 직접 만든다."""
    session, repo, user, class_a = (
        world["session"],
        world["repo_a"],
        world["user_a"],
        world["class_a"],
    )
    base = _start(repo, user)
    special = _start(repo, user, template=PLAIN, optional=())
    repo.set_default(base, expected=None, actor_id=user.id)
    repo.set_override(class_a.id, special, expected=None, actor_id=user.id)
    session.execute(
        update(TemplateProfileVersion)
        .where(TemplateProfileVersion.profile_id == special.profile_id)
        .values(status="ARCHIVED")
    )

    resolution = repo.resolve(class_a.id)
    assert resolution.source == SELECTION_REQUIRED
    assert resolution.profile_ref is None
    assert resolution.reason == "CLASSROOM_OVERRIDE_NOT_READY"


def test_본_것과_현재_포인터가_다르면_덮어쓰지_않는다(world):
    """두 교사가 같은 화면(기본 없음)을 보고 각자 다른 버전을 기본으로 고른다."""
    repo, user, class_a = world["repo_a"], world["user_a"], world["class_a"]
    first = _start(repo, user)
    second = _start(repo, user, template=PLAIN, optional=())

    repo.set_default(first, expected=None, actor_id=user.id)
    with pytest.raises(TemplateProfileError) as excinfo:
        repo.set_default(second, expected=None, actor_id=user.id)
    assert _code(excinfo) == "CONFLICT"
    with pytest.raises(TemplateProfileError) as excinfo:
        repo.clear_default(expected=second)
    assert _code(excinfo) == "CONFLICT"

    repo.set_override(class_a.id, second, expected=None, actor_id=user.id)
    with pytest.raises(TemplateProfileError) as excinfo:
        repo.set_override(class_a.id, first, expected=first, actor_id=user.id)
    assert _code(excinfo) == "CONFLICT"
    assert repo.resolve(class_a.id).profile_ref == second


def test_동시에_기본을_걸면_하나만_통과한다(_schema):
    """서로 다른 연결 두 개가 같은 순간 「기본 없음」을 보고 기본을 건다."""
    # 다른 연결에 보여야 하므로 커밋하고, 만든 행만 finally 에서 지운다.
    with Session(engine) as session:
        center = _center(session, "동시성 테스트원")
        user = _user(session, center, "concurrency@example.com")
        repo = PostgresTemplateProfileRepository(session, center_id=center.id)
        refs = (_start(repo, user), _start(repo, user, template=PLAIN, optional=()))
        session.commit()
        center_id, user_id = center.id, user.id
    barrier = Barrier(2)
    raced = []

    class RacingSession(Session):
        """두 연결이 INSERT 직전에서 서로를 기다린다 — 둘 다 「기본 없음」을 본 상태다."""

        def execute(self, statement, *args, **kwargs):
            if isinstance(statement, Insert) and statement.table.name == DEFAULTS:
                raced.append(barrier.wait(timeout=10))
            return super().execute(statement, *args, **kwargs)

    def point(ref):
        with RacingSession(engine) as session:
            try:
                PostgresTemplateProfileRepository(session, center_id=center_id).set_default(
                    ref, expected=None, actor_id=user_id
                )
                session.commit()
                return ref
            except TemplateProfileError as error:
                assert error.code == "CONFLICT"
                return None

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(point, refs))
        winners = [ref for ref in results if ref is not None]
        assert sorted(raced) == [0, 1]  # 실제로 겹쳤다
        assert len(winners) == 1
        with Session(engine) as session:
            row = session.scalar(
                select(TemplateProfileDefault).where(TemplateProfileDefault.center_id == center_id)
            )
            assert TemplateProfileRef(row.profile_id, row.profile_version) == winners[0]
    finally:
        with Session(engine) as session:
            for model in (TemplateProfileDefault, TemplateProfileVersion):
                session.execute(delete(model).where(model.center_id == center_id))
            session.execute(delete(User).where(User.id == user_id))
            session.execute(delete(Center).where(Center.id == center_id))
            session.commit()


def _pair(ref):
    return ref.profile_id, ref.profile_version
