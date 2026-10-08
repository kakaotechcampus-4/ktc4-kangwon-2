"""월간 TemplateProfile 저장과 선택 정책 (Contract 2 — 결정 문서 C2.6 · C2.7).

p0-planning 의 `TemplateProfileRepository` 포트(`get_profile`)를 Postgres 로 구현하고, Core 밖에
있어야 하는 것 — 버전 상태, 원 기본 · 반 override 포인터, 해석 순서 — 을 여기서 지킨다.
Core 는 정확한 `(profile_id, profile_version)` 하나를 받기만 한다.

**원 하나에 묶인다.** plans repository 와 같다. 남의 원 Profile · 반은 없는 것과 같다(NOT_FOUND).

**자동으로 고르지 않는다.** latest 도, 조용한 fallback 도 없다. 포인터는 사용자 행동으로만
움직이고, 포인터가 가리키는 대상이 쓸 수 없으면 다음 단계로 내려가지 않고 「선택 필요」다(R3).

**포인터 변경은 compare-and-set 이다.** 호출자는 화면에서 본 현재 값(`expected`)을 같이 보낸다.
그 사이 누가 바꿨으면 덮어쓰지 않고 CONFLICT 다 — 한 문장(INSERT … ON CONFLICT DO NOTHING /
UPDATE … WHERE 현재값)이라 동시 요청도 둘 중 하나만 통과한다.

커밋은 호출자가 한다. 보관 검사와 상태 변경이 한 transaction 안에 있어야 하기 때문이다.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace

from psycopg.errors import UniqueViolation
from sqlalchemy import delete, exists, func, literal_column, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ssuksak.planning import InvalidDomainValueError, TemplateProfileRef
from ssuksak.planning.application.ports import MonthlyTemplateRepository
from ssuksak.planning.domain.monthly_template import SemanticVariant, TemplateRef
from ssuksak.planning.domain.monthly_template_profile import (
    DEFAULT_PROFILE_SECTION_KEYS,
    TemplateProfile,
)

from app.features.centers.models import Class
from app.features.plans.codec import from_jsonable, to_jsonable
from app.features.template_profiles.models import (
    TemplateProfileDefault,
    TemplateProfileOverride,
    TemplateProfileVersion,
)

DOC_KIND = "monthly"

# 해석 결과의 출처 (C2.7 R1 · R2 · R4 · R6).
CLASSROOM_OVERRIDE = "CLASSROOM_OVERRIDE"
INSTITUTION_DEFAULT = "INSTITUTION_DEFAULT"
EXPLICIT_SELECTION = "EXPLICIT_SELECTION"
SELECTION_REQUIRED = "SELECTION_REQUIRED"

# Template A 는 옛 이름 `habits` 로 적혀 있다. Profile 은 `basic_habit` 으로 바꿔 담는다(Core 별칭).
_TEMPLATE_KEY = {"basic_habit": "habits"}


class TemplateProfileError(Exception):
    """`code` 는 테스트가 보는 의미 식별자다. 공개 HTTP 오류 코드는 API PR 이 정한다.

    NOT_FOUND · NOT_DRAFT · NOT_READY · CLASSROOM_SCOPED · IN_USE · CONFLICT ·
    TEMPLATE_NOT_APPROVED · INVALID
    """

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Resolution:
    """어느 Profile 버전을 어디서 가져왔는지(R6). 「선택 필요」면 `profile_ref` 가 없다."""

    source: str
    profile_ref: TemplateProfileRef | None = None
    reason: str | None = None


def _new_profile_id() -> str:
    return f"tprofile_{uuid.uuid4().hex}"


def _ref(row) -> TemplateProfileRef:
    return TemplateProfileRef(row.profile_id, row.profile_version)


class PostgresTemplateProfileRepository:
    """한 원의 월간 TemplateProfile 버전과 포인터를 읽고 쓴다."""

    def __init__(
        self,
        session: Session,
        *,
        center_id: int,
        new_profile_id: Callable[[], str] = _new_profile_id,
    ):
        self._session = session
        self._center_id = center_id
        self._new_profile_id = new_profile_id

    # ── Core 포트 ──────────────────────────────────────────────────────────

    def get_profile(self, profile_id: str, profile_version: str) -> TemplateProfile | None:
        """생성이 쓰는 조회. **READY 만** 준다 — DRAFT · ARCHIVED 로는 계획안을 만들지 않는다."""
        row = self._session.scalar(
            self._version_query(profile_id, profile_version).where(
                TemplateProfileVersion.status == "READY"
            )
        )
        return None if row is None else from_jsonable(TemplateProfile, row.body)

    # ── 버전 ──────────────────────────────────────────────────────────────

    def start_from_reference(
        self,
        templates: MonthlyTemplateRepository,
        template_ref: TemplateRef,
        *,
        selected_optional_keys: tuple[str, ...],
        display_labels: Mapping[str, str],
        focus_variant: SemanticVariant | None,
        actor_id: int,
    ) -> TemplateProfileRef:
        """「Reference 기반으로 시작」 — 기반 Template + 고른 Optional 칸 → 원 소유 READY v1.

        **기반 Template 이 사람 승인을 받았는지 본다** (결정 문서 12.8). 승인 대기 Template 으로
        시작하지 않는다. 우회 경로를 두지 않는다.
        기본 포인터는 걸지 않는다 — 사용자가 동의할 때 `set_default` 를 따로 부른다.
        """
        template = templates.get_template(template_ref.template_id, template_ref.template_version)
        if template is None:
            raise TemplateProfileError("NOT_FOUND", f"Template {template_ref} 가 없다")
        if not template.is_active:
            raise TemplateProfileError(
                "TEMPLATE_NOT_APPROVED", f"Template {template_ref} 는 사람 승인 전이다"
            )
        wanted = DEFAULT_PROFILE_SECTION_KEYS | set(selected_optional_keys)
        sections = []
        for key in sorted(wanted):
            section = template.section(_TEMPLATE_KEY.get(key, key))
            if section is None:
                raise TemplateProfileError("INVALID", f"Template 에 {key} 칸이 없다")
            sections.append(
                replace(
                    section,
                    activated=True,
                    display_label=display_labels.get(key, section.display_label),
                    semantic_variant=(
                        (focus_variant or section.semantic_variant)
                        if key == "focus"
                        else section.semantic_variant
                    ),
                )
            )
        try:
            profile = TemplateProfile(
                profile_ref=TemplateProfileRef(self._new_profile_id(), "v1"),
                institution_ref=str(self._center_id),
                base_template_ref=template.template_ref,
                selected_optional_keys=tuple(selected_optional_keys),
                sections=tuple(sections),
            )
        except InvalidDomainValueError as error:
            raise TemplateProfileError("INVALID", str(error)) from error
        self._insert(profile, status="READY", parent_version=None, actor_id=actor_id)
        return profile.profile_ref

    def derive_draft(self, ready_ref: TemplateProfileRef, *, actor_id: int) -> TemplateProfileRef:
        """READY 를 고치려면 새 DRAFT 버전을 만든다. READY 는 그대로 남는다."""
        row = self._version(ready_ref)
        if row.status != "READY":
            raise TemplateProfileError("NOT_READY", f"{ready_ref} 는 READY 가 아니다")
        family = self._session.scalar(
            select(func.count()).where(
                TemplateProfileVersion.center_id == self._center_id,
                TemplateProfileVersion.profile_id == row.profile_id,
            )
        )
        # 버전 행은 지우지 않으므로 개수가 곧 마지막 번호다. 동시 파생은 유일 제약이 막는다.
        new_ref = TemplateProfileRef(row.profile_id, f"v{family + 1}")
        profile = replace(from_jsonable(TemplateProfile, row.body), profile_ref=new_ref)
        self._insert(profile, status="DRAFT", parent_version=row.profile_version, actor_id=actor_id)
        return new_ref

    def update_draft(self, profile: TemplateProfile) -> None:
        """DRAFT 만 고칠 수 있다. READY · ARCHIVED 는 불변이다.

        기반 Template 은 바꾸지 못한다 — 승인 검사는 Reference 기반 시작에서 한 번 했다.
        """
        self._check_owned_shape(profile)
        row = self._version(profile.profile_ref, lock=True)
        if row.status != "DRAFT":
            raise TemplateProfileError("NOT_DRAFT", f"{profile.profile_ref} 는 고칠 수 없다")
        if to_jsonable(profile.base_template_ref) != row.body["base_template_ref"]:
            raise TemplateProfileError("INVALID", "DRAFT 의 기반 Template 은 바꿀 수 없다")
        row.body = to_jsonable(profile)
        self._session.flush()

    def publish(self, draft_ref: TemplateProfileRef) -> None:
        """DRAFT → READY. 본문은 저장할 때 이미 Core 검증을 통과했다."""
        row = self._version(draft_ref, lock=True)
        if row.status != "DRAFT":
            raise TemplateProfileError("NOT_DRAFT", f"{draft_ref} 는 DRAFT 가 아니다")
        row.status = "READY"
        self._session.flush()

    def archive(self, ref: TemplateProfileRef) -> None:
        """READY → ARCHIVED. 포인터가 하나라도 가리키면(학년도 무관) 막는다. 자동 해제 없음.

        버전 행을 FOR UPDATE 로 잡는다. 포인터를 거는 쪽은 같은 행을 FOR SHARE 로 잡으므로
        「검사 → 보관」 사이에 새 포인터가 끼어들지 못한다.
        """
        row = self._version(ref, lock=True)
        if row.status != "READY":
            raise TemplateProfileError("NOT_READY", f"{ref} 는 READY 가 아니다")
        in_use = self._session.scalar(
            select(
                exists().where(
                    TemplateProfileDefault.profile_id == row.profile_id,
                    TemplateProfileDefault.profile_version == row.profile_version,
                )
                | exists().where(
                    TemplateProfileOverride.profile_id == row.profile_id,
                    TemplateProfileOverride.profile_version == row.profile_version,
                )
            )
        )
        if in_use:
            raise TemplateProfileError("IN_USE", f"{ref} 를 가리키는 포인터가 있다")
        row.status = "ARCHIVED"
        self._session.flush()

    def list_ready(self) -> tuple[TemplateProfileRef, ...]:
        """「선택 필요」일 때 보여 줄 후보 (R4)."""
        rows = self._session.scalars(
            select(TemplateProfileVersion)
            .where(
                TemplateProfileVersion.center_id == self._center_id,
                TemplateProfileVersion.doc_kind == DOC_KIND,
                TemplateProfileVersion.status == "READY",
            )
            .order_by(TemplateProfileVersion.created_at, TemplateProfileVersion.id)
        )
        return tuple(_ref(row) for row in rows)

    # ── 포인터 ────────────────────────────────────────────────────────────

    def set_default(
        self,
        ref: TemplateProfileRef,
        *,
        expected: TemplateProfileRef | None,
        actor_id: int,
    ) -> None:
        """원 기본을 `ref` 로. `expected` 는 사용자가 본 현재 기본(없었으면 None)."""
        self._set_pointer(
            TemplateProfileDefault,
            {"center_id": self._center_id, "doc_kind": DOC_KIND},
            ref,
            expected,
            actor_id,
        )

    def clear_default(self, *, expected: TemplateProfileRef) -> None:
        self._clear_pointer(
            TemplateProfileDefault, {"center_id": self._center_id, "doc_kind": DOC_KIND}, expected
        )

    def set_override(
        self,
        class_id: int,
        ref: TemplateProfileRef,
        *,
        expected: TemplateProfileRef | None,
        actor_id: int,
    ) -> None:
        self._own_class(class_id)
        self._set_pointer(
            TemplateProfileOverride,
            {"class_id": class_id, "doc_kind": DOC_KIND},
            ref,
            expected,
            actor_id,
            center_id=self._center_id,
        )

    def clear_override(self, class_id: int, *, expected: TemplateProfileRef) -> None:
        self._own_class(class_id)
        self._clear_pointer(
            TemplateProfileOverride, {"class_id": class_id, "doc_kind": DOC_KIND}, expected
        )

    # ── 해석 ──────────────────────────────────────────────────────────────

    def resolve(self, class_id: int) -> Resolution:
        """R1 반 override → R2 원 기본 → R4 선택 필요.

        R3: 찾은 포인터의 대상이 쓸 수 없으면 **다음 단계로 내려가지 않는다.** 내려가면 사용자가
        고른 반 설정이 조용히 무시된다.
        """
        self._own_class(class_id)
        steps = (
            (CLASSROOM_OVERRIDE, TemplateProfileOverride, {"class_id": class_id}),
            (INSTITUTION_DEFAULT, TemplateProfileDefault, {"center_id": self._center_id}),
        )
        for source, model, key in steps:
            pointer = self._session.scalar(select(model).filter_by(doc_kind=DOC_KIND, **key))
            if pointer is None:
                continue
            ref = _ref(pointer)
            problem = self._target_problem(self._session.scalar(self._version_query(*_split(ref))))
            if problem is not None:
                return Resolution(SELECTION_REQUIRED, reason=f"{source}_{problem}")
            return Resolution(source, ref)
        return Resolution(SELECTION_REQUIRED, reason="NO_POINTER")

    def select(self, ref: TemplateProfileRef) -> Resolution:
        """사용자가 직접 고른 버전 (R4 · R5). 포인터가 바뀌었다고 다시 해석하지 않는다."""
        self._ready_target(ref, lock=False)
        return Resolution(EXPLICIT_SELECTION, ref)

    # ── 내부 ──────────────────────────────────────────────────────────────

    def _version_query(self, profile_id: str, profile_version: str):
        return select(TemplateProfileVersion).where(
            TemplateProfileVersion.center_id == self._center_id,
            TemplateProfileVersion.doc_kind == DOC_KIND,
            TemplateProfileVersion.profile_id == profile_id,
            TemplateProfileVersion.profile_version == profile_version,
        )

    def _version(self, ref: TemplateProfileRef, *, lock: bool = False) -> TemplateProfileVersion:
        query = self._version_query(*_split(ref))
        row = self._session.scalar(query.with_for_update() if lock else query)
        if row is None:
            raise TemplateProfileError("NOT_FOUND", f"{ref} 가 없다")
        return row

    @staticmethod
    def _target_problem(row: TemplateProfileVersion | None) -> str | None:
        """포인터 대상 조건(C2.6): 존재 · READY · classroom_ref 없음. 원 · 종류는 쿼리가 본다."""
        if row is None:
            return "NOT_FOUND"
        if row.status != "READY":
            return "NOT_READY"
        if row.body.get("classroom_ref") is not None:
            return "CLASSROOM_SCOPED"
        return None

    def _ready_target(self, ref: TemplateProfileRef, *, lock: bool) -> None:
        query = self._version_query(*_split(ref))
        # FOR SHARE — 포인터를 거는 동안 같은 버전이 보관되지 못하게 한다(archive 와 짝).
        problem = self._target_problem(
            self._session.scalar(query.with_for_update(read=True) if lock else query)
        )
        if problem is not None:
            raise TemplateProfileError(problem, f"{ref} 는 포인터 대상이 될 수 없다")

    def _set_pointer(self, model, key, ref, expected, actor_id, **extra) -> None:
        self._ready_target(ref, lock=True)
        target = {
            "profile_id": ref.profile_id,
            "profile_version": ref.profile_version,
            "changed_by": actor_id,
            "changed_at": func.now(),
        }
        if expected is None:
            statement = insert(model).values(**key, **extra, **target).on_conflict_do_nothing()
        else:
            statement = update(model).filter_by(**key, **_target_of(expected)).values(**target)
        self._require_one_changed(statement)

    def _clear_pointer(self, model, key, expected: TemplateProfileRef) -> None:
        self._require_one_changed(delete(model).filter_by(**key, **_target_of(expected)))

    def _require_one_changed(self, statement) -> None:
        # Session 을 거친 INSERT 는 rowcount 를 -1 로 준다. RETURNING 으로 실제 바뀐 행을 센다.
        if self._session.execute(statement.returning(literal_column("1"))).first() is None:
            raise TemplateProfileError("CONFLICT", "포인터가 그 사이 바뀌었다")

    def _own_class(self, class_id: int) -> None:
        classroom = self._session.get(Class, class_id)
        if classroom is None or classroom.center_id != self._center_id:
            raise TemplateProfileError("NOT_FOUND", "반이 없다")

    def _check_owned_shape(self, profile: TemplateProfile) -> None:
        if profile.institution_ref != str(self._center_id):
            raise TemplateProfileError("NOT_FOUND", "다른 원의 Profile 이다")
        # Contract 2 는 반 전용 Profile 을 쓰지 않는다(C2-G). 포인터 대상 조건 ④.
        if profile.classroom_ref is not None:
            raise TemplateProfileError("CLASSROOM_SCOPED", "P0 Profile 은 classroom_ref 가 없다")

    def _insert(
        self,
        profile: TemplateProfile,
        *,
        status: str,
        parent_version: str | None,
        actor_id: int,
    ) -> None:
        self._check_owned_shape(profile)
        row = TemplateProfileVersion(
            center_id=self._center_id,
            doc_kind=DOC_KIND,
            profile_id=profile.profile_ref.profile_id,
            profile_version=profile.profile_ref.profile_version,
            status=status,
            parent_version=parent_version,
            body=to_jsonable(profile),
            created_by=actor_id,
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
        except IntegrityError as error:
            if not isinstance(error.orig, UniqueViolation):
                raise
            raise TemplateProfileError(
                "CONFLICT", f"{profile.profile_ref} 버전이 이미 있다"
            ) from error


def _split(ref: TemplateProfileRef) -> tuple[str, str]:
    return ref.profile_id, ref.profile_version


def _target_of(ref: TemplateProfileRef) -> dict[str, str]:
    return {"profile_id": ref.profile_id, "profile_version": ref.profile_version}
